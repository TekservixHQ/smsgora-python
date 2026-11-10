import hashlib, hmac, json, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from smsgora import SmsGora, SmsGoraError, verify_webhook

CALLS = []


class Handler(BaseHTTPRequestHandler):
    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        CALLS.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path.startswith("/limit"):
            self.send_response(429); self.send_header("Retry-After", "7"); self.end_headers()
            self.wfile.write(b'{"success":false,"message":"Too many requests"}'); return
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"success": True, "data": {"ok": True}}).encode())
    do_GET = do_POST = do_DELETE = do_PUT = _go
    def log_message(self, *a): pass


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.c = SmsGora("sgk_test", base_url="http://127.0.0.1:%d/" % cls.srv.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def last(self):
        return CALLS[-1]

    def test_send(self):
        self.assertEqual(self.c.send_sms(to="+1555", message="hi"), {"ok": True})
        m, p, h, b = self.last()
        self.assertEqual((m, p), ("POST", "/send-sms"))
        self.assertEqual(h["x-api-key"], "sgk_test")
        self.assertEqual(b, {"recipients": ["+1555"], "message": "hi"})

    def test_send_device(self):
        self.c.send_sms(to=["+1", "+2"], message="x", device_id=42, sim_slot=1, schedule_at="2026-12-01T08:00:00Z")
        m, p, h, b = self.last()
        self.assertEqual(p, "/devices/42/send-sms")
        self.assertEqual(b["sim_slot"], 1)
        self.assertEqual(b["schedule_at"], "2026-12-01T08:00:00Z")

    def test_bulk_and_lists(self):
        self.c.send_bulk_sms(42, [{"recipients": ["+1"]}], message_template="t")
        self.assertEqual(self.last()[3], {"messages": [{"recipients": ["+1"]}], "messageTemplate": "t"})
        self.c.list_received_sms(device_id=3, limit=5, since=None)
        self.assertEqual(self.last()[1], "/devices/3/get-received-sms?limit=5")
        self.c.list_messages(status="sent")
        self.assertEqual(self.last()[1], "/messages?status=sent")
        self.c.delete_webhook(9)
        self.assertEqual(self.last()[:2], ("DELETE", "/webhooks/9"))

    def test_error(self):
        c = SmsGora("k", base_url="http://127.0.0.1:%d/limit" % self.srv.server_port)
        with self.assertRaises(SmsGoraError) as e:
            c.get_account()
        self.assertEqual((e.exception.status, e.exception.retry_after, str(e.exception)), (429, 7.0, "Too many requests"))

    def test_webhook(self):
        raw = b'{"event":"sms.received"}'
        sig = "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook(raw, sig, "s3cret"))
        self.assertTrue(verify_webhook(raw.decode(), sig, "s3cret"))
        self.assertFalse(verify_webhook(raw, sig, "wrong"))
        self.assertFalse(verify_webhook(raw, None, "s3cret"))

    def test_requires_key(self):
        with self.assertRaises(ValueError):
            SmsGora("")


if __name__ == "__main__":
    unittest.main()
