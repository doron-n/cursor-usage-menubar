from __future__ import annotations

from cursor_usage_menubar.client import fetch_usage
from cursor_usage_menubar.formatters import dollars
from cursor_usage_menubar.models import UsageSnapshot


def redact(email: str | None) -> str:
    if not email or "@" not in email:
        return "—"
    name, domain = email.split("@", 1)
    return f"{name[:1]}***@{domain}"


def render(snapshot: UsageSnapshot) -> str:
    lines = [
        f"account: {redact(snapshot.email)}",
        f"team: {snapshot.team_name or '—'}",
        f"plan: {snapshot.plan_name}",
        f"spent: {dollars(snapshot.spent_cents) if snapshot.spent_cents is not None else '—'}",
        f"limit: {dollars(snapshot.limit_cents) if snapshot.limit_cents is not None else '—'}",
        f"percent: {snapshot.percent if snapshot.percent is not None else '—'}",
        f"cycle: {snapshot.cycle_start or '—'} → {snapshot.cycle_end or '—'}",
        f"status: {snapshot.status or 'ok'}",
        "models:",
    ]
    for model in snapshot.models:
        lines.append(f"  - {model.label}: {dollars(model.total_cents)}")
        for child in model.children:
            lines.append(f"      {child.label}: {dollars(child.total_cents)} ({child.request_count} req)")
    return "\n".join(lines)


def main() -> None:
    print(render(fetch_usage()))


if __name__ == "__main__":
    main()
