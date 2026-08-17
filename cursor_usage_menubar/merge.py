from __future__ import annotations

from collections import defaultdict

from cursor_usage_menubar.formatters import (
    child_label,
    is_auto_event,
    is_auto_intent,
    percent_used,
)
from cursor_usage_menubar.models import ModelSpend, Session, UsageSnapshot


def scale_auto_children(
    auto_total: int, children: list[ModelSpend]
) -> tuple[ModelSpend, ...]:
    if not children:
        return ()
    child_sum = sum(c.total_cents for c in children)
    if child_sum <= 0 or auto_total <= 0:
        return tuple(children)
    scaled: list[ModelSpend] = []
    allocated = 0
    for i, child in enumerate(children):
        if i == len(children) - 1:
            cents = auto_total - allocated
        else:
            cents = int(round(auto_total * (child.total_cents / child_sum)))
            allocated += cents
        scaled.append(
            ModelSpend(
                label=child.label,
                model_intent=child.model_intent,
                total_cents=cents,
                input_tokens=child.input_tokens,
                output_tokens=child.output_tokens,
                request_count=child.request_count,
                is_auto=False,
                children=(),
            )
        )
    return tuple(scaled)


def _nested(d: object, *keys: str) -> object:
    cur = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _auto_label(intent: str) -> str:
    return "Auto"


def _human_label(intent: str) -> str:
    if is_auto_intent(intent):
        return "Auto"
    cleaned = (intent or "").replace("-", " ").replace("_", " ").strip()
    return cleaned.title() if cleaned else "Unknown"


def _tokens(block: object) -> tuple[int, int]:
    if not isinstance(block, dict):
        return 0, 0
    inp = _as_int(block.get("inputTokens") or block.get("input_tokens")) or 0
    out = _as_int(block.get("outputTokens") or block.get("output_tokens")) or 0
    return inp, out


def merge_snapshot(
    session: Session | None,
    usage_summary: dict | None,
    period_usage: dict | None,
    aggregated: dict | None,
    filtered: dict | None,
    plan_info: dict | None,
) -> UsageSnapshot:
    usage_summary = usage_summary or {}
    period_usage = period_usage or {}
    aggregated = aggregated or {}
    filtered = filtered or {}
    plan_info = plan_info or {}

    overall = _nested(usage_summary, "individualUsage", "overall") or {}
    plan_usage = period_usage.get("planUsage") or period_usage.get("usage") or {}
    if not isinstance(overall, dict):
        overall = {}
    if not isinstance(plan_usage, dict):
        plan_usage = {}

    spent = _as_int(overall.get("used"))
    limit = _as_int(overall.get("limit"))
    remaining = _as_int(overall.get("remaining"))
    if limit is None or limit <= 0:
        spent = _as_int(plan_usage.get("used")) if spent is None else spent
        limit = _as_int(plan_usage.get("limit"))
        remaining = _as_int(plan_usage.get("remaining"))
    if spent is None:
        spent = _as_int(aggregated.get("totalCostCents"))
        remaining = None if limit is None else (limit - spent if spent is not None else None)

    pct = percent_used(spent, limit) if spent is not None and limit is not None else None
    if remaining is None and spent is not None and limit is not None:
        remaining = limit - spent

    plan_name = (
        _as_str(plan_info.get("planName") or plan_info.get("name"))
        or (session.plan_hint if session else None)
        or "Cursor"
    )
    cycle_start = _as_str(
        usage_summary.get("billingCycleStart")
        or usage_summary.get("startDate")
        or period_usage.get("startDate")
        or period_usage.get("periodStart")
    )
    cycle_end = _as_str(
        usage_summary.get("billingCycleEnd")
        or usage_summary.get("endDate")
        or period_usage.get("endDate")
        or period_usage.get("periodEnd")
    )

    children_by_label: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cents": 0, "in": 0, "out": 0, "n": 0}
    )
    for event in filtered.get("usageEvents") or filtered.get("events") or []:
        if not isinstance(event, dict):
            continue
        model_name = str(event.get("model") or "")
        if not is_auto_event(model_name):
            continue
        label = child_label(model_name)
        bucket = children_by_label[label]
        bucket["cents"] += _as_int(event.get("chargedCents")) or 0
        inp, out = _tokens(event.get("tokenUsage") or event)
        bucket["in"] += inp
        bucket["out"] += out
        bucket["n"] += 1

    raw_children = [
        ModelSpend(
            label=label,
            model_intent=label.lower(),
            total_cents=vals["cents"],
            input_tokens=vals["in"],
            output_tokens=vals["out"],
            request_count=vals["n"],
            is_auto=False,
            children=(),
        )
        for label, vals in children_by_label.items()
    ]

    models: list[ModelSpend] = []
    for row in aggregated.get("aggregations") or []:
        if not isinstance(row, dict):
            continue
        intent = str(row.get("modelIntent") or row.get("model") or "")
        cents = _as_int(row.get("totalCents")) or 0
        inp, out = _tokens(row)
        auto = is_auto_intent(intent)
        kids = scale_auto_children(cents, raw_children) if auto else ()
        models.append(
            ModelSpend(
                label=_auto_label(intent) if auto else _human_label(intent),
                model_intent=intent,
                total_cents=cents,
                input_tokens=inp,
                output_tokens=out,
                request_count=sum(k.request_count for k in kids) if kids else 0,
                is_auto=auto,
                children=kids,
            )
        )
    models.sort(key=lambda m: m.total_cents, reverse=True)
    top = models[0] if models else None

    return UsageSnapshot(
        email=session.email if session else None,
        team_name=session.team_name if session else None,
        plan_name=plan_name,
        spent_cents=spent,
        limit_cents=limit if limit and limit > 0 else None,
        remaining_cents=remaining,
        percent=pct,
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        models=tuple(models),
        status=None,
        top_model=top,
    )
