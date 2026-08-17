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

    def test_period_wins_wholesale_when_summary_limit_invalid(self):
        snap = merge_snapshot(
            session=_session(),
            usage_summary={
                "individualUsage": {"overall": {"used": 99999, "limit": 0, "remaining": 0}}
            },
            period_usage={
                "planUsage": {"used": 1200, "limit": 4000, "remaining": 2800},
            },
            aggregated=None,
            filtered=None,
            plan_info=None,
        )
        self.assertEqual(snap.spent_cents, 1200)
        self.assertEqual(snap.limit_cents, 4000)
        self.assertEqual(snap.remaining_cents, 2800)
        self.assertEqual(snap.percent, 30)

    def test_auto_with_zero_total_has_no_children(self):
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
        ]
        self.assertEqual(scale_auto_children(0, children), ())

        snap = merge_snapshot(
            session=_session(),
            usage_summary={
                "individualUsage": {"overall": {"used": 100, "limit": 200, "remaining": 100}}
            },
            period_usage=None,
            aggregated={
                "aggregations": [
                    {"modelIntent": "auto-smart", "totalCents": 0, "inputTokens": 0, "outputTokens": 0}
                ],
            },
            filtered={
                "usageEvents": [
                    {
                        "model": "Cursor Grok 4.5 (Auto Balanced)",
                        "chargedCents": 50,
                        "tokenUsage": {},
                    },
                ]
            },
            plan_info=None,
        )
        auto = snap.models[0]
        self.assertTrue(auto.is_auto)
        self.assertEqual(auto.total_cents, 0)
        self.assertEqual(auto.children, ())

    def test_many_child_rounding_no_negatives_and_sums_to_total(self):
        children = [
            ModelSpend(
                label=f"Model {i}",
                model_intent=f"m{i}",
                total_cents=1,
                input_tokens=0,
                output_tokens=0,
                request_count=1,
                is_auto=False,
                children=(),
            )
            for i in range(6)
        ]
        scaled = scale_auto_children(4, children)
        self.assertEqual(len(scaled), 6)
        self.assertEqual(sum(c.total_cents for c in scaled), 4)
        for child in scaled:
            self.assertGreaterEqual(child.total_cents, 0)

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

    def test_usage_events_display_key_becomes_children(self):
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
                "totalUsageEventsCount": 2,
                "usageEventsDisplay": [
                    {
                        "model": "Cursor Grok 4.5 (Auto Balanced)",
                        "chargedCents": 750,
                        "tokenUsage": {"inputTokens": 4, "outputTokens": 1},
                    },
                    {
                        "model": "Cursor Grok 4.5 (Auto Balanced)",
                        "chargedCents": 250,
                        "tokenUsage": {"inputTokens": 4, "outputTokens": 1},
                    },
                ],
            },
            plan_info=None,
        )
        auto = snap.models[0]
        self.assertTrue(auto.is_auto)
        self.assertEqual(len(auto.children), 1)
        self.assertEqual(auto.children[0].label, "Grok 4.5")
        self.assertEqual(auto.children[0].total_cents, 1000)
        self.assertEqual(auto.children[0].request_count, 2)

    def test_auto_smart_and_default_fold_into_single_auto_row(self):
        snap = merge_snapshot(
            session=_session(),
            usage_summary={
                "individualUsage": {"overall": {"used": 1000, "limit": 2000, "remaining": 1000}}
            },
            period_usage=None,
            aggregated={
                "aggregations": [
                    {
                        "modelIntent": "auto-smart",
                        "totalCents": 600,
                        "inputTokens": 6,
                        "outputTokens": 3,
                    },
                    {
                        "modelIntent": "default",
                        "totalCents": 400,
                        "inputTokens": 4,
                        "outputTokens": 2,
                    },
                ],
            },
            filtered={
                "usageEvents": [
                    {
                        "model": "Cursor Grok 4.5 (Auto Balanced)",
                        "chargedCents": 750,
                        "tokenUsage": {"inputTokens": 4, "outputTokens": 1},
                    },
                    {
                        "model": "GPT-5.6 Sol (default)",
                        "chargedCents": 250,
                        "tokenUsage": {"inputTokens": 1, "outputTokens": 1},
                    },
                ]
            },
            plan_info=None,
        )
        auto_rows = [m for m in snap.models if m.is_auto]
        self.assertEqual(len(auto_rows), 1)
        auto = auto_rows[0]
        self.assertEqual(auto.label, "Auto")
        self.assertEqual(auto.total_cents, 1000)
        self.assertEqual(auto.input_tokens, 10)
        self.assertEqual(auto.output_tokens, 5)
        # Both auto-smart and default events feed the same children pool,
        # each child counted once, summing back to the combined Auto total.
        self.assertEqual(sum(c.total_cents for c in auto.children), 1000)
        labels = sorted(c.label for c in auto.children)
        self.assertEqual(labels, ["GPT-5.6 Sol", "Grok 4.5"])


if __name__ == "__main__":
    unittest.main()
