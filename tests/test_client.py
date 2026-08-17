from __future__ import annotations

import inspect
import io
import json
import ssl
import unittest
import urllib.request
from unittest.mock import patch

import cursor_usage_menubar.client as client_mod
from cursor_usage_menubar.client import fetch_usage, json_request
from cursor_usage_menubar.models import Session


class _Resp:
    def __init__(self, payload: dict, status: int = 200):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _RawResp:
    def __init__(self, raw: bytes):
        self._raw = raw

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ClientTest(unittest.TestCase):
    def test_json_request_sets_connect_and_certifi(self):
        captured = {}

        def fake_open(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            captured["timeout"] = timeout
            return _Resp({"ok": True})

        with patch.object(client_mod._OPENER, "open", fake_open):
            data = json_request(
                "POST",
                "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage",
                token="secret-token",
                body={},
            )
        self.assertEqual(data, {"ok": True})
        self.assertEqual(captured["headers"]["authorization"], "Bearer secret-token")
        self.assertEqual(captured["headers"]["connect-protocol-version"], "1")
        self.assertEqual(captured["timeout"], 8)
        # certifi-backed TLS context is wired into the shared opener, not
        # passed per-call (needed so the no-redirect handler stays in effect).
        self.assertIsInstance(client_mod._SSL_CONTEXT, ssl.SSLContext)

    def test_json_request_invalid_utf8_body_returns_none(self):
        def fake_open(req, timeout=None):
            return _RawResp(b"\xff\xfe\xfa\x00not-utf8")

        with patch.object(client_mod._OPENER, "open", fake_open):
            data = json_request("GET", "https://cursor.com/api/usage-summary")
        self.assertIsNone(data)

    def test_json_request_malformed_json_body_returns_none(self):
        def fake_open(req, timeout=None):
            return _RawResp(b"{not valid json")

        with patch.object(client_mod._OPENER, "open", fake_open):
            data = json_request("GET", "https://cursor.com/api/usage-summary")
        self.assertIsNone(data)

    def test_no_redirect_handler_refuses_redirects(self):
        handler = client_mod._NoRedirectHandler()
        req = urllib.request.Request("https://cursor.com/api/usage-summary")
        result = handler.redirect_request(
            req, None, 302, "Found", {}, "https://evil.example.com/steal-cookie"
        )
        self.assertIsNone(result)

    def test_opener_never_follows_even_same_host_redirect(self):
        # Ruling: simplest safe opener refuses all redirects, same-host or not.
        handler = client_mod._NoRedirectHandler()
        req = urllib.request.Request("https://cursor.com/api/usage-summary")
        result = handler.redirect_request(
            req, None, 302, "Found", {}, "https://cursor.com/api/other"
        )
        self.assertIsNone(result)

    def test_fetch_usage_merges_mocked_apis_and_drops_session(self):
        session = Session(
            access_token="tok",
            sub="user",
            email="ada@example.com",
            team_id=7,
            team_name="Acme",
            plan_hint="enterprise",
        )
        calls = []

        def fake_json_request(method, url, *, token=None, cookie=None, body=None):
            calls.append(url)
            if url.endswith("usage-summary"):
                return {
                    "individualUsage": {
                        "overall": {"used": 500, "limit": 1000, "remaining": 500}
                    }
                }
            if url.endswith("GetAggregatedUsageEvents"):
                self.assertEqual(body, {"teamId": 7})
                return {
                    "aggregations": [
                        {"modelIntent": "auto-smart", "totalCents": 500, "inputTokens": 1, "outputTokens": 1}
                    ],
                    "totalCostCents": 500,
                }
            if url.endswith("GetFilteredUsageEvents"):
                return {"usageEvents": []}
            if url.endswith("GetPlanInfo"):
                return {"planName": "Enterprise"}
            if url.endswith("GetCurrentPeriodUsage"):
                return {}
            return {}

        with (
            patch("cursor_usage_menubar.client.read_session", return_value=session),
            patch("cursor_usage_menubar.client.json_request", fake_json_request),
        ):
            snap = fetch_usage()
        self.assertEqual(snap.spent_cents, 500)
        self.assertEqual(snap.percent, 50)
        self.assertEqual(snap.plan_name, "Enterprise")
        self.assertTrue(any("usage-summary" in u for u in calls))
        self.assertFalse(hasattr(fetch_usage, "session"))
        import cursor_usage_menubar.client as client_mod

        self.assertFalse(hasattr(client_mod, "_SESSION"))
        self.assertFalse(hasattr(client_mod, "access_token"))

    def test_no_session_returns_status(self):
        with patch("cursor_usage_menubar.client.read_session", return_value=None):
            snap = fetch_usage()
        self.assertEqual(snap.status, "Open Cursor to refresh your session")
        self.assertIsNone(snap.spent_cents)

    def test_source_never_refreshes_oauth(self):
        import cursor_usage_menubar.client as client_mod

        source = inspect.getsource(client_mod)
        self.assertNotIn("/oauth/token", source)


if __name__ == "__main__":
    unittest.main()
