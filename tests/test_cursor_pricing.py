import unittest

from cursor_usage_menubar.cursor_pricing import (
    apply_model_filter,
    billable_models,
    cursor_model_forecast,
    filter_models,
    forecast_card_captions,
    forecast_menu_row,
    is_cursor_pool_model,
    tokens_to_composer_cents,
)
from cursor_usage_menubar.models import ModelSpend, UsageSnapshot


def _snap(models, spent, limit=10000, percent=None) -> UsageSnapshot:
    return UsageSnapshot(
        email="a@b.c",
        team_name="Acme",
        plan_name="Enterprise",
        spent_cents=spent,
        limit_cents=limit,
        remaining_cents=(limit - spent) if limit else None,
        percent=percent,
        cycle_start=None,
        cycle_end=None,
        models=models,
        status=None,
        top_model=models[0] if models else None,
    )


class CursorPoolMatchTest(unittest.TestCase):
    def test_cursor_pool_labels(self):
        self.assertTrue(is_cursor_pool_model("Cursor Grok 4.5 High Fast"))
        self.assertTrue(is_cursor_pool_model("Grok 4.6", "grok-4.6"))
        self.assertTrue(is_cursor_pool_model("Composer 2.5 Fast"))
        self.assertTrue(is_cursor_pool_model("composer-2.5"))

    def test_third_party_labels(self):
        self.assertFalse(is_cursor_pool_model("Claude 4.6 Sonnet"))
        self.assertFalse(is_cursor_pool_model("GPT-5.4", "gpt-5.4"))
        self.assertFalse(is_cursor_pool_model("Gemini 3 Pro"))
        self.assertFalse(is_cursor_pool_model("Auto", "auto-smart"))


class ComposerRateTest(unittest.TestCase):
    def test_one_million_in_and_out(self):
        self.assertEqual(tokens_to_composer_cents(1_000_000, 1_000_000), 300)

    def test_typical_claude_shaped_tokens(self):
        self.assertEqual(tokens_to_composer_cents(1_000_000, 200_000), 100)


class ForecastTest(unittest.TestCase):
    def test_reprices_claude_keeps_grok(self):
        grok = ModelSpend("Cursor Grok 4.5", "grok-4.5", 500, 100_000, 10_000, 5, False)
        claude = ModelSpend(
            "Claude 4.6 Sonnet", "claude-4.6-sonnet", 1800, 1_000_000, 200_000, 10, False
        )
        forecast = cursor_model_forecast(_snap((grok, claude), spent=2300, percent=23))
        self.assertIsNotNone(forecast)
        self.assertEqual(forecast.predicted_cents, 600)
        self.assertEqual(forecast.saved_cents, 1700)
        self.assertEqual(forecast.percent, 6)
        self.assertFalse(forecast.already_cursor)

    def test_auto_children_not_double_counted(self):
        claude = ModelSpend(
            "Claude 4.6 Sonnet", "claude-4.6-sonnet", 1800, 1_000_000, 200_000, 8, False
        )
        grok = ModelSpend("Grok 4.5", "grok-4.5", 500, 80_000, 8_000, 2, False)
        auto = ModelSpend("Auto", "auto-smart", 2300, 1_080_000, 208_000, 10, True, (claude, grok))
        self.assertEqual(len(billable_models((auto,))), 2)
        forecast = cursor_model_forecast(_snap((auto,), spent=2300, percent=23))
        self.assertEqual(forecast.predicted_cents, 600)
        self.assertEqual(forecast.saved_cents, 1700)

    def test_already_cursor_models_is_zero_savings(self):
        grok = ModelSpend("Composer 2.5", "composer-2.5", 800, 1_000_000, 100_000, 4, False)
        forecast = cursor_model_forecast(_snap((grok,), spent=800))
        self.assertIsNotNone(forecast)
        self.assertTrue(forecast.already_cursor)
        self.assertEqual(forecast.saved_cents, 0)
        self.assertEqual(forecast.predicted_cents, 800)

    def test_none_without_usable_tokens(self):
        claude = ModelSpend("Claude 4.6 Sonnet", "claude-4.6-sonnet", 1800, 1, 1, 10, False)
        self.assertIsNone(cursor_model_forecast(_snap((claude,), spent=1800)))

    def test_none_without_models_or_spend(self):
        self.assertIsNone(cursor_model_forecast(_snap((), spent=100)))
        self.assertIsNone(cursor_model_forecast(UsageSnapshot.empty("signed out")))

    def test_menu_row(self):
        grok = ModelSpend("Cursor Grok 4.5", "grok-4.5", 500, 100_000, 10_000, 5, False)
        claude = ModelSpend(
            "Claude 4.6 Sonnet", "claude-4.6-sonnet", 1800, 1_000_000, 200_000, 10, False
        )
        row = forecast_menu_row(cursor_model_forecast(_snap((grok, claude), spent=2300)))
        self.assertEqual(row, "If only Cursor models: $6.00 · 6% of budget (would save $17.00)")
        title, sub = forecast_card_captions(
            cursor_model_forecast(_snap((grok, claude), spent=2300))
        )
        self.assertEqual(
            title, "If you'd used only Cursor models · $6.00 · 6% of monthly budget"
        )
        self.assertEqual(sub, "Would have saved $17.00 this month")
        self.assertIsNone(
            forecast_menu_row(cursor_model_forecast(_snap(
                (ModelSpend("Composer 2.5", "composer-2.5", 800, 1, 1, 1, False),),
                spent=800,
            )))
        )


class ModelFilterTest(unittest.TestCase):
    def test_splits_cursor_and_other_and_keeps_matching_auto_children(self):
        grok = ModelSpend("Cursor Grok 4.5", "grok-4.5", 500, 100_000, 10_000, 5, False)
        claude = ModelSpend(
            "Claude 4.6 Sonnet", "claude-4.6-sonnet", 1800, 1_000_000, 200_000, 10, False
        )
        auto = ModelSpend(
            "Auto", "auto-smart", 2300, 1_100_000, 210_000, 15, True, (grok, claude)
        )
        cursor = filter_models((auto,), "cursor")
        other = filter_models((auto,), "other")
        self.assertEqual([m.label for m in cursor], ["Auto"])
        self.assertEqual([c.label for c in cursor[0].children], ["Cursor Grok 4.5"])
        self.assertEqual(cursor[0].total_cents, 500)
        self.assertEqual([m.label for m in other], ["Auto"])
        self.assertEqual([c.label for c in other[0].children], ["Claude 4.6 Sonnet"])
        self.assertEqual(other[0].total_cents, 1800)
        self.assertEqual(filter_models((auto,), "all"), (auto,))

    def test_apply_model_filter_keeps_budget_recomputes_spend(self):
        grok = ModelSpend("Composer 2.5", "composer-2.5", 400, 10, 4, 2, False)
        claude = ModelSpend("Claude 4.6 Sonnet", "claude-4.6-sonnet", 600, 10, 4, 3, False)
        snap = _snap((grok, claude), spent=1000, limit=5000, percent=20)
        filtered = apply_model_filter(snap, "cursor")
        self.assertEqual(filtered.limit_cents, 5000)
        self.assertEqual(filtered.spent_cents, 400)
        self.assertEqual(filtered.remaining_cents, 4600)
        self.assertEqual(filtered.percent, 8)
        self.assertEqual([m.label for m in filtered.models], ["Composer 2.5"])
        self.assertIs(apply_model_filter(snap, "all"), snap)


if __name__ == "__main__":
    unittest.main()
