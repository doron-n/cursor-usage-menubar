from __future__ import annotations

import unittest

from cursor_usage_menubar.merge import merge_snapshot, scale_auto_children
from cursor_usage_menubar.models import ModelSpend, Session


def _session() -> Session:
    return Session(
        access_token="t",
        sub="u",
        email="ada@example.com",
        team_id=42,
        team_name="Acme",
        plan_hint="enterprise",
    )


class MergeTest(unittest.TestCase):
    def test_usage_summary_overall_wins_when_limit_positive(self):
        snap = merge_snapshot(
            session=_session(),
            usage_summary={
                "individualUsage": {
                    "overall": {"used": 23734, "limit": 50000, "remaining": 26266}
                },
                "billingCycleStart": "2026-08-01",
                "billingCycleEnd": "2026-08-31",
            },
            period_usage={"planUsage": {"used": 1, "limit": 2}},
            aggregated={
                "totalCostCents": 999,
                "aggregations": [
                    {
                        "modelIntent": "auto-smart",
                        "totalCents": 10000,
                        "inputTokens": 10,
                        "outputTokens": 5,
                    }
                ],
            },
            filtered={"usageEvents": []},
            plan_info={"planName": "Enterprise"},
        )
        self.assertEqual(snap.spent_cents, 23734)
        self.assertEqual(snap.limit_cents, 50000)
        self.assertEqual(snap.remaining_cents, 26266)
        self.assertEqual(snap.percent, 47)
        self.assertEqual(snap.plan_name, "Enterprise")
        self.assertEqual(snap.email, "ada@example.com")
        self.assertEqual(snap.team_name, "Acme")
        self.assertEqual(snap.cycle_start, "2026-08-01")
        self.assertIsNotNone(snap.top_model)
        self.assertEqual(snap.top_model.label, "Auto")

    def test_falls_back_to_period_usage_without_summary_limit(self):
        snap = merge_snapshot(
            session=_session(),
            usage_summary={},
            period_usage={
                "planUsage": {"used": 1200, "limit": 4000, "remaining": 2800},
                "startDate": "2026-08-01",
                "endDate": "2026-08-31",
            },
            aggregated=None,
            filtered=None,
            plan_info=None,
        )
        self.assertEqual(snap.spent_cents, 1200)
        self.assertEqual(snap.limit_cents, 4000)
        self.assertEqual(snap.percent, 30)
        self.assertEqual(snap.plan_name, "enterprise")

    def test_auto_children_scale_to_auto_total(self):
        children = [
            ModelSpend(
                label="Grok 4.5",
                model_intent="grok",
                total_cents=80,
                input_tokens=1,
                output_tokens=1,
                request_count=2,
                is_auto=False,
                children=(),
            ),
            ModelSpend(
                label="Opus 5",
                model_intent="opus",
                total_cents=20,
                input_tokens=1,
                output_tokens=1,
                request_count=1,
                is_auto=False,
                children=(),
            ),
        ]
        scaled = scale_auto_children(1000, children)
        self.assertEqual(sum(c.total_cents for c in scaled), 1000)
        self.assertEqual(scaled[0].total_cents, 800)
        self.assertEqual(scaled[1].total_cents, 200)

    def test_filtered_auto_events_become_children(self):
        snap = merge_snapshot(
            session=_session(),
            usage_summary={
                "individualUsage": {"overall": {"used": 1000, "limit": 2000, "remaining": 1000}}
            },
            period_usage=None,
            aggregated={
                "totalCostCents": 1000,
                "aggregations": [
                    {"modelIntent": "auto-smart", "totalCents": 1000, "inputTokens": 8, "outputTokens": 2}
                ],
            },
            filtered={
                "usageEvents": [
                    {
                        "model": "Cursor Grok 4.5 (Auto Balanced)",
                        "chargedCents": 75,
                        "tokenUsage": {"inputTokens": 4, "outputTokens": 1},
                    },
                    {
                        "model": "Cursor Grok 4.5 (Auto Balanced)",
                        "chargedCents": 25,
                        "tokenUsage": {"inputTokens": 4, "outputTokens": 1},
                    },
                    {
                        "model": "GPT-5.6 Sol",
                        "chargedCents": 9999,
                        "tokenUsage": {},
                    },
                ]
            },
            plan_info=None,
        )
        auto = snap.models[0]
        self.assertTrue(auto.is_auto)
        self.assertEqual(len(auto.children), 1)
        self.assertEqual(auto.children[0].label, "Grok 4.5")
        self.assertEqual(auto.children[0].total_cents, 1000)
        self.assertEqual(auto.children[0].request_count, 2)


if __name__ == "__main__":
    unittest.main()
