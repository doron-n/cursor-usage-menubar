from __future__ import annotations

import http.client
import json
import ssl
import urllib.error
import urllib.request

import certifi

from cursor_usage_menubar.auth import read_session, session_cookie
from cursor_usage_menubar.merge import merge_snapshot
from cursor_usage_menubar.models import UsageSnapshot

USAGE_SUMMARY_URL = "https://cursor.com/api/usage-summary"
API2 = "https://api2.cursor.sh/aiserver.v1.DashboardService"
_TIMEOUT = 8


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


def fetch_usage() -> UsageSnapshot:
    session = read_session()
    if session is None:
        return UsageSnapshot.empty("Open Cursor to refresh your session")
    cookie = session_cookie(session.sub, session.access_token)
    token = session.access_token
    team_body: dict = {}
    if session.team_id is not None:
        team_body["teamId"] = session.team_id
    usage_summary = json_request(
        "GET", USAGE_SUMMARY_URL, cookie=cookie
    )
    period = json_request(
        "POST", f"{API2}/GetCurrentPeriodUsage", token=token, body={}
    )
    aggregated = json_request(
        "POST", f"{API2}/GetAggregatedUsageEvents", token=token, body=team_body
    )
    filtered_body = {"page": 1, "pageSize": 1000, **team_body}
    filtered = json_request(
        "POST", f"{API2}/GetFilteredUsageEvents", token=token, body=filtered_body
    )
    plan_info = json_request(
        "POST", f"{API2}/GetPlanInfo", token=token, body={}
    )
    if usage_summary is None and period is None and aggregated is None:
        return UsageSnapshot.empty("Open Cursor to refresh your session")
    return merge_snapshot(
        session=session,
        usage_summary=usage_summary,
        period_usage=period,
        aggregated=aggregated,
        filtered=filtered,
        plan_info=plan_info,
    )
