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
class GroupMember:
    user_id: int
    email: str | None = None
    name: str | None = None
    spend_cents: int = 0
    limit_cents: int | None = None


@dataclass(frozen=True)
class BillingGroup:
    id: int
    name: str | None = None
    spend_cents: int | None = None
    limit_cents: int | None = None
    members: tuple[GroupMember, ...] = ()


@dataclass(frozen=True)
class UsageEvent:
    at_ms: int
    cents: int
    user_email: str | None = None
    user_id: int | None = None
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


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
    scope: str = "team"
    group_id: int | None = None
    group_label: str | None = None
    groups: tuple[BillingGroup, ...] = ()
    breakdown_kind: str = "models"
    events: tuple[UsageEvent, ...] = ()

    def selected_members(self) -> tuple[GroupMember, ...]:
        if self.scope != "group" or self.group_id is None:
            return ()
        for group in self.groups:
            if group.id == self.group_id:
                return group.members
        return ()

    def view_label(self) -> str:
        if self.scope == "self":
            return "Myself only"
        if self.scope == "team":
            return "Global"
        if self.scope == "group" or self.group_id is not None:
            label = self.group_label or (
                str(self.group_id) if self.group_id is not None else "Group"
            )
            if (
                self.group_label
                and self.group_id is not None
                and self.group_label != str(self.group_id)
            ):
                return f"{self.group_label} ({self.group_id})"
            return label
        return "Global"

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
