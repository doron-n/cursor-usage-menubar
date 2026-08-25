from __future__ import annotations

from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSColor,
    NSFont,
    NSMakeRect,
    NSPopUpButton,
    NSScrollView,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject
from objc import python_method
from objc import super as objc_super

from cursor_usage_menubar.breakdown import (
    FOOTER_H,
    HEADER_H,
    PAD,
    ROW_H,
    WINDOW_WIDTH,
    BarView,
    FlippedView,
    _color_for,
    fill_summary_card,
    summary_height,
)
from cursor_usage_menubar.formatters import dollars
from cursor_usage_menubar.models import GroupMember, UsageSnapshot

SORT_BY_OPTIONS = ("usage", "cursor", "name", "cap", "recent")
SORT_BY_LABELS = ("Usage", "Cursor models", "Name", "Cap", "Recent")


def users_layout_height(snapshot: UsageSnapshot) -> int:
    members = snapshot.selected_members()
    height = PAD + HEADER_H + summary_height(snapshot, required=True) + 36
    height += ROW_H * max(1, len(members))
    return height + FOOTER_H + PAD


def listed_members(snapshot: UsageSnapshot) -> tuple[GroupMember, ...]:
    selected = snapshot.selected_members()
    if selected:
        return selected
    seen: dict[int, GroupMember] = {}
    for group in snapshot.groups:
        for member in group.members:
            seen.setdefault(member.user_id, member)
    members = tuple(seen.values())
    if snapshot.scope == "self" and snapshot.email:
        email = snapshot.email.casefold()
        mine = tuple(m for m in members if (m.email or "").casefold() == email)
        return mine
    return members


def ordered_members(
    snapshot: UsageSnapshot,
    *,
    sort_by: str = "usage",
    descending: bool = True,
    query: str = "",
    spikes_only: bool = False,
    recent_by_id: dict[int, int] | None = None,
    cursor_by_id: dict[int, int] | None = None,
    burst_ids: frozenset[int] | None = None,
) -> tuple[GroupMember, ...]:
    members = list(listed_members(snapshot))
    needle = query.strip().casefold()
    if needle:
        members = [
            member
            for member in members
            if needle in (member.name or "").casefold()
            or needle in (member.email or "").casefold()
            or needle in str(member.user_id)
        ]
    if spikes_only:
        flagged = burst_ids or frozenset()
        members = [member for member in members if member.user_id in flagged]
    key = sort_by if sort_by in SORT_BY_OPTIONS else "usage"
    if key == "recent":
        recent = recent_by_id or {}
        members.sort(key=lambda m: (recent.get(m.user_id, 0), m.user_id), reverse=descending)
    elif key == "cursor":
        shares = cursor_by_id or {}
        known = [member for member in members if member.user_id in shares]
        unknown = [member for member in members if member.user_id not in shares]
        known.sort(
            key=lambda member: (shares[member.user_id], member.user_id),
            reverse=descending,
        )
        members = known + unknown
    elif key == "usage":
        with_cap = [m for m in members if m.limit_cents]
        no_cap = [m for m in members if not m.limit_cents]
        with_cap.sort(
            key=lambda m: (member_cap_fraction(m), m.spend_cents, m.user_id),
            reverse=descending,
        )
        members = with_cap + no_cap
    else:
        members.sort(key=_member_sort_key(key), reverse=descending)
    return tuple(members)


def _member_sort_key(sort_by: str):
    if sort_by == "name":
        return lambda m: ((m.name or m.email or str(m.user_id)).casefold(), m.user_id)
    if sort_by == "cap":
        # Missing caps sort last when descending (typical default).
        return lambda m: (m.limit_cents if m.limit_cents is not None else -1, m.user_id)
    return lambda m: (m.spend_cents, m.user_id)


def member_cap_percent(member: GroupMember) -> int | None:
    if not member.limit_cents or member.limit_cents <= 0:
        return None
    return int(round(100 * member.spend_cents / member.limit_cents))


def cursor_usage_share(cursor_cents: int, other_cents: int) -> float | None:
    total = max(0, int(cursor_cents)) + max(0, int(other_cents))
    if total <= 0:
        return None
    return max(0, int(cursor_cents)) / total


def member_cap_fraction(member: GroupMember) -> float:
    if not member.limit_cents or member.limit_cents <= 0:
        return 0.0
    return min(1.0, member.spend_cents / member.limit_cents)


class UsersController(NSObject):
    _instance = None

    def init(self):
        self = objc_super(UsersController, self).init()
        self.window = None
        self.snapshot = None
        self.sort_by = "usage"
        self.sort_desc = True
        return self

    @classmethod
    def shared(cls):
        if cls._instance is None:
            cls._instance = cls.alloc().init()
        return cls._instance

    def show_(self, snapshot: UsageSnapshot):
        self.snapshot = snapshot
        self._ensure_window()
        self.render()
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    @python_method
    def _ensure_window(self):
        if self.window is not None and self._window_alive():
            return
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(40, 40, WINDOW_WIDTH, 640),
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Users by Usage")
        self.window.setReleasedWhenClosed_(False)
        self.window.setBackgroundColor_(NSColor.controlBackgroundColor())
        self.window.center()

    @python_method
    def _window_alive(self):
        try:
            self.window.isVisible()
            return True
        except Exception:
            return False

    @python_method
    def render(self):
        snap = self.snapshot
        height = max(640, users_layout_height(snap))
        scroll = NSScrollView.alloc().initWithFrame_(self.window.contentView().bounds())
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(True)
        scroll.setBackgroundColor_(NSColor.controlBackgroundColor())
        scroll.setAutoresizingMask_(18)
        doc = FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, WINDOW_WIDTH, height))
        doc.setWantsLayer_(True)
        y = PAD
        y = self._header(doc, snap, y)
        y = self._summary(doc, snap, y)
        y = self._users(doc, snap, y)
        self._footer(doc, y)
        scroll.setDocumentView_(doc)
        self.window.setContentView_(scroll)

    @python_method
    def _label(self, parent, text, x, y, w, h, size=13, bold=False, color=None, secondary=False):
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        field.setBezeled_(False)
        field.setDrawsBackground_(False)
        field.setEditable_(False)
        field.setSelectable_(False)
        field.setStringValue_(text)
        font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
        field.setFont_(font)
        if secondary:
            field.setTextColor_(NSColor.secondaryLabelColor())
        elif color is not None:
            field.setTextColor_(color)
        else:
            field.setTextColor_(NSColor.labelColor())
        parent.addSubview_(field)
        return field

    @python_method
    def _header(self, doc, snap, y):
        self._label(doc, "Users by Usage", PAD, y, 400, 28, size=22, bold=True)
        cycle = "—"
        if snap.cycle_start or snap.cycle_end:
            cycle = f"{snap.cycle_start or '?'} → {snap.cycle_end or '?'}"
        subtitle = f"{snap.view_label()} · {cycle}"
        self._label(doc, subtitle, PAD, y + 32, 520, 18, size=12, secondary=True)
        return y + HEADER_H

    @python_method
    def _summary(self, doc, snap, y):
        card_h = summary_height(snap, required=True)
        card = FlippedView.alloc().initWithFrame_(
            NSMakeRect(PAD, y, WINDOW_WIDTH - PAD * 2, card_h - 16)
        )
        card.setWantsLayer_(True)
        card.layer().setCornerRadius_(12)
        card.layer().setBackgroundColor_(
            NSColor.separatorColor().colorWithAlphaComponent_(0.18).CGColor()
        )
        fill_summary_card(
            self,
            card,
            snap,
            users_count=len(snap.selected_members()),
            required_forecast=True,
        )
        doc.addSubview_(card)
        return y + card_h

    @python_method
    def _users(self, doc, snap, y):
        self._label(doc, "BY USER", PAD, y + 4, 120, 18, size=11, bold=True, secondary=True)
        self._sort_controls(doc, y)
        y += 32
        members = ordered_members(
            snap, sort_by=self.sort_by, descending=self.sort_desc
        )
        if not members:
            self._label(
                doc,
                "No users in this view",
                PAD,
                y,
                400,
                18,
                size=12,
                secondary=True,
            )
            return y + 22
        for member in members:
            y = self._user_row(doc, member, y)
        return y

    def sortByChanged_(self, sender):
        idx = int(sender.indexOfSelectedItem())
        if 0 <= idx < len(SORT_BY_OPTIONS):
            self.sort_by = SORT_BY_OPTIONS[idx]
        self.render()

    def sortDirChanged_(self, sender):
        self.sort_desc = int(sender.indexOfSelectedItem()) == 0
        self.render()

    @python_method
    def _sort_controls(self, doc, y):
        by = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(WINDOW_WIDTH - PAD - 210, y, 110, 26), False
        )
        by.addItemsWithTitles_(list(SORT_BY_LABELS))
        by.selectItemAtIndex_(
            SORT_BY_OPTIONS.index(self.sort_by)
            if self.sort_by in SORT_BY_OPTIONS
            else 0
        )
        by.setTarget_(self)
        by.setAction_("sortByChanged:")
        doc.addSubview_(by)
        direction = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(WINDOW_WIDTH - PAD - 92, y, 92, 26), False
        )
        direction.addItemsWithTitles_(["Desc", "Asc"])
        direction.selectItemAtIndex_(0 if self.sort_desc else 1)
        direction.setTarget_(self)
        direction.setAction_("sortDirChanged:")
        doc.addSubview_(direction)

    @python_method
    def _user_row(self, doc, member: GroupMember, y):
        x = PAD
        width = WINDOW_WIDTH - PAD * 2
        name = member.name or member.email or str(member.user_id)
        frac = member_cap_fraction(member)
        pct = member_cap_percent(member)
        spent = dollars(member.spend_cents)
        amount = f"{spent} · {pct}%" if pct is not None else spent
        self._label(doc, name, x, y, 280, 18, size=13, bold=True)
        self._label(
            doc,
            amount,
            x + width - 160,
            y,
            160,
            18,
            size=12,
            secondary=True,
        )
        bar = BarView.alloc().initWithFrame_fraction_color_(
            NSMakeRect(x, y + 24, width, 14), frac, _color_for(name)
        )
        doc.addSubview_(bar)
        detail = member.email or f"User {member.user_id}"
        if member.limit_cents:
            detail = f"{detail} · cap {dollars(member.limit_cents)}"
        self._label(doc, detail, x, y + 42, width, 16, size=11, secondary=True)
        return y + ROW_H

    @python_method
    def _footer(self, doc, y):
        self._label(
            doc,
            "Unofficial Cursor APIs — they can change or break without notice.",
            PAD,
            y + 8,
            WINDOW_WIDTH - PAD * 2,
            32,
            size=11,
            secondary=True,
        )


def show_users(snapshot: UsageSnapshot) -> None:
    UsersController.shared().show_(snapshot)


def refresh_users_if_visible(snapshot: UsageSnapshot) -> None:
    ctrl = UsersController._instance
    if ctrl is None or ctrl.window is None:
        return
    try:
        visible = bool(ctrl.window.isVisible())
    except Exception:
        return
    if not visible:
        return
    ctrl.snapshot = snapshot
    ctrl.render()
