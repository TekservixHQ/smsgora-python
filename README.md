# smsgora

Python client for the [SMS Gora SMS Gateway](https://tekservix.com/smsgora/) API.

SMS Gora turns Android phones with ordinary SIM cards into an SMS gateway. Your server calls the API, a linked phone sends the text, and replies and delivery reports come back to you. There's no sender ID registration and no per-message fee from us: your mobile operator bills the texts like any SMS.

- Zero dependencies (standard library only), Python 3.8+
- Works in Django, Flask, FastAPI, scripts and cron jobs
- Webhook signature check built in

## Install

```bash
pip install smsgora
```

## Quick start

Create an API key in the SMS Gora dashboard (SMS Gora -> API keys) and keep it on your server.

```python
import os
from smsgora import SmsGora

sms = SmsGora(api_key=os.environ["SMSGORA_KEY"])

result = sms.send_sms(to="+15551234567", message="Your verification code is 482913")
print(result["message_ids"])  # [1873]
```

## Sending

```python
from datetime import datetime, timezone

# Several recipients (up to 1,000 per call)
sms.send_sms(to=["+15551234567", "+447700900123"], message="Your order has shipped")

# From a chosen phone and SIM, scheduled for later
sms.send_sms(
    to="+15551234567",
    message="Reminder: your appointment is tomorrow at 10:00",
    device_id=42,
    sim_slot=1,  # 0 = SIM 1, 1 = SIM 2
    schedule_at=datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc),
)

# Different texts for different people in one call (up to 5,000 recipients)
sms.send_bulk_sms(
    42,
    message_template="Hello, your parcel is ready for pickup.",
    messages=[
        {"recipients": ["+15551234567"], "message": "Hi Aline, parcel #1042 is ready."},
        {"recipients": ["+15557654321"]},
    ],
)
```

## Delivery status and incoming SMS

```python
msg = sms.get_message(1873)
print(msg["status"])  # queued -> dispatched -> sent -> delivered (or failed)

sms.cancel_message(1874)  # works while queued or scheduled

inbox = sms.list_received_sms(since="2026-11-01", limit=50)
phones = sms.list_devices()
account = sms.get_account()
```

Anything else in the [API reference](https://tekservix.com/smsgora/docs/) is one call away:

```python
batch = sms.request("GET", "/batches/311")
```

## Webhooks

Add your HTTPS URL in SMS Gora -> Webhooks (or with `create_webhook`) and keep the secret. Each request carries `X-SmsGora-Signature: sha256=...`, an HMAC-SHA256 of the raw body. Check it before trusting the request. Flask example:

```python
import json, os
from flask import Flask, request, abort
from smsgora import verify_webhook

app = Flask(__name__)

@app.post("/sms/webhook")
def sms_webhook():
    if not verify_webhook(request.get_data(), request.headers.get("X-SmsGora-Signature"),
                          os.environ["SMSGORA_WEBHOOK_SECRET"]):
        abort(401)
    event = json.loads(request.get_data())
    if event["event"] == "sms.received":
        print(event["data"]["from"], event["data"]["message"])
    return "", 200  # answer within 10 seconds; queue slow work
```

In Django use `request.body`; in FastAPI use `await request.body()`. Always pass the raw bytes, not re-encoded JSON.

## Errors

Failed calls raise `SmsGoraError` with `status`, `message`, field `errors` and, on 429, `retry_after` in seconds.

```python
from smsgora import SmsGoraError

try:
    sms.send_sms(to="+15551234567", message="Hi")
except SmsGoraError as err:
    if err.status == 429:
        pass  # rate limit (300 requests/minute per key) or plan limit reached
```

Never ship the key inside a browser or mobile app: anyone could read it. Call the API from your server.

## Migrating from TextBee

SMS Gora accepts TextBee-style requests, so most integrations switch by changing the base URL and key. See the [compatibility notes](https://tekservix.com/smsgora/docs/).

## Good to know

A phone-based gateway suits OTPs, order alerts, reminders and two-way conversations at moderate volume. It isn't meant for mass marketing blasts, and in the US high-volume business texting belongs on registered 10DLC or toll-free numbers.

## More from Tekservix

- [WAservix WhatsApp API Gateway](https://tekservix.com/waservix/): send WhatsApp messages from your own number (`pip install waservix`)
- [AI Sales Agent](https://tekservix.com/ai-sales-agent): answers customers on WhatsApp and SMS using your website's content
- [Website to App](https://tekservix.com/mobile-apps): turn your website into Android and iOS apps
- Also on npm: `npm install smsgora`

## License

MIT
