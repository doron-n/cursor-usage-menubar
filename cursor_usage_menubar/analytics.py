from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cursor_usage_menubar.cursor_pricing import pool_cents
from cursor_usage_menubar.formatters import child_label
from cursor_usage_menubar.models import GroupMember, ModelSpend, UsageEvent

BURST_WINDOW_MS = 24 * 60 * 60 * 1000
FAST_WINDOW_MS = 6 * 60 * 60 * 1000
MIN_BURST_CENTS = 1500
MIN_FAST_CENTS = 800
BURST_SHARE = 0.25
FAST_SHARE = 0.15
CAP_SHARE = 0.15


def parse_events(filtered: dict | None) -> tuple[UsageEvent, ...]:
    raw = []
    if isinstance(filtered, dict):
        raw = (
            filtered.get("usageEvents")
            or filtered.get("events")
            or filtered.get("usageEventsDisplay")
            or []
        )
    if not isinstance(raw, list):
        return ()
    out: list[UsageEvent] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        at_ms = _time_ms(
            item.get("timestampMs")
            or item.get("timestamp")
            or item.get("createdAt")
            or item.get("date")
            or item.get("time")
            or item.get("eventTime")
        )
        if at_ms is None:
            continue
        cents = _as_int(item.get("chargedCents") or item.get("totalCents")) or 0
        owning = item.get("owningUser") or item.get("owning_user")
        user_id = _as_int(
            item.get("userId")
            or item.get("user_id")
            or item.get("owningUserId")
            or item.get("owning_user_id")
            or owning
        )
        email = item.get("userEmail") or item.get("email")
        if email is None and isinstance(owning, str) and "@" in owning:
            email = owning
        email_text = str(email).strip() if email else None
        tokens = item.get("tokenUsage") if isinstance(item.get("tokenUsage"), dict) else item
        inp = _as_int(tokens.get("inputTokens") or tokens.get("input_tokens")) or 0
        out_tok = _as_int(tokens.get("outputTokens") or tokens.get("output_tokens")) or 0
        out.append(
            UsageEvent(
                at_ms=at_ms,
                cents=cents,
                user_email=email_text or None,
                user_id=user_id,
                model=str(item.get("model") or item.get("modelIntent") or ""),
                input_tokens=inp,
                output_tokens=out_tok,
            )
        )
    out.sort(key=lambda event: event.at_ms)
    return tuple(out)


def month_start_date(now_ms: int | None = None):
    if now_ms is None:
        day = datetime.now(timezone.utc).date()
    else:
        day = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).date()
    return day.replace(day=1)


def daily_spend_series(
    events: tuple[UsageEvent, ...],
    *,
    cycle_start: str | None = None,
    cycle_end: str | None = None,
    now_ms: int | None = None,
) -> tuple[tuple[str, int], ...]:
    buckets: dict[str, int] = {}
    for event in events:
        day = _day_utc(event.at_ms)
        buckets[day] = buckets.get(day, 0) + event.cents
    today = None
    if now_ms is not None:
        today = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).date()
    start = month_start_date(now_ms) if now_ms is not None else _parse_day(cycle_start)
    if start is not None:
        start = start.replace(day=1)
    end = _parse_day(cycle_end)
    if today is not None:
        if end is None or end > today:
            end = today
    if not buckets and start is None:
        return ()
    if start is None:
        start = datetime.fromisoformat(min(buckets)).date().replace(day=1)
    if end is None:
        end = datetime.fromisoformat(max(buckets)).date() if buckets else start
    days = []
    cursor = start
    while cursor <= end and len(days) < 31:
        key = cursor.isoformat()
        days.append((key, buckets.get(key, 0)))
        cursor += timedelta(days=1)
    return tuple(days)


def recent_spend_cents(
    events: tuple[UsageEvent, ...],
    member: GroupMember,
    *,
    now_ms: int,
    window_ms: int = BURST_WINDOW_MS,
) -> int:
    start = now_ms - window_ms
    total = 0
    for event in events:
        if event.at_ms < start or event.at_ms > now_ms:
            continue
        if _event_matches(event, member):
            total += event.cents
    return total


def burst_member_ids(
    events: tuple[UsageEvent, ...],
    members: tuple[GroupMember, ...],
    *,
    now_ms: int,
) -> frozenset[int]:
    flagged: set[int] = set()
    for member in members:
        day = recent_spend_cents(events, member, now_ms=now_ms, window_ms=BURST_WINDOW_MS)
        fast = recent_spend_cents(events, member, now_ms=now_ms, window_ms=FAST_WINDOW_MS)
        if _is_burst(day, fast, member.spend_cents, member.limit_cents):
            flagged.add(member.user_id)
    return frozenset(flagged)


def member_events(
    events: tuple[UsageEvent, ...], member: GroupMember
) -> tuple[UsageEvent, ...]:
    return tuple(event for event in events if _event_matches(event, member))


def member_models(
    events: tuple[UsageEvent, ...], member: GroupMember
) -> tuple[ModelSpend, ...]:
    buckets: dict[str, dict[str, int]] = {}
    for event in member_events(events, member):
        label = child_label(event.model) or event.model or "Unknown"
        bucket = buckets.setdefault(
            label, {"cents": 0, "in": 0, "out": 0, "n": 0}
        )
        bucket["cents"] += event.cents
        bucket["in"] += event.input_tokens
        bucket["out"] += event.output_tokens
        bucket["n"] += 1
    models = [
        ModelSpend(
            label=label,
            model_intent=label.casefold(),
            total_cents=vals["cents"],
            input_tokens=vals["in"],
            output_tokens=vals["out"],
            request_count=vals["n"],
            is_auto=False,
        )
        for label, vals in buckets.items()
    ]
    models.sort(key=lambda model: model.total_cents, reverse=True)
    return tuple(models)


def member_stats(events: tuple[UsageEvent, ...], member: GroupMember) -> dict:
    mine = member_events(events, member)
    models = member_models(events, member)
    return {
        "requests": len(mine),
        "event_cents": sum(event.cents for event in mine),
        "input_tokens": sum(event.input_tokens for event in mine),
        "output_tokens": sum(event.output_tokens for event in mine),
        "first_ms": mine[0].at_ms if mine else None,
        "last_ms": mine[-1].at_ms if mine else None,
        "top_model": models[0].label if models else None,
        "top_models": models[:3],
        "models": models,
        "pool": pool_cents(models),
    }


def members_pool_cents(
    events: tuple[UsageEvent, ...], members: tuple[GroupMember, ...]
) -> tuple[int, int]:
    cursor = 0
    other = 0
    for member in members:
        piece = pool_cents(member_models(events, member))
        cursor += piece[0]
        other += piece[1]
    return cursor, other


def view_pool_cents(
    events: tuple[UsageEvent, ...],
    members: tuple[GroupMember, ...],
    models: tuple[ModelSpend, ...] = (),
) -> tuple[int, int]:
    from_events = members_pool_cents(events, members)
    if from_events[0] or from_events[1]:
        return from_events
    return pool_cents(models)


def burst_reason(
    events: tuple[UsageEvent, ...],
    member: GroupMember,
    *,
    now_ms: int,
) -> str | None:
    day = recent_spend_cents(events, member, now_ms=now_ms, window_ms=BURST_WINDOW_MS)
    fast = recent_spend_cents(events, member, now_ms=now_ms, window_ms=FAST_WINDOW_MS)
    if not _is_burst(day, fast, member.spend_cents, member.limit_cents):
        return None
    if fast >= MIN_FAST_CENTS and (
        member.spend_cents <= 0 or fast >= member.spend_cents * FAST_SHARE
    ):
        return f"Spike · ${fast / 100:.2f} in 6h"
    return f"Spike · ${day / 100:.2f} in 24h"


def _is_burst(day: int, fast: int, total: int, cap: int | None) -> bool:
    if day >= MIN_BURST_CENTS and total > 0 and day >= total * BURST_SHARE:
        return True
    if cap and cap > 0 and day >= MIN_BURST_CENTS and day >= cap * CAP_SHARE:
        return True
    if fast >= MIN_FAST_CENTS and total > 0 and fast >= total * FAST_SHARE:
        return True
    return False


def _event_matches(event: UsageEvent, member: GroupMember) -> bool:
    if event.user_id is not None and event.user_id == member.user_id:
        return True
    if event.user_email and member.email:
        return event.user_email.casefold() == member.email.casefold()
    return False


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _time_ms(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        if number < 10_000_000_000:
            return number * 1000
        return number
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _time_ms(int(text))
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def _day_utc(at_ms: int) -> str:
    return datetime.fromtimestamp(at_ms / 1000, tz=timezone.utc).date().isoformat()


def _parse_day(value: str | None):
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None
