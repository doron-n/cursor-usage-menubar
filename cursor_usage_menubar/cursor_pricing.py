from __future__ import annotations

import re
from dataclasses import dataclass

from cursor_usage_menubar.formatters import dollars, percent_used
from cursor_usage_menubar.models import ModelSpend, UsageSnapshot

# Composer 2.5 list rates from https://cursor.com/docs/models-and-pricing
# (Cursor Models pool, dollars per million tokens).
COMPOSER_INPUT_PER_MILLION = 0.50
COMPOSER_OUTPUT_PER_MILLION = 2.50

_COMPOSER_RE = re.compile(r"\bcomposer\b", re.IGNORECASE)
_GROK_VERSION_RE = re.compile(r"\bgrok[\s-]*4\.[56]\b", re.IGNORECASE)
_CURSOR_GROK_RE = re.compile(r"\bcursor[\s-]+grok\b", re.IGNORECASE)


@dataclass(frozen=True)
class CursorForecast:
    predicted_cents: int
    saved_cents: int
    percent: int | None
    already_cursor: bool = False


def is_cursor_pool_model(label: str, intent: str = "") -> bool:
    text = f"{label} {intent}".strip()
    if not text:
        return False
    if _COMPOSER_RE.search(text):
        return True
    if _GROK_VERSION_RE.search(text) or _CURSOR_GROK_RE.search(text):
        return True
    return False


def tokens_to_composer_cents(input_tokens: int, output_tokens: int) -> int:
    dollars_cost = (
        input_tokens * COMPOSER_INPUT_PER_MILLION
        + output_tokens * COMPOSER_OUTPUT_PER_MILLION
    ) / 1_000_000
    return int(round(dollars_cost * 100))


def billable_models(models: tuple[ModelSpend, ...]) -> tuple[ModelSpend, ...]:
    out: list[ModelSpend] = []
    for model in models:
        if model.is_auto and model.children:
            out.extend(billable_models(model.children))
        else:
            out.append(model)
    return tuple(out)


MODEL_FILTERS = ("all", "cursor", "other")


def _matches_pool(model: ModelSpend, pool: str) -> bool:
    is_cursor = is_cursor_pool_model(model.label, model.model_intent)
    if pool == "cursor":
        return is_cursor
    if pool == "other":
        return not is_cursor
    return True


def _with_children(model: ModelSpend, children: tuple[ModelSpend, ...]) -> ModelSpend:
    return ModelSpend(
        label=model.label,
        model_intent=model.model_intent,
        total_cents=sum(c.total_cents for c in children),
        input_tokens=sum(c.input_tokens for c in children),
        output_tokens=sum(c.output_tokens for c in children),
        request_count=sum(c.request_count for c in children),
        is_auto=model.is_auto,
        children=children,
    )


def filter_models(
    models: tuple[ModelSpend, ...], pool: str
) -> tuple[ModelSpend, ...]:
    if pool not in ("cursor", "other"):
        return models
    out: list[ModelSpend] = []
    for model in models:
        if model.is_auto and model.children:
            kids = tuple(c for c in model.children if _matches_pool(c, pool))
            if kids:
                out.append(_with_children(model, kids))
            continue
        if _matches_pool(model, pool):
            out.append(model)
    return tuple(out)


def apply_model_filter(snapshot: UsageSnapshot, pool: str) -> UsageSnapshot:
    from dataclasses import replace

    models = filter_models(snapshot.models, pool)
    if pool not in ("cursor", "other"):
        return snapshot
    spent = sum(m.total_cents for m in models)
    remaining = (
        None
        if snapshot.limit_cents is None
        else snapshot.limit_cents - spent
    )
    return replace(
        snapshot,
        models=models,
        spent_cents=spent,
        remaining_cents=remaining,
        percent=percent_used(spent, snapshot.limit_cents or 0),
        top_model=models[0] if models else None,
    )


def cursor_model_forecast(snapshot: UsageSnapshot) -> CursorForecast | None:
    """Spend if third-party tokens had run at Composer 2.5 list rates.

    Cursor-pool models (Grok 4.5/4.6, Composer 2.5) keep their actual cost.
    """
    if snapshot.spent_cents is None or snapshot.spent_cents < 0:
        return None
    models = billable_models(snapshot.models)
    if not models:
        return None

    cursor_cents = 0
    other_in = 0
    other_out = 0
    other_actual = 0
    for model in models:
        if is_cursor_pool_model(model.label, model.model_intent):
            cursor_cents += model.total_cents
            continue
        other_actual += model.total_cents
        other_in += model.input_tokens
        other_out += model.output_tokens

    if other_actual <= 0:
        return CursorForecast(
            predicted_cents=snapshot.spent_cents,
            saved_cents=0,
            percent=percent_used(snapshot.spent_cents, snapshot.limit_cents or 0),
            already_cursor=True,
        )

    other_predicted = tokens_to_composer_cents(other_in, other_out)
    if other_predicted <= 0:
        return None

    predicted = cursor_cents + other_predicted
    saved = max(0, snapshot.spent_cents - predicted)
    if saved <= 0:
        return None
    return CursorForecast(
        predicted_cents=predicted,
        saved_cents=saved,
        percent=percent_used(predicted, snapshot.limit_cents or 0),
    )


def forecast_menu_row(forecast: CursorForecast) -> str | None:
    if forecast.saved_cents <= 0:
        return None
    pct = f" · {forecast.percent}% of budget" if forecast.percent is not None else ""
    return (
        f"If only Cursor models: {dollars(forecast.predicted_cents)}{pct} "
        f"(would save {dollars(forecast.saved_cents)})"
    )


def forecast_card_captions(forecast: CursorForecast) -> tuple[str, str]:
    spent = dollars(forecast.predicted_cents)
    pct = (
        f"{forecast.percent}% of monthly budget"
        if forecast.percent is not None
        else "—"
    )
    title = f"If you'd used only Cursor models · {spent} · {pct}"
    if forecast.saved_cents > 0:
        sub = f"Would have saved {dollars(forecast.saved_cents)} this month"
    elif forecast.already_cursor:
        sub = "You're already on Cursor models"
    else:
        sub = "Estimated at Cursor model rates"
    return title, sub
