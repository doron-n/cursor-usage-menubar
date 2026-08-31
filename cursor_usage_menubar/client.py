from __future__ import annotations

import http.client
import json
import ssl
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone

import certifi

from cursor_usage_menubar.analytics import (
    events_for_members,
    member_events,
    month_start_date,
    parse_events,
)
from cursor_usage_menubar.auth import read_session, session_cookie
from cursor_usage_menubar.merge import aggregations_from_filtered, merge_snapshot
from cursor_usage_menubar.models import (
    BillingGroup,
    GroupMember,
    Session,
    UsageEvent,
    UsageSnapshot,
)
from cursor_usage_menubar.roles import (
    NO_ADMIN_STATUS,
    extract_role,
    is_admin_role,
    member_role_for_email,
)

USAGE_SUMMARY_URL = "https://cursor.com/api/usage-summary"
API2 = "https://api2.cursor.sh/aiserver.v1.DashboardService"
DASHBOARD = "https://cursor.com/api/dashboard"
_TIMEOUT = 8
_DASHBOARD_PATHS = {
    "GetAggregatedUsageEvents": "get-aggregated-usage-events",
    "GetFilteredUsageEvents": "get-filtered-usage-events",
    "GetCurrentPeriodUsage": "get-current-period-usage",
    "GetPlanInfo": "get-plan-info",
    "GetGroups": "get-team-groups",
    "GetTeamMembers": "get-team-members",
    "GetMe": "get-me",
}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never follow redirects, so a redirect can't be used to smuggle the
    Cookie/Authorization headers we set to a different host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_OPENER = urllib.request.build_opener(
    _NoRedirectHandler, urllib.request.HTTPSHandler(context=_SSL_CONTEXT)
)


def json_request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    cookie: str | None = None,
    body: dict | None = None,
) -> dict | None:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Connect-Protocol-Version", "1")
    if cookie:
        req.add_header("Cookie", cookie)
    if "cursor.com" in url:
        req.add_header("Origin", "https://cursor.com")
        req.add_header("Referer", "https://cursor.com/dashboard?tab=usage")
    try:
        with _OPENER.open(req, timeout=_TIMEOUT) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        return None
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        # json.JSONDecodeError is a ValueError; bytes.decode() inside
        # json.loads can also raise UnicodeDecodeError (also a ValueError)
        # if the body isn't valid UTF-8.
        return None
    return parsed if isinstance(parsed, dict) else None


def dashboard_request(
    method_name: str,
    *,
    token: str,
    cookie: str | None = None,
    body: dict | None = None,
) -> dict | None:
    payload = json_request(
        "POST", f"{API2}/{method_name}", token=token, body=body
    )
    if isinstance(payload, dict):
        return payload
    path = _DASHBOARD_PATHS.get(method_name)
    if not path or not cookie:
        return payload
    return json_request(
        "POST", f"{DASHBOARD}/{path}", cookie=cookie, body=body
    )


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _dollars_to_cents(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def _cycle_ms(summary: dict | None) -> tuple[int | None, int | None]:
    if not isinstance(summary, dict):
        return None, None
    start = summary.get("billingCycleStart") or summary.get("startDate")
    end = summary.get("billingCycleEnd") or summary.get("endDate")

    def _ms(value: object) -> int | None:
        if not value:
            return None
        text = str(value)
        if text.isdigit():
            return int(text)
        try:
            return int(
                datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000
            )
        except ValueError:
            return None

    start_ms, end_ms = _ms(start), _ms(end)
    month_ms = int(
        datetime.combine(
            month_start_date(), datetime.min.time(), tzinfo=timezone.utc
        ).timestamp()
        * 1000
    )
    if start_ms is None or start_ms > month_ms:
        start_ms = month_ms
    return start_ms, end_ms


def _date_fields(start_ms: int | None, end_ms: int | None) -> dict:
    body: dict = {}
    if start_ms is not None:
        body["startDate"] = str(int(start_ms))
    if end_ms is not None:
        body["endDate"] = str(int(end_ms))
    return body


def _event_rows(payload: dict | None) -> list:
    if not isinstance(payload, dict):
        return []
    raw = (
        payload.get("usageEventsDisplay")
        or payload.get("usageEvents")
        or payload.get("events")
        or []
    )
    return raw if isinstance(raw, list) else []


EVENT_PAGE_SIZE = 1000
EVENT_MAX_PAGES = 20


def fetch_filtered_usage_events(
    *,
    token: str,
    base_body: dict,
    page_size: int = EVENT_PAGE_SIZE,
    max_pages: int = EVENT_MAX_PAGES,
    cookie: str | None = None,
) -> dict:
    first = dashboard_request(
        "GetFilteredUsageEvents",
        token=token,
        cookie=cookie,
        body={**base_body, "page": 1, "pageSize": page_size},
    )
    if not isinstance(first, dict):
        return {"usageEventsDisplay": []}
    rows = list(_event_rows(first))
    total = _as_int(first.get("totalUsageEventsCount")) or 0
    if total > 0:
        num_pages = min(max_pages, max(1, (total + page_size - 1) // page_size))
    elif len(rows) >= page_size:
        num_pages = max_pages
    else:
        num_pages = 1

    extra: dict[int, dict | None] = {}
    if num_pages > 1:

        def _page(page: int) -> dict | None:
            return dashboard_request(
                "GetFilteredUsageEvents",
                token=token,
                cookie=cookie,
                body={**base_body, "page": page, "pageSize": page_size},
            )

        if total > 0:
            workers = min(8, num_pages - 1)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_page, page): page for page in range(2, num_pages + 1)}
                for future in as_completed(futures):
                    extra[futures[future]] = future.result()
        else:
            for page in range(2, num_pages + 1):
                payload = _page(page)
                extra[page] = payload
                chunk = _event_rows(payload)
                if not chunk or len(chunk) < page_size:
                    break

    for page in range(2, num_pages + 1):
        rows.extend(_event_rows(extra.get(page)))

    out = dict(first)
    if "usageEvents" in first:
        out["usageEvents"] = rows
    elif "events" in first:
        out["events"] = rows
    else:
        out["usageEventsDisplay"] = rows
    out["totalUsageEventsCount"] = total or len(rows)
    return out


def load_member_events(
    member: GroupMember, snapshot: UsageSnapshot
) -> tuple[UsageEvent, ...]:
    """Team-wide fetches keep only the newest pages. Load this user's events
    when that window missed them, so per-user models are not empty."""
    cached = member_events(snapshot.events, member)
    if cached:
        return cached
    session = read_session()
    if session is None:
        return ()
    cookie = session_cookie(session.sub, session.access_token)
    start_ms, end_ms = _cycle_ms(
        {
            "billingCycleStart": snapshot.cycle_start,
            "billingCycleEnd": snapshot.cycle_end,
        }
    )
    body: dict = {"userId": member.user_id}
    if session.team_id is not None:
        body["teamId"] = session.team_id
    body.update(_date_fields(start_ms, end_ms))
    payload = fetch_filtered_usage_events(
        token=session.access_token, cookie=cookie, base_body=body
    )
    parsed = parse_events(payload)
    return member_events(parsed, member) or parsed


def _parse_members(raw: object) -> tuple[GroupMember, ...]:
    if not isinstance(raw, list):
        return ()
    members: list[GroupMember] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        user_id = _as_int(item.get("userId") or item.get("id") or item.get("user_id"))
        if user_id is None:
            continue
        email = item.get("email") or item.get("userEmail")
        name = item.get("name") or item.get("displayName")
        spend = _as_int(item.get("spendCents") or item.get("overallSpendCents")) or 0
        limit = _dollars_to_cents(
            item.get("effectivePerUserLimitDollars") or item.get("monthlyLimitDollars")
        )
        members.append(
            GroupMember(
                user_id=user_id,
                email=str(email) if email else None,
                name=str(name) if name else None,
                spend_cents=spend,
                limit_cents=limit,
            )
        )
    return tuple(members)


def parse_groups(payload: dict | None) -> tuple[BillingGroup, ...]:
    if not isinstance(payload, dict):
        return ()
    raw = (
        payload.get("groups")
        or payload.get("billingGroups")
        or payload.get("teamGroups")
        or payload.get("data")
        or []
    )
    if isinstance(raw, dict):
        raw = raw.get("groups") or raw.get("items") or []
    if not isinstance(raw, list):
        return ()
    groups: list[BillingGroup] = []
    seen: set[int] = set()

    def _add(item: dict, members_override: object | None = None) -> None:
        gid = item.get("id") if item.get("id") is not None else (
            item.get("groupId") or item.get("group_id")
        )
        gid_int = _as_int(gid)
        if gid_int is None or gid_int in seen:
            return
        seen.add(gid_int)
        name = item.get("name") or item.get("groupName") or item.get("displayName")
        members = _parse_members(
            members_override if members_override is not None else item.get("members")
        )
        spend = _as_int(item.get("spendCents"))
        if spend is None and members:
            spend = sum(m.spend_cents for m in members)
        limit = sum(m.limit_cents or 0 for m in members) or None
        groups.append(
            BillingGroup(
                id=gid_int,
                name=str(name) if name else None,
                spend_cents=spend,
                limit_cents=limit,
                members=members,
            )
        )

    for item in raw:
        if isinstance(item, dict):
            _add(item)
    unassigned = payload.get("unassignedGroup")
    if isinstance(unassigned, dict):
        _add(unassigned, payload.get("unassignedMembers") or unassigned.get("members"))
    return tuple(groups)


def list_groups(*, token: str, cookie: str, team_id: int | None) -> tuple[BillingGroup, ...]:
    team_body: dict = {}
    if team_id is not None:
        team_body["teamId"] = team_id
    payload = dashboard_request(
        "GetGroups", token=token, cookie=cookie, body=team_body
    )
    return parse_groups(payload)


def find_group_member(
    groups: tuple[BillingGroup, ...], email: str | None
) -> GroupMember | None:
    if not email:
        return None
    want = email.casefold()
    for group in groups:
        for member in group.members:
            if member.email and member.email.casefold() == want:
                return member
    return None


def combine_aggregations(payloads: list[dict | None]) -> dict:
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cents": 0, "in": 0, "out": 0}
    )
    total = 0
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        cost = _as_int(payload.get("totalCostCents"))
        if cost is not None:
            total += cost
        for row in payload.get("aggregations") or []:
            if not isinstance(row, dict):
                continue
            intent = str(row.get("modelIntent") or row.get("model") or "unknown")
            buckets[intent]["cents"] += _as_int(row.get("totalCents")) or 0
            buckets[intent]["in"] += _as_int(row.get("inputTokens")) or 0
            buckets[intent]["out"] += _as_int(row.get("outputTokens")) or 0
    return {
        "totalCostCents": total,
        "aggregations": [
            {
                "modelIntent": intent,
                "totalCents": vals["cents"],
                "inputTokens": vals["in"],
                "outputTokens": vals["out"],
            }
            for intent, vals in buckets.items()
        ],
    }


def fetch_group_model_aggregations(
    *,
    token: str,
    team_id: int | None,
    start_ms: int | None,
    end_ms: int | None,
    user_ids: list[int],
    cookie: str | None = None,
) -> dict:
    if not user_ids:
        return {"aggregations": [], "totalCostCents": 0}

    def _one(user_id: int) -> dict | None:
        body: dict = {"userId": user_id}
        if team_id is not None:
            body["teamId"] = team_id
        if start_ms is not None:
            body["startDate"] = str(int(start_ms))
        if end_ms is not None:
            body["endDate"] = str(int(end_ms))
        return dashboard_request(
            "GetAggregatedUsageEvents", token=token, cookie=cookie, body=body
        )

    payloads: list[dict | None] = []
    workers = min(8, len(user_ids))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, uid) for uid in user_ids]
        for future in as_completed(futures):
            try:
                payloads.append(future.result())
            except Exception:
                payloads.append(None)
    return combine_aggregations(payloads)


def load_group_models(snapshot: UsageSnapshot) -> UsageSnapshot:
    """Fill snapshot.models with group-wide model spend (not per-user rows)."""
    members = snapshot.selected_members()
    user_ids = [m.user_id for m in members if m.spend_cents > 0]
    if not user_ids:
        user_ids = [m.user_id for m in members]
    session = read_session()
    if session is None:
        return snapshot
    start_ms, end_ms = _cycle_ms(
        {
            "billingCycleStart": snapshot.cycle_start,
            "billingCycleEnd": snapshot.cycle_end,
        }
    )
    aggregated = fetch_group_model_aggregations(
        token=session.access_token,
        cookie=session_cookie(session.sub, session.access_token),
        team_id=session.team_id,
        start_ms=start_ms,
        end_ms=end_ms,
        user_ids=user_ids,
    )
    loaded = merge_snapshot(
        session=session,
        usage_summary={
            "billingCycleStart": snapshot.cycle_start,
            "billingCycleEnd": snapshot.cycle_end,
        },
        period_usage=None,
        aggregated=aggregated,
        filtered={"usageEventsDisplay": []},
        plan_info={"planName": snapshot.plan_name},
        group_id=snapshot.group_id,
        group_ids=snapshot.group_ids or snapshot.selected_group_ids(),
        group_label=snapshot.group_label,
        groups=snapshot.groups,
        scope="group",
        spend_override=snapshot.spent_cents,
        limit_override=snapshot.limit_cents,
        breakdown_kind="models",
    )
    return replace(loaded, events=snapshot.events)


def find_member_id(payload: dict | None, email: str | None) -> int | str | None:
    if not email or not isinstance(payload, dict):
        return None
    raw = payload.get("teamMembers") or payload.get("members") or payload.get("users") or []
    if not isinstance(raw, list):
        return None
    want = email.casefold()
    for item in raw:
        if not isinstance(item, dict):
            continue
        member_email = item.get("email") or item.get("userEmail")
        if not member_email or str(member_email).casefold() != want:
            continue
        member_id = item.get("id") or item.get("userId") or item.get("user_id")
        if member_id is None or member_id == "":
            return None
        try:
            return int(member_id)
        except (TypeError, ValueError):
            return str(member_id)
    return None


def filter_events_for_email(filtered: dict | None, email: str | None) -> dict | None:
    if not email or not isinstance(filtered, dict):
        return filtered
    for key in ("usageEvents", "usageEventsDisplay", "events"):
        raw = filtered.get(key)
        if not isinstance(raw, list) or not raw:
            continue
        if not any(
            isinstance(event, dict) and (event.get("userEmail") or event.get("email"))
            for event in raw
        ):
            return filtered
        kept = [
            event
            for event in raw
            if isinstance(event, dict)
            and str(event.get("userEmail") or event.get("email") or "").casefold()
            == email.casefold()
        ]
        out = dict(filtered)
        out[key] = kept
        return out
    return filtered


def fetch_live_role(
    *,
    token: str,
    cookie: str,
    team_id: int | None,
    email: str | None,
) -> str | None:
    team_body: dict = {}
    if team_id is not None:
        team_body["teamId"] = team_id
    members = dashboard_request(
        "GetTeamMembers", token=token, cookie=cookie, body=team_body
    )
    role = member_role_for_email(members, email)
    if role:
        return role
    me = dashboard_request("GetMe", token=token, cookie=cookie, body=team_body)
    role = member_role_for_email(me, email) or extract_role(me)
    if role:
        return role
    auth_me = json_request("GET", "https://cursor.com/api/auth/me", cookie=cookie)
    return member_role_for_email(auth_me, email) or extract_role(auth_me)


def has_admin_access(session: Session, *, token: str, cookie: str) -> bool:
    live = fetch_live_role(
        token=token,
        cookie=cookie,
        team_id=session.team_id,
        email=session.email,
    )
    if live is not None:
        return is_admin_role(live)
    return is_admin_role(session.team_role)


def fetch_usage(
    scope: str = "team",
    group_id: int | None = None,
    group_ids: tuple[int, ...] | list[int] | None = None,
) -> UsageSnapshot:
    from cursor_usage_menubar.prefs import normalize_group_ids

    if scope not in ("team", "self", "group"):
        scope = "team"
    ids = normalize_group_ids(group_id, group_ids) if scope == "group" else ()
    group_id = ids[0] if ids else None
    session = read_session()
    if session is None:
        return UsageSnapshot.empty("Open Cursor to refresh your session")
    cookie = session_cookie(session.sub, session.access_token)
    token = session.access_token
    if not has_admin_access(session, token=token, cookie=cookie):
        return UsageSnapshot.empty(NO_ADMIN_STATUS)
    groups = list_groups(token=token, cookie=cookie, team_id=session.team_id)
    self_member = find_group_member(groups, session.email)
    usage_summary = json_request("GET", USAGE_SUMMARY_URL, cookie=cookie)
    start_ms, end_ms = _cycle_ms(usage_summary)
    team_body: dict = {}
    if session.team_id is not None:
        team_body["teamId"] = session.team_id
    team_body.update(_date_fields(start_ms, end_ms))
    user_id = self_member.user_id if self_member else None
    if user_id is None and scope == "self":
        members = dashboard_request(
            "GetTeamMembers",
            token=token,
            cookie=cookie,
            body={"teamId": session.team_id} if session.team_id is not None else {},
        )
        user_id = find_member_id(members, session.email)
        if isinstance(user_id, str) and str(user_id).isdigit():
            user_id = int(user_id)
    if scope == "self" and user_id is not None:
        team_body["userId"] = user_id
    period = dashboard_request(
        "GetCurrentPeriodUsage", token=token, cookie=cookie, body={}
    )
    aggregated = dashboard_request(
        "GetAggregatedUsageEvents", token=token, cookie=cookie, body=team_body
    )
    filtered = fetch_filtered_usage_events(
        token=token, cookie=cookie, base_body=team_body
    )
    plan_info = dashboard_request(
        "GetPlanInfo", token=token, cookie=cookie, body={}
    )
    selected_groups = [group for group in groups if group.id in ids]
    group_label = None
    if selected_groups:
        names = [group.name or str(group.id) for group in selected_groups]
        group_label = " + ".join(names) if len(names) > 1 else selected_groups[0].name
    elif group_id is not None:
        group_label = str(group_id)
    spend_override = None
    limit_override = None
    breakdown_kind = "models"
    event_source = filtered
    if scope == "group" and selected_groups:
        spend_override = sum(group.spend_cents or 0 for group in selected_groups)
        limits = [group.limit_cents for group in selected_groups if group.limit_cents]
        limit_override = sum(limits) if limits else None
        aggregated = {"aggregations": [], "totalCostCents": spend_override or 0}
    elif scope == "self" and self_member is not None:
        spend_override = self_member.spend_cents
        limit_override = self_member.limit_cents
    elif scope == "self":
        filtered = filter_events_for_email(filtered, session.email)
        event_source = filtered
        if user_id is None:
            synthesized = aggregations_from_filtered(filtered)
            if synthesized is not None:
                aggregated = synthesized
    if usage_summary is None and period is None and aggregated is None:
        return UsageSnapshot.empty("Open Cursor to refresh your session")
    snapshot = merge_snapshot(
        session=session,
        usage_summary=usage_summary,
        period_usage=period,
        aggregated=aggregated,
        filtered=filtered,
        plan_info=plan_info,
        group_id=group_id,
        group_ids=ids,
        group_label=group_label,
        groups=groups,
        scope=scope,
        spend_override=spend_override,
        limit_override=limit_override,
        breakdown_kind=breakdown_kind,
    )
    if event_source is not filtered:
        snapshot = replace(snapshot, events=parse_events(event_source))
    if scope == "group" and snapshot.selected_members():
        snapshot = replace(
            snapshot, events=events_for_members(snapshot.events, snapshot.selected_members())
        )
    return snapshot
