from __future__ import annotations

import webbrowser

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

from cursor_usage_menubar.breakdown import refresh_if_visible, show_breakdown
from cursor_usage_menubar.client import fetch_usage, load_group_models
from cursor_usage_menubar.formatters import dollars, menu_title
from cursor_usage_menubar.models import UsageSnapshot
from cursor_usage_menubar.prefs import load_prefs, save_prefs
from cursor_usage_menubar.users import refresh_users_if_visible, show_users

DASHBOARD_URL = "https://cursor.com/dashboard/usage"
_FETCH_ERROR_STATUS = "Open Cursor to refresh your session"


def _safe_fetch_usage() -> UsageSnapshot:
    """fetch_usage() talks to the network and parses third-party JSON; any
    unexpected failure here must degrade gracefully instead of crashing the
    menu bar app."""
    try:
        prefs = load_prefs()
        return fetch_usage(scope=prefs["scope"], group_id=prefs.get("group_id"))
    except Exception:
        return UsageSnapshot.empty(_FETCH_ERROR_STATUS)


def info_rows(snapshot: UsageSnapshot) -> list[str]:
    if snapshot.status and snapshot.spent_cents is None:
        return [snapshot.status]
    account = snapshot.email or "Unknown"
    if snapshot.team_name:
        account = f"{account} · {snapshot.team_name}"
    spent = dollars(snapshot.spent_cents) if snapshot.spent_cents is not None else "—"
    if snapshot.limit_cents:
        allowance = (
            f"{dollars(snapshot.spent_cents or 0)} / {dollars(snapshot.limit_cents)}"
            + (f" ({snapshot.percent}%)" if snapshot.percent is not None else "")
        )
        remaining = (
            dollars(snapshot.remaining_cents)
            if snapshot.remaining_cents is not None
            else "—"
        )
    else:
        allowance = "— (no cap reported)"
        remaining = "—"
    cycle = "—"
    if snapshot.cycle_start or snapshot.cycle_end:
        cycle = f"{snapshot.cycle_start or '?'} → {snapshot.cycle_end or '?'}"
    rows = [
        f"Account: {account}",
        f"Plan: {snapshot.plan_name}",
        f"View: {snapshot.view_label()}",
        f"Spent: {spent}",
        f"Allowance: {allowance}",
        f"Remaining: {remaining}",
        f"Cycle: {cycle}",
    ]
    members = snapshot.selected_members()
    if members:
        top_user = max(members, key=lambda m: m.spend_cents)
        name = top_user.name or top_user.email or str(top_user.user_id)
        share = ""
        if snapshot.spent_cents:
            share = f" · {int(round(100 * top_user.spend_cents / snapshot.spent_cents))}%"
        rows.append(f"Top user: {name} · {dollars(top_user.spend_cents)}{share}")
    if snapshot.top_model is not None and snapshot.spent_cents:
        share = int(round(100 * snapshot.top_model.total_cents / snapshot.spent_cents))
        rows.append(
            f"Top model: {snapshot.top_model.label} · "
            f"{dollars(snapshot.top_model.total_cents)} · {share}%"
        )
    elif snapshot.top_model is not None:
        rows.append(
            f"Top model: {snapshot.top_model.label} · "
            f"{dollars(snapshot.top_model.total_cents)}"
        )
    elif not members:
        rows.append("Top model: —")
    return rows


def user_usage_rows(snapshot: UsageSnapshot) -> list[str]:
    members = snapshot.selected_members()
    if not members:
        return []
    ordered = sorted(members, key=lambda m: m.spend_cents, reverse=True)
    total = snapshot.spent_cents or sum(m.spend_cents for m in ordered) or 1
    rows = ["Users by usage"]
    for member in ordered:
        name = member.name or member.email or str(member.user_id)
        share = int(round(100 * member.spend_cents / total)) if total else 0
        rows.append(f"{name} · {dollars(member.spend_cents)} · {share}%")
    return rows


class CursorUsageApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("Cursor · —", quit_button=None)
        self._snapshot: UsageSnapshot | None = None
        self._view_callbacks: list = []

    def _select_view(self, scope: str, group_id: int | None = None):
        def _cb(_sender=None) -> None:
            payload = {"scope": scope}
            if scope == "group":
                payload["group_id"] = group_id
            save_prefs(payload)
            self.refresh_now()

        self._view_callbacks.append(_cb)
        return _cb

    def _enter_group_id(self, _sender=None) -> None:
        current = load_prefs().get("group_id")
        win = rumps.Window(
            message="Billing group ID (leave empty for the whole team)",
            title="Select Group",
            default_text=str(current) if current is not None else "9485",
            ok="Use",
            cancel="Cancel",
            dimensions=(260, 24),
        )
        response = win.run()
        if not getattr(response, "clicked", False):
            return
        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            save_prefs({"scope": "self"})
            self.refresh_now()
            return
        try:
            save_prefs({"scope": "group", "group_id": int(text)})
        except ValueError:
            rumps.alert("Group ID must be a number, for example 9485.")
            return
        self.refresh_now()

    def _view_menu(self, snapshot: UsageSnapshot) -> rumps.MenuItem:
        selected_scope = snapshot.scope if snapshot.scope in ("team", "self", "group") else "team"
        selected_group = snapshot.group_id if selected_scope == "group" else None
        menu = rumps.MenuItem("View")
        self_item = rumps.MenuItem("Myself only", callback=self._select_view("self"))
        self_item.state = 1 if selected_scope == "self" else 0
        menu.add(self_item)
        menu.add(rumps.separator)
        seen: set[int] = set()
        for group in snapshot.groups:
            seen.add(group.id)
            title = f"{group.name} ({group.id})" if group.name else str(group.id)
            item = rumps.MenuItem(title, callback=self._select_view("group", group.id))
            item.state = 1 if selected_group == group.id else 0
            menu.add(item)
        if selected_group is not None and selected_group not in seen:
            item = rumps.MenuItem(
                str(selected_group), callback=self._select_view("group", selected_group)
            )
            item.state = 1
            menu.add(item)
        menu.add(rumps.MenuItem("Enter Group ID…", callback=self._enter_group_id))
        return menu

    def _rebuild_info(self, snapshot: UsageSnapshot) -> None:
        self._view_callbacks = []
        self.menu.clear()
        for row in info_rows(snapshot):
            item = rumps.MenuItem(row)
            item.set_callback(None)
            self.menu.add(item)
        self.menu.add(rumps.separator)
        self.menu.add(self._view_menu(snapshot))
        if snapshot.selected_members():
            self.menu.add(
                rumps.MenuItem("View Users by Usage…", callback=self.view_users)
            )
        self.menu.add(rumps.MenuItem("View Model Breakdown…", callback=self.view_breakdown))
        self.menu.add(rumps.MenuItem("Refresh Now", callback=self.refresh_now))
        self.menu.add(rumps.MenuItem("Open Cursor Dashboard", callback=self.open_dashboard))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Quit", callback=self.quit_app))

    def _apply(self, snapshot: UsageSnapshot) -> None:
        self._snapshot = snapshot
        self.title = menu_title(snapshot.spent_cents, snapshot.percent)
        self._rebuild_info(snapshot)
        refresh_if_visible(snapshot)
        refresh_users_if_visible(snapshot)

    @rumps.timer(300)
    def poll(self, _sender=None) -> None:
        self._apply(_safe_fetch_usage())

    def refresh_now(self, _sender=None) -> None:
        self._apply(_safe_fetch_usage())

    def view_users(self, _sender=None) -> None:
        snap = self._snapshot or _safe_fetch_usage()
        self._snapshot = snap
        show_users(snap)

    def view_breakdown(self, _sender=None) -> None:
        snap = self._snapshot or _safe_fetch_usage()
        if snap.scope == "group" and snap.group_id is not None:
            try:
                snap = load_group_models(snap)
            except Exception:
                pass
        self._snapshot = snap
        self._rebuild_info(snap)
        show_breakdown(snap)

    def open_dashboard(self, _sender=None) -> None:
        webbrowser.open(DASHBOARD_URL)

    def quit_app(self, _sender=None) -> None:
        rumps.quit_application()

    def run(self, **kwargs):
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
        self.refresh_now()
        super().run(**kwargs)
