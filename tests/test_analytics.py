from datetime import datetime, timezone
import unittest

from cursor_usage_menubar.analytics import (
    WEEK_MS,
    burst_member_ids,
    burst_reason,
    daily_spend_series,
    member_models,
    member_stats,
    overview_pool_cents,
    parse_events,
    recent_spend_cents,
    top_members_by_recent_spend,
    view_pool_cents,
)
from cursor_usage_menubar.models import GroupMember, ModelSpend, UsageEvent


DAY = 24 * 60 * 60 * 1000
NOW = int(datetime(2026, 8, 25, 12, tzinfo=timezone.utc).timestamp() * 1000)


class ParseEventsTest(unittest.TestCase):
    def test_reads_iso_and_millis(self):
        events = parse_events(
            {
                "usageEvents": [
                    {
                        "timestamp": "2026-08-25T12:00:00Z",
                        "chargedCents": 400,
                        "userEmail": "ada@x.com",
                        "userId": 1,
                    },
                    {
                        "timestampMs": NOW - 1000,
                        "chargedCents": 200,
                        "email": "bob@x.com",
                    },
                ]
            }
        )
        self.assertEqual(len(events), 2)
        by_email = {event.user_email: event.cents for event in events}
        self.assertEqual(by_email["ada@x.com"], 400)
        self.assertEqual(by_email["bob@x.com"], 200)

    def test_skips_events_without_time(self):
        events = parse_events({"usageEvents": [{"chargedCents": 9}]})
        self.assertEqual(events, ())

    def test_reads_token_usage(self):
        events = parse_events(
            {
                "usageEvents": [
                    {
                        "timestampMs": NOW,
                        "chargedCents": 150,
                        "userId": 1,
                        "model": "grok-4.5",
                        "tokenUsage": {"inputTokens": 12, "outputTokens": 34},
                    }
                ]
            }
        )
        self.assertEqual(events[0].input_tokens, 12)
        self.assertEqual(events[0].output_tokens, 34)
        self.assertEqual(events[0].model, "grok-4.5")

    def test_reads_owning_user_from_dashboard_events(self):
        events = parse_events(
            {
                "usageEventsDisplay": [
                    {
                        "timestamp": str(NOW),
                        "model": "composer-2",
                        "owningUser": "152683922",
                        "chargedCents": 124.73,
                        "tokenUsage": {"inputTokens": 3, "outputTokens": 20},
                    }
                ]
            }
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].user_id, 152683922)
        self.assertEqual(events[0].model, "composer-2")
        self.assertIsNone(events[0].user_email)

    def test_event_id_is_not_treated_as_user_id(self):
        events = parse_events(
            {
                "usageEvents": [
                    {
                        "timestampMs": NOW,
                        "id": 999001,
                        "owningUser": "7",
                        "chargedCents": 10,
                        "model": "grok-4.5",
                    }
                ]
            }
        )
        self.assertEqual(events[0].user_id, 7)


class DailySeriesTest(unittest.TestCase):
    def test_fills_cycle_days(self):
        events = (
            UsageEvent(at_ms=NOW - DAY, cents=100),
            UsageEvent(at_ms=NOW, cents=250),
        )
        series = daily_spend_series(
            events,
            cycle_start="2026-08-24",
            cycle_end="2026-08-26",
            now_ms=NOW,
        )
        self.assertGreaterEqual(len(series), 2)
        self.assertEqual(sum(cents for _day, cents in series), 350)

    def test_series_starts_at_first_of_month(self):
        events = (UsageEvent(at_ms=NOW, cents=250),)
        series = daily_spend_series(
            events,
            cycle_start="2026-08-17",
            cycle_end="2026-09-16",
            now_ms=NOW,
        )
        self.assertEqual(series[0][0], "2026-08-01")
        self.assertEqual(series[-1][0], "2026-08-25")
        self.assertEqual(len(series), 25)
        self.assertEqual(sum(cents for _day, cents in series), 250)

    def test_series_is_spend_per_day_not_cumulative(self):
        events = (
            UsageEvent(at_ms=NOW - 2 * DAY, cents=100),
            UsageEvent(at_ms=NOW - DAY, cents=250),
            UsageEvent(at_ms=NOW, cents=50),
        )
        series = daily_spend_series(events, now_ms=NOW)
        by_day = dict(series)
        self.assertEqual(by_day["2026-08-23"], 100)
        self.assertEqual(by_day["2026-08-24"], 250)
        self.assertEqual(by_day["2026-08-25"], 50)
        self.assertEqual(by_day["2026-08-01"], 0)


class BurstTest(unittest.TestCase):
    def test_flags_user_who_spent_a_quarter_in_one_day(self):
        ada = GroupMember(1, "ada@x.com", "Ada", 4000, 50000)
        bob = GroupMember(2, "bob@x.com", "Bob", 4000, 50000)
        events = (
            UsageEvent(NOW - 3600_000, 2000, "ada@x.com", 1),
            UsageEvent(NOW - 3 * DAY, 2000, "bob@x.com", 2),
        )
        flagged = burst_member_ids(events, (ada, bob), now_ms=NOW)
        self.assertEqual(flagged, frozenset({1}))
        self.assertIn("Spike", burst_reason(events, ada, now_ms=NOW) or "")
        self.assertIsNone(burst_reason(events, bob, now_ms=NOW))
        self.assertEqual(recent_spend_cents(events, ada, now_ms=NOW), 2000)

    def test_top_three_spenders_in_last_seven_days(self):
        ada = GroupMember(1, "ada@x.com", "Ada", 4000, 50000)
        bob = GroupMember(2, "bob@x.com", "Bob", 8000, 50000)
        cam = GroupMember(3, "cam@x.com", "Cam", 1000, 50000)
        dan = GroupMember(4, "dan@x.com", "Dan", 9000, 50000)
        events = (
            UsageEvent(NOW - DAY, 300, "ada@x.com", 1),
            UsageEvent(NOW - 2 * DAY, 900, "bob@x.com", 2),
            UsageEvent(NOW - 3 * DAY, 500, "cam@x.com", 3),
            UsageEvent(NOW - 10 * DAY, 8000, "dan@x.com", 4),
        )
        top = top_members_by_recent_spend(
            events, (ada, bob, cam, dan), now_ms=NOW, window_ms=WEEK_MS, limit=3
        )
        self.assertEqual([member.user_id for member in top], [2, 3, 1])


class MemberDetailTest(unittest.TestCase):
    def test_member_models_and_stats(self):
        ada = GroupMember(1, "ada@x.com", "Ada", 4000, 50000)
        events = (
            UsageEvent(NOW - 1000, 300, "ada@x.com", 1, "grok-4.5", 10, 20),
            UsageEvent(NOW, 700, "ada@x.com", 1, "composer-1", 5, 8),
            UsageEvent(NOW, 50, "bob@x.com", 2, "grok-4.5", 1, 1),
        )
        models = member_models(events, ada)
        self.assertEqual([model.label for model in models], ["composer-1", "grok-4.5"])
        self.assertEqual(models[0].total_cents, 700)
        self.assertEqual(models[0].request_count, 1)
        stats = member_stats(events, ada)
        self.assertEqual(stats["requests"], 2)
        self.assertEqual(stats["event_cents"], 1000)
        self.assertEqual(stats["input_tokens"], 15)
        self.assertEqual(stats["output_tokens"], 28)
        self.assertEqual(stats["top_model"], "composer-1")
        self.assertEqual(stats["first_ms"], NOW - 1000)
        self.assertEqual(stats["last_ms"], NOW)

    def test_top_three_models_by_spend(self):
        ada = GroupMember(1, "ada@x.com", "Ada", 4000, 50000)
        events = (
            UsageEvent(NOW, 100, "ada@x.com", 1, "opus", 1, 1),
            UsageEvent(NOW, 400, "ada@x.com", 1, "grok-4.5", 1, 1),
            UsageEvent(NOW, 900, "ada@x.com", 1, "composer-1", 1, 1),
            UsageEvent(NOW, 250, "ada@x.com", 1, "sonnet", 1, 1),
        )
        stats = member_stats(events, ada)
        self.assertEqual(
            [model.label for model in stats["top_models"]],
            ["composer-1", "grok-4.5", "sonnet"],
        )

    def test_top_models_match_owning_user_without_email(self):
        ada = GroupMember(7, "ada@x.com", "Ada", 4000, 50000)
        events = parse_events(
            {
                "usageEventsDisplay": [
                    {
                        "timestamp": str(NOW),
                        "model": "composer-2",
                        "owningUser": "7",
                        "chargedCents": 900,
                    },
                    {
                        "timestamp": str(NOW - 1000),
                        "model": "grok-4.5",
                        "owningUser": "7",
                        "chargedCents": 400,
                    },
                    {
                        "timestamp": str(NOW),
                        "model": "sonnet",
                        "owningUser": "8",
                        "chargedCents": 8000,
                    },
                ]
            }
        )
        stats = member_stats(events, ada)
        self.assertEqual(
            [model.label for model in stats["top_models"]],
            ["composer-2", "grok-4.5"],
        )

    def test_view_pool_falls_back_to_aggregated_models(self):
        ada = GroupMember(7, "ada@x.com", "Ada", 1000, 10000)
        models = (
            ModelSpend("composer-1", "composer-1", 700, 1, 1, 1, False),
            ModelSpend("sonnet", "sonnet", 300, 1, 1, 1, False),
        )
        self.assertEqual(view_pool_cents((), (ada,), models), (700, 300))

    def test_view_pool_prefers_matched_events(self):
        ada = GroupMember(7, "ada@x.com", "Ada", 1000, 10000)
        events = (
            UsageEvent(NOW, 100, "ada@x.com", 7, "composer-1", 1, 1),
            UsageEvent(NOW, 50, "ada@x.com", 7, "sonnet", 1, 1),
        )
        models = (
            ModelSpend("composer-1", "composer-1", 700, 1, 1, 1, False),
            ModelSpend("sonnet", "sonnet", 300, 1, 1, 1, False),
        )
        self.assertEqual(view_pool_cents(events, (ada,), models), (100, 50))

    def test_overview_pool_scales_mix_to_official_spend(self):
        ada = GroupMember(7, "ada@x.com", "Ada", 1000, 10000)
        events = (
            UsageEvent(NOW, 100, "ada@x.com", 7, "composer-1", 1, 1),
            UsageEvent(NOW, 50, "ada@x.com", 7, "sonnet", 1, 1),
        )
        models = (
            ModelSpend("composer-1", "composer-1", 700, 1, 1, 1, False),
            ModelSpend("sonnet", "sonnet", 300, 1, 1, 1, False),
        )
        self.assertEqual(
            overview_pool_cents(events, (ada,), models, spent_cents=10000),
            (7000, 3000),
        )
        self.assertEqual(
            overview_pool_cents(events, (ada,), (), spent_cents=9000),
            (6000, 3000),
        )


if __name__ == "__main__":
    unittest.main()
