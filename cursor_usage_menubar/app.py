from __future__ import annotations

import webbrowser

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

from cursor_usage_menubar.breakdown import show_breakdown
from cursor_usage_menubar.client import fetch_usage
from cursor_usage_menubar.formatters import dollars, menu_title
from cursor_usage_menubar.models import UsageSnapshot

DASHBOARD_URL = "https://cursor.com/dashboard/usage"


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
    top = "—"
    if snapshot.top_model is not None and snapshot.spent_cents:
        share = int(round(100 * snapshot.top_model.total_cents / snapshot.spent_cents))
        top = (
            f"{snapshot.top_model.label} · "
            f"{dollars(snapshot.top_model.total_cents)} · {share}%"
        )
    elif snapshot.top_model is not None:
        top = f"{snapshot.top_model.label} · {dollars(snapshot.top_model.total_cents)}"
    return [
        f"Account: {account}",
        f"Plan: {snapshot.plan_name}",
        f"Spent: {spent}",
        f"Allowance: {allowance}",
        f"Remaining: {remaining}",
        f"Cycle: {cycle}",
        f"Top model: {top}",
    ]


class CursorUsageApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("Cursor · —", quit_button=None)
        self._snapshot: UsageSnapshot | None = None
        self._info_items: list[rumps.MenuItem] = []
        self.menu = [
            rumps.separator,
            rumps.MenuItem("View Model Breakdown…", callback=self.view_breakdown),
            rumps.MenuItem("Refresh Now", callback=self.refresh_now),
            rumps.MenuItem("Open Cursor Dashboard", callback=self.open_dashboard),
            rumps.separator,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

    def _rebuild_info(self, snapshot: UsageSnapshot) -> None:
        for item in self._info_items:
            try:
                del self.menu[item.title]
            except Exception:
                pass
        self._info_items = []
        for row in reversed(info_rows(snapshot)):
            item = rumps.MenuItem(row)
            item.set_callback(None)
            self.menu.insert(0, item)
            self._info_items.append(item)

    def _apply(self, snapshot: UsageSnapshot) -> None:
        self._snapshot = snapshot
        self.title = menu_title(snapshot.spent_cents, snapshot.percent)
        self._rebuild_info(snapshot)

    @rumps.timer(300)
    def poll(self, _sender=None) -> None:
        self._apply(fetch_usage())

    def refresh_now(self, _sender=None) -> None:
        self._apply(fetch_usage())

    def view_breakdown(self, _sender=None) -> None:
        snap = self._snapshot or fetch_usage()
        self._snapshot = snap
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
