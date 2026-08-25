from __future__ import annotations

import inspect
import io
import json
import ssl
import unittest
import urllib.request
from unittest.mock import patch

import cursor_usage_menubar.client as client_mod
from cursor_usage_menubar.client import (
    combine_aggregations,
    fetch_filtered_usage_events,
    fetch_usage,
    filter_events_for_email,
    find_member_id,
    json_request,
    load_group_models,
    parse_groups,
)
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
                self.assertEqual(body.get("teamId"), 7)
                self.assertIn("startDate", body)
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

    def test_parse_groups_and_member_id(self):
        groups = parse_groups(
            {
                "groups": [
                    {"id": 9485, "name": "Platform"},
                    {"groupId": "12", "groupName": "Other"},
                    {"id": 9485, "name": "dup"},
                ]
            }
        )
        self.assertEqual([(g.id, g.name) for g in groups], [(9485, "Platform"), (12, "Other")])
        billed = parse_groups(
            {
                "groups": [
                    {
                        "id": 9484,
                        "name": "xDome-R&D",
                        "spendCents": 630274,
                        "members": [
                            {
                                "userId": 1,
                                "email": "ada@example.com",
                                "name": "Ada",
                                "spendCents": 630274,
                                "effectivePerUserLimitDollars": 500,
                            }
                        ],
                    }
                ],
                "unassignedGroup": {"id": -1, "name": "Unassigned", "spendCents": 10},
                "unassignedMembers": [],
            }
        )
        self.assertEqual(billed[0].spend_cents, 630274)
        self.assertEqual(billed[0].limit_cents, 50000)
        self.assertEqual(billed[0].members[0].user_id, 1)
        self.assertEqual(billed[-1].id, -1)
        self.assertEqual(billed[-1].name, "Unassigned")
        self.assertEqual(
            find_member_id(
                {"teamMembers": [{"id": 99, "email": "Ada@example.com"}]},
                "ada@example.com",
            ),
            99,
        )

    def test_filter_events_for_email(self):
        payload = {
            "usageEvents": [
                {"userEmail": "ada@example.com", "chargedCents": 10},
                {"userEmail": "other@example.com", "chargedCents": 90},
            ]
        }
        filtered = filter_events_for_email(payload, "ada@example.com")
        self.assertEqual(filtered["usageEvents"], [payload["usageEvents"][0]])

    def test_fetch_usage_uses_get_groups_spend(self):
        session = Session(
            access_token="tok",
            sub="user",
            email="ada@example.com",
            team_id=7,
            team_name="Acme",
            plan_hint="enterprise",
        )
        bodies = []

        def fake_json_request(method, url, *, token=None, cookie=None, body=None):
            bodies.append((url, body))
            if url.endswith("GetGroups"):
                return {
                    "groups": [
                        {
                            "id": 9484,
                            "name": "xDome-R&D",
                            "spendCents": 630274,
                            "members": [
                                {
                                    "userId": 1,
                                    "name": "Ada",
                                    "email": "ada@example.com",
                                    "spendCents": 630274,
                                    "effectivePerUserLimitDollars": 500,
                                }
                            ],
                        }
                    ]
                }
            if "usage-summary" in url:
                return {
                    "individualUsage": {
                        "overall": {"used": 40000, "limit": 50000, "remaining": 10000}
                    }
                }
            if url.endswith("GetAggregatedUsageEvents"):
                return {"aggregations": [], "totalCostCents": 4060727}
            if url.endswith("GetFilteredUsageEvents"):
                return {"usageEvents": []}
            if url.endswith("GetPlanInfo"):
                return {"planName": "Enterprise"}
            return {}

        with (
            patch("cursor_usage_menubar.client.read_session", return_value=session),
            patch("cursor_usage_menubar.client.json_request", fake_json_request),
        ):
            snap = fetch_usage(scope="group", group_id=9484)
        self.assertEqual(snap.spent_cents, 630274)
        self.assertEqual(snap.limit_cents, 50000)
        self.assertEqual(snap.view_label(), "xDome-R&D (9484)")
        self.assertEqual(snap.breakdown_kind, "models")
        self.assertEqual(snap.models, ())
        self.assertEqual(snap.selected_members()[0].name, "Ada")
        agg = [body for url, body in bodies if url.endswith("GetAggregatedUsageEvents")]
        self.assertTrue(not agg or "groupId" not in (agg[0] or {}))

    def test_combine_aggregations_sums_models_across_users(self):
        combined = combine_aggregations(
            [
                {
                    "totalCostCents": 100,
                    "aggregations": [
                        {"modelIntent": "grok", "totalCents": 60, "inputTokens": 2, "outputTokens": 1},
                        {"modelIntent": "auto", "totalCents": 40, "inputTokens": 1, "outputTokens": 1},
                    ],
                },
                {
                    "totalCostCents": 50,
                    "aggregations": [
                        {"modelIntent": "grok", "totalCents": 50, "inputTokens": 3, "outputTokens": 2},
                    ],
                },
            ]
        )
        by_intent = {row["modelIntent"]: row for row in combined["aggregations"]}
        self.assertEqual(combined["totalCostCents"], 150)
        self.assertEqual(by_intent["grok"]["totalCents"], 110)
        self.assertEqual(by_intent["auto"]["totalCents"], 40)

    def test_load_group_models_uses_per_user_aggregations(self):
        from cursor_usage_menubar.models import BillingGroup, GroupMember, Session, UsageSnapshot

        session = Session(
            access_token="tok",
            sub="user",
            email="ada@example.com",
            team_id=7,
            team_name="Acme",
            plan_hint="enterprise",
        )
        snap = UsageSnapshot(
            email="ada@example.com",
            team_name="Acme",
            plan_name="Enterprise",
            spent_cents=150,
            limit_cents=1000,
            remaining_cents=850,
            percent=15,
            cycle_start="2026-08-01T00:00:00.000Z",
            cycle_end="2026-09-01T00:00:00.000Z",
            models=(),
            status=None,
            top_model=None,
            scope="group",
            group_id=9484,
            group_label="xDome-R&D",
            groups=(
                BillingGroup(
                    id=9484,
                    name="xDome-R&D",
                    spend_cents=150,
                    members=(
                        GroupMember(1, "a@x.com", "Ada", 100, 50000),
                        GroupMember(2, "b@x.com", "Bob", 50, 50000),
                    ),
                ),
            ),
        )
        seen_ids = []

        def fake_json_request(method, url, *, token=None, cookie=None, body=None):
            if url.endswith("GetAggregatedUsageEvents"):
                seen_ids.append(body.get("userId"))
                if body.get("userId") == 1:
                    return {
                        "totalCostCents": 100,
                        "aggregations": [
                            {"modelIntent": "grok", "totalCents": 100, "inputTokens": 1, "outputTokens": 1}
                        ],
                    }
                return {
                    "totalCostCents": 50,
                    "aggregations": [
                        {"modelIntent": "grok", "totalCents": 20, "inputTokens": 1, "outputTokens": 1},
                        {"modelIntent": "claude", "totalCents": 30, "inputTokens": 1, "outputTokens": 1},
                    ],
                }
            return {}

        with (
            patch("cursor_usage_menubar.client.read_session", return_value=session),
            patch("cursor_usage_menubar.client.json_request", fake_json_request),
        ):
            loaded = load_group_models(snap)
        self.assertEqual(sorted(seen_ids), [1, 2])
        self.assertEqual(loaded.breakdown_kind, "models")
        labels = {m.label: m.total_cents for m in loaded.models}
        self.assertEqual(labels.get("Grok"), 120)
        self.assertEqual(labels.get("Claude"), 30)
        self.assertNotIn("Ada", labels)

    def test_fetch_usage_self_uses_group_member(self):
        session = Session(
            access_token="tok",
            sub="user",
            email="ada@example.com",
            team_id=7,
            team_name="Acme",
            plan_hint="enterprise",
        )
        bodies = []

        def fake_json_request(method, url, *, token=None, cookie=None, body=None):
            bodies.append((url, body))
            if url.endswith("GetGroups"):
                return {
                    "groups": [
                        {
                            "id": 9485,
                            "name": "SecureAccess-R&D",
                            "spendCents": 9000,
                            "members": [
                                {
                                    "userId": 349717204,
                                    "email": "ada@example.com",
                                    "name": "Ada",
                                    "spendCents": 8515,
                                    "effectivePerUserLimitDollars": 500,
                                }
                            ],
                        }
                    ]
                }
            if "usage-summary" in url:
                return {
                    "billingCycleStart": "2026-08-01T00:00:00.000Z",
                    "billingCycleEnd": "2026-09-01T00:00:00.000Z",
                    "individualUsage": {
                        "overall": {"used": 40000, "limit": 50000, "remaining": 10000}
                    },
                }
            if url.endswith("GetAggregatedUsageEvents"):
                return {
                    "aggregations": [
                        {"modelIntent": "grok", "totalCents": 300, "inputTokens": 1, "outputTokens": 1}
                    ],
                    "totalCostCents": 300,
                }
            if url.endswith("GetFilteredUsageEvents"):
                return {"usageEvents": []}
            if url.endswith("GetPlanInfo"):
                return {"planName": "Enterprise"}
            return {}

        with (
            patch("cursor_usage_menubar.client.read_session", return_value=session),
            patch("cursor_usage_menubar.client.json_request", fake_json_request),
        ):
            snap = fetch_usage(scope="self")
        self.assertEqual(snap.spent_cents, 8515)
        self.assertEqual(snap.limit_cents, 50000)
        self.assertEqual(snap.view_label(), "Myself only")
        agg = [body for url, body in bodies if url.endswith("GetAggregatedUsageEvents")]
        self.assertEqual(agg[0]["userId"], 349717204)
        self.assertIn("startDate", agg[0])


class CycleWindowTest(unittest.TestCase):
    def test_fetch_window_starts_on_first_of_month(self):
        from datetime import datetime, timezone

        from cursor_usage_menubar.analytics import month_start_date
        from cursor_usage_menubar.client import _cycle_ms

        start_ms, _end = _cycle_ms(
            {
                "billingCycleStart": "2026-08-17T00:00:00.000Z",
                "billingCycleEnd": "2026-09-16T00:00:00.000Z",
            }
        )
        month = month_start_date()
        month_ms = int(
            datetime.combine(month, datetime.min.time(), tzinfo=timezone.utc).timestamp()
            * 1000
        )
        self.assertEqual(start_ms, month_ms)


class FilteredEventsFetchTest(unittest.TestCase):
    def test_sends_dates_as_strings_and_paginates(self):
        calls = []

        def fake_json_request(method, url, *, token=None, cookie=None, body=None):
            calls.append(body)
            page = body["page"]
            if page == 1:
                return {
                    "totalUsageEventsCount": 3,
                    "usageEventsDisplay": [
                        {
                            "timestamp": "1777680000000",
                            "chargedCents": 100,
                            "model": "composer-1",
                        },
                        {
                            "timestamp": "1777593600000",
                            "chargedCents": 200,
                            "model": "grok-4.5",
                        },
                    ],
                }
            return {
                "totalUsageEventsCount": 3,
                "usageEventsDisplay": [
                    {
                        "timestamp": "1776988800000",
                        "chargedCents": 300,
                        "model": "sonnet",
                    }
                ],
            }

        with patch("cursor_usage_menubar.client.json_request", fake_json_request):
            payload = fetch_filtered_usage_events(
                token="tok",
                base_body={"teamId": 7, "startDate": "1776988800000"},
                page_size=2,
            )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["page"], 1)
        self.assertEqual(calls[1]["page"], 2)
        self.assertIsInstance(calls[0]["startDate"], str)
        self.assertEqual(len(payload["usageEventsDisplay"]), 3)

    def test_fetch_usage_sends_string_start_date(self):
        session = Session(
            access_token="tok",
            sub="user",
            email="ada@example.com",
            team_id=7,
            team_name="Acme",
            plan_hint="enterprise",
        )
        bodies = []

        def fake_json_request(method, url, *, token=None, cookie=None, body=None):
            bodies.append((url, body))
            if url.endswith("usage-summary"):
                return {
                    "billingCycleStart": "2026-08-17T00:00:00.000Z",
                    "individualUsage": {
                        "overall": {"used": 500, "limit": 1000, "remaining": 500}
                    },
                }
            if url.endswith("GetFilteredUsageEvents"):
                return {"usageEventsDisplay": []}
            if url.endswith("GetPlanInfo"):
                return {"planName": "Enterprise"}
            return {}

        with (
            patch("cursor_usage_menubar.client.read_session", return_value=session),
            patch("cursor_usage_menubar.client.json_request", fake_json_request),
        ):
            fetch_usage()
        filtered = [
            body for url, body in bodies if url.endswith("GetFilteredUsageEvents")
        ]
        self.assertTrue(filtered)
        self.assertIsInstance(filtered[0]["startDate"], str)
        self.assertTrue(filtered[0]["startDate"].isdigit())


if __name__ == "__main__":
    unittest.main()
