from __future__ import annotations

import re

_AUTO_INTENTS = frozenset({"auto", "auto-smart", "default", "composer-auto"})
_AUTO_EVENT_RE = re.compile(r"\(auto|\bdefault\b", re.IGNORECASE)
_CURSOR_PREFIX_RE = re.compile(r"^Cursor\s+", re.IGNORECASE)
_AUTO_SUFFIX_RE = re.compile(r"\s*\((?:Auto|Default)[^)]*\)\s*$", re.IGNORECASE)


def dollars(cents: int) -> str:
    return f"${cents / 100.0:.2f}"


def percent_used(used: int, limit: int) -> int | None:
    if limit <= 0:
        return None
    return int((used / limit) * 100)


def menu_title(spent_cents: int | None, percent: int | None) -> str:
    if spent_cents is None or percent is None:
        return "Cursor · —"
    return f"Cursor · {dollars(spent_cents)} · {percent}%"


def is_auto_event(model_name: str) -> bool:
    return bool(_AUTO_EVENT_RE.search(model_name or ""))


def is_auto_intent(model_intent: str) -> bool:
    mi = (model_intent or "").strip().lower()
    return mi in _AUTO_INTENTS or "auto" in mi


def child_label(model_name: str) -> str:
    label = _AUTO_SUFFIX_RE.sub("", model_name or "").strip()
    label = _CURSOR_PREFIX_RE.sub("", label).strip()
    return label or model_name
