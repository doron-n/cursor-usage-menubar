from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    access_token: str
    sub: str
    email: str | None = None
    team_id: int | None = None
    team_name: str | None = None
    plan_hint: str | None = None


@dataclass(frozen=True)
class ModelSpend:
    label: str
    model_intent: str
    total_cents: int
    input_tokens: int
    output_tokens: int
    request_count: int
    is_auto: bool
    children: tuple["ModelSpend", ...] = ()


@dataclass(frozen=True)
class UsageSnapshot:
    email: str | None
    team_name: str | None
    plan_name: str
    spent_cents: int | None
    limit_cents: int | None
    remaining_cents: int | None
    percent: int | None
    cycle_start: str | None
    cycle_end: str | None
    models: tuple[ModelSpend, ...]
    status: str | None
    top_model: ModelSpend | None

    @staticmethod
    def empty(status: str) -> "UsageSnapshot":
        return UsageSnapshot(
            email=None,
            team_name=None,
            plan_name="Cursor",
            spent_cents=None,
            limit_cents=None,
            remaining_cents=None,
            percent=None,
            cycle_start=None,
            cycle_end=None,
            models=(),
            status=status,
            top_model=None,
        )
