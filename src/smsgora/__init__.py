"""Python client for the SMS Gora SMS Gateway API.

Docs: https://tekservix.com/smsgora/docs/
"""

import datetime as _dt
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request

__all__ = ["SmsGora", "SmsGoraError", "verify_webhook"]
__version__ = "1.0.0"

DEFAULT_BASE_URL = "https://tekservix.com/smsgora/api/v1"


class SmsGoraError(Exception):
    """Raised when the API answers with an error.

    Attributes: status (HTTP code), errors (field errors), body (parsed answer)
    and retry_after (seconds, on 429).
    """

    def __init__(self, message, status=None, errors=None, body=None, retry_after=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.errors = errors
        self.body = body
        self.retry_after = retry_after


def _q(value):
    return urllib.parse.quote(str(value), safe="")


def _query(params):
    if not params:
        return ""
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    return "?" + urllib.parse.urlencode(clean) if clean else ""


class SmsGora:
    """Client for the SMS Gora SMS Gateway.

    >>> sms = SmsGora(api_key="sgk_...")
    >>> sms.send_sms(to="+15551234567", message="Your code is 482913")
    """

    def __init__(self, api_key, base_url=DEFAULT_BASE_URL, timeout=30):
        if not api_key:
            raise ValueError("SmsGora: api_key is required (create one in SMS Gora -> API keys)")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method, path, body=None):
        """Call any documented endpoint, e.g. request("GET", "/devices"). Returns the `data` field."""
        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "smsgora-python/" + __version__,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                status, text, retry = res.status, res.read().decode("utf-8"), None
        except urllib.error.HTTPError as err:
            status, text = err.code, err.read().decode("utf-8", "replace")
            retry = err.headers.get("Retry-After") if err.headers else None
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            parsed = None
        failed = status >= 400 or (isinstance(parsed, dict) and parsed.get("success") is False)
        if failed:
            msg = parsed.get("message") if isinstance(parsed, dict) else None
            raise SmsGoraError(
                msg or "HTTP %d" % status,
                status=status,
                errors=parsed.get("errors") if isinstance(parsed, dict) else None,
                body=parsed if parsed is not None else text,
                retry_after=float(retry) if retry else None,
            )
        if isinstance(parsed, dict) and "data" in parsed:
            return parsed["data"]
        return parsed

    def send_sms(self, to, message, device_id=None, sim_slot=None, schedule_at=None):
        """Send an SMS to one number or a list (up to 1,000). Picks your best online phone unless device_id is given.

        sim_slot: 0 = SIM 1, 1 = SIM 2. schedule_at: datetime or ISO string.
        """
        recipients = [to] if isinstance(to, str) else list(to)
        body = {"recipients": recipients, "message": message}
        if sim_slot is not None:
            body["sim_slot"] = sim_slot
        if schedule_at:
            if isinstance(schedule_at, _dt.datetime):
                schedule_at = schedule_at.isoformat()
            body["schedule_at"] = schedule_at
        path = "/devices/%s/send-sms" % _q(device_id) if device_id else "/send-sms"
        return self.request("POST", path, body)

    def send_bulk_sms(self, device_id, messages, message_template=None):
        """Different texts for different people in one call (up to 5,000 recipients).

        messages: [{"recipients": ["+1555..."], "message": "optional own text"}, ...]
        """
        body = {"messages": messages}
        if message_template is not None:
            body["messageTemplate"] = message_template
        return self.request("POST", "/devices/%s/send-bulk-sms" % _q(device_id), body)

    def get_message(self, message_id):
        """Status is queued, dispatched, sent, delivered, failed or cancelled."""
        return self.request("GET", "/messages/%s" % _q(message_id))

    def cancel_message(self, message_id):
        """Cancel a queued or scheduled message."""
        return self.request("POST", "/messages/%s/cancel" % _q(message_id))

    def list_messages(self, **filters):
        """Filters: direction (in/out), status, device_id, phone, since, after_id, page, limit."""
        return self.request("GET", "/messages" + _query(filters))

    def list_received_sms(self, device_id=None, **filters):
        """Incoming SMS for all phones, or one phone with device_id."""
        path = "/devices/%s/get-received-sms" % _q(device_id) if device_id else "/received-sms"
        return self.request("GET", path + _query(filters))

    def get_batch(self, batch_id):
        return self.request("GET", "/batches/%s" % _q(batch_id))

    def list_devices(self):
        """Your linked Android phones."""
        return self.request("GET", "/devices")

    def get_device(self, device_id):
        return self.request("GET", "/devices/%s" % _q(device_id))

    def get_account(self):
        """Account, plan and usage."""
        return self.request("GET", "/account")

    def list_webhooks(self):
        return self.request("GET", "/webhooks")

    def create_webhook(self, url, events=("sms.received",), device_id=None):
        """Register a webhook. The answer includes the secret (only returned once)."""
        return self.request("POST", "/webhooks", {"url": url, "events": list(events), "device_id": device_id})

    def delete_webhook(self, webhook_id):
        return self.request("DELETE", "/webhooks/%s" % _q(webhook_id))


def verify_webhook(raw_body, signature, secret):
    """Check the X-SmsGora-Signature header (sha256=<hex HMAC-SHA256 of the raw body>).

    raw_body: bytes or str exactly as received, before JSON parsing.
    """
    if not raw_body or not signature or not secret:
        return False
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(signature).encode("utf-8"), expected.encode("utf-8"))
