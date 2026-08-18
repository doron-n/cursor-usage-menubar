from __future__ import annotations

from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSColor,
    NSFont,
    NSMakeRect,
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
    SUMMARY_H,
    WINDOW_WIDTH,
    BarView,
    FlippedView,
    _color_for,
)
from cursor_usage_menubar.formatters import dollars
from cursor_usage_menubar.models import GroupMember, UsageSnapshot


def users_layout_height(snapshot: UsageSnapshot) -> int:
    members = snapshot.selected_members()
    height = PAD + HEADER_H + SUMMARY_H + 36
    height += ROW_H * max(1, len(members))
    return height + FOOTER_H + PAD


def ordered_members(snapshot: UsageSnapshot) -> tuple[GroupMember, ...]:
    members = snapshot.selected_members()
    return tuple(sorted(members, key=lambda m: m.spend_cents, reverse=True))


class UsersController(NSObject):
    _instance = None

    def init(self):
        self = objc_super(UsersController, self).init()
        self.window = None
        self.snapshot = None
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
        card = FlippedView.alloc().initWithFrame_(
            NSMakeRect(PAD, y, WINDOW_WIDTH - PAD * 2, SUMMARY_H - 16)
        )
        card.setWantsLayer_(True)
        card.layer().setCornerRadius_(12)
        card.layer().setBackgroundColor_(
            NSColor.separatorColor().colorWithAlphaComponent_(0.18).CGColor()
        )
        spent = dollars(snap.spent_cents) if snap.spent_cents is not None else "—"
        n = len(snap.selected_members())
        self._label(card, spent, 16, 12, 300, 36, size=28, bold=True)
        self._label(
            card,
            f"{n} users in this group",
            16,
            50,
            400,
            18,
            size=12,
            secondary=True,
        )
        fraction = 0.0
        if snap.percent is not None:
            fraction = min(1.0, snap.percent / 100.0)
        if snap.percent is not None and snap.percent >= 90:
            color = NSColor.systemRedColor()
        elif snap.percent is not None and snap.percent >= 75:
            color = NSColor.systemOrangeColor()
        else:
            color = NSColor.systemGreenColor()
        bar = BarView.alloc().initWithFrame_fraction_color_(
            NSMakeRect(16, 78, WINDOW_WIDTH - PAD * 2 - 48, 14), fraction, color
        )
        card.addSubview_(bar)
        doc.addSubview_(card)
        return y + SUMMARY_H

    @python_method
    def _users(self, doc, snap, y):
        self._label(doc, "BY USER", PAD, y, 200, 18, size=11, bold=True, secondary=True)
        y += 28
        members = ordered_members(snap)
        total = snap.spent_cents or sum(m.spend_cents for m in members) or 1
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
            y = self._user_row(doc, member, total, y)
        return y

    @python_method
    def _user_row(self, doc, member: GroupMember, total: int, y):
        x = PAD
        width = WINDOW_WIDTH - PAD * 2
        name = member.name or member.email or str(member.user_id)
        frac = member.spend_cents / total if total else 0
        pct = int(round(100 * frac))
        self._label(doc, name, x, y, 280, 18, size=13, bold=True)
        self._label(
            doc,
            f"{dollars(member.spend_cents)} · {pct}%",
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
