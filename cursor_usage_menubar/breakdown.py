from __future__ import annotations

import hashlib

from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSScrollView,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject
from objc import python_method
from objc import super as objc_super

from cursor_usage_menubar.formatters import dollars
from cursor_usage_menubar.models import ModelSpend, UsageSnapshot

WINDOW_WIDTH = 580
HEADER_H = 64
SUMMARY_H = 118
ROW_H = 72
CHILD_H = 58
FOOTER_H = 48
PAD = 20

try:
    DISCLOSURE = __import__("AppKit").NSDisclosureBezelStyle
except AttributeError:
    DISCLOSURE = 5

_PALETTE = (
    NSColor.systemBlueColor(),
    NSColor.systemPurpleColor(),
    NSColor.systemPinkColor(),
    NSColor.systemOrangeColor(),
    NSColor.systemTealColor(),
    NSColor.systemIndigoColor(),
    NSColor.systemGreenColor(),
    NSColor.systemBrownColor(),
)


def layout_height(snapshot: UsageSnapshot, auto_expanded: bool) -> int:
    height = PAD + HEADER_H + SUMMARY_H + 36
    for model in snapshot.models:
        height += ROW_H
        if model.is_auto and auto_expanded:
            height += CHILD_H * max(1, len(model.children))
        elif model.is_auto:
            height += 22
    return height + FOOTER_H + PAD


def _color_for(name: str):
    digest = hashlib.md5(name.encode()).hexdigest()
    return _PALETTE[int(digest, 16) % len(_PALETTE)]


class FlippedView(NSView):
    def isFlipped(self):
        return True


class BarView(NSView):
    def initWithFrame_fraction_color_(self, frame, fraction, color):
        self = objc_super(BarView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.fraction = max(0.0, min(1.0, float(fraction)))
        self.barColor = color
        return self

    def drawRect_(self, _rect):
        NSColor.separatorColor().colorWithAlphaComponent_(0.35).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), 6, 6
        ).fill()
        width = self.bounds().size.width * self.fraction
        if width <= 0:
            return
        self.barColor.set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(0, 0, width, self.bounds().size.height), 6, 6
        ).fill()


class BreakdownController(NSObject):
    _instance = None

    def init(self):
        self = objc_super(BreakdownController, self).init()
        self.window = None
        self.auto_expanded = False
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

    def toggleAuto_(self, _sender):
        self.auto_expanded = not self.auto_expanded
        self.render()

    @python_method
    def _ensure_window(self):
        if self.window is not None and self._window_alive():
            return
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WINDOW_WIDTH, 640),
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Cursor Usage")
        # Keep the singleton window alive after the user closes it so this
        # reusable controller never re-messages a deallocated NSWindow.
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
        height = max(640, layout_height(snap, self.auto_expanded))
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
        y = self._models(doc, snap, y)
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
        self._label(doc, "Cursor Usage", PAD, y, 400, 28, size=22, bold=True)
        cycle = "—"
        if snap.cycle_start or snap.cycle_end:
            cycle = f"{snap.cycle_start or '?'} → {snap.cycle_end or '?'}"
        self._label(doc, cycle, PAD, y + 32, 400, 18, size=12, secondary=True)
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
        pct_text = f"{snap.percent}%" if snap.percent is not None else "—"
        self._label(card, spent, 16, 12, 300, 36, size=28, bold=True)
        self._label(card, f"{pct_text} of limit", 16, 50, 300, 18, size=12, secondary=True)
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
    def _models(self, doc, snap, y):
        self._label(doc, "BY MODEL", PAD, y, 200, 18, size=11, bold=True, secondary=True)
        y += 28
        total = snap.spent_cents or sum(m.total_cents for m in snap.models) or 1
        for model in snap.models:
            y = self._model_row(doc, model, total, y, nested=False)
            if model.is_auto:
                if self.auto_expanded:
                    for child in model.children:
                        y = self._model_row(doc, child, total, y, nested=True)
                    if not model.children:
                        self._label(
                            doc,
                            "No Auto-routed models in this period",
                            PAD + 28,
                            y,
                            400,
                            18,
                            size=11,
                            secondary=True,
                        )
                        y += 22
                else:
                    n = len(model.children)
                    self._label(
                        doc,
                        f"{n} models routed by Auto",
                        PAD + 28,
                        y,
                        400,
                        18,
                        size=11,
                        secondary=True,
                    )
                    y += 22
        return y

    @python_method
    def _model_row(self, doc, model: ModelSpend, total: int, y, nested: bool):
        indent = 36 if nested else 0
        x = PAD + indent
        width = WINDOW_WIDTH - PAD * 2 - indent
        if model.is_auto and not nested:
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y + 4, 16, 16))
            btn.setBezelStyle_(DISCLOSURE)
            btn.setButtonType_(1)
            btn.setTitle_("")
            btn.setState_(1 if self.auto_expanded else 0)
            btn.setTarget_(self)
            btn.setAction_("toggleAuto:")
            doc.addSubview_(btn)
            x += 22
            width -= 22
        frac = model.total_cents / total if total else 0
        pct = int(round(100 * frac))
        self._label(doc, model.label, x, y, 280, 18, size=13, bold=True)
        self._label(
            doc,
            f"{dollars(model.total_cents)} · {pct}%",
            x + width - 160,
            y,
            160,
            18,
            size=12,
            secondary=True,
        )
        color = _color_for(model.label)
        bar = BarView.alloc().initWithFrame_fraction_color_(
            NSMakeRect(x, y + 24, width, 14), frac, color
        )
        doc.addSubview_(bar)
        tokens = f"{model.input_tokens:,} in / {model.output_tokens:,} out"
        if nested or model.request_count:
            tokens = f"{model.request_count} requests · {tokens}"
        self._label(doc, tokens, x, y + 42, width, 16, size=11, secondary=True)
        return y + (CHILD_H if nested else ROW_H)

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


def show_breakdown(snapshot: UsageSnapshot) -> None:
    BreakdownController.shared().show_(snapshot)
