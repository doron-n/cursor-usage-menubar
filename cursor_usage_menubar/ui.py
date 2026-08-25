from __future__ import annotations

from AppKit import (
    NSBezierPath,
    NSColor,
    NSFont,
    NSImage,
    NSImageView,
    NSMakeRect,
    NSTextField,
    NSView,
)
from objc import super as objc_super

from cursor_usage_menubar.theme import as_theme, theme_color, usage_tone

NS_ROUND_CAP = 1


def money_font(size: float):
    try:
        return NSFont.monospacedDigitSystemFontOfSize_weight_(size, 0.4)
    except Exception:
        return NSFont.boldSystemFontOfSize_(size)


def make_card(frame, theme: str, radius: float = 18):
    from cursor_usage_menubar.breakdown import FlippedView

    card = FlippedView.alloc().initWithFrame_(frame)
    card.setWantsLayer_(True)
    layer = card.layer()
    layer.setCornerRadius_(radius)
    layer.setBackgroundColor_(theme_color(theme, "card").CGColor())
    try:
        layer.setBorderWidth_(1)
        layer.setBorderColor_(theme_color(theme, "line").CGColor())
    except Exception:
        pass
    return card


def add_symbol(parent, name: str, x: float, y: float, size: float, color: NSColor):
    view = NSImageView.alloc().initWithFrame_(NSMakeRect(x, y, size, size))
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, name)
    if image is not None:
        try:
            from AppKit import NSImageSymbolConfiguration

            config = NSImageSymbolConfiguration.configurationWithPointSize_weight_(
                size * 0.86, 0.3
            )
            image = image.imageWithSymbolConfiguration_(config)
        except Exception:
            pass
        view.setImage_(image)
        try:
            view.setContentTintColor_(color)
        except Exception:
            pass
    parent.addSubview_(view)
    return view


def symbol_image(name: str, size: float = 14):
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, name)
    if image is None:
        return None
    try:
        from AppKit import NSImageSymbolConfiguration

        config = NSImageSymbolConfiguration.configurationWithPointSize_weight_(size, 0.3)
        return image.imageWithSymbolConfiguration_(config)
    except Exception:
        return image


class GaugeView(NSView):
    def initWithFrame_percent_theme_(self, frame, percent, theme):
        self = objc_super(GaugeView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.percent = percent
        self.theme = as_theme(theme)
        label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(8, frame.size.height / 2 - 18, frame.size.width - 16, 28)
        )
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setAlignment_(1)
        label.setFont_(money_font(22))
        label.setTextColor_(theme_color(self.theme, "text"))
        label.setStringValue_("—" if percent is None else f"{int(percent)}%")
        self.addSubview_(label)
        hint = NSTextField.alloc().initWithFrame_(
            NSMakeRect(8, frame.size.height / 2 + 10, frame.size.width - 16, 16)
        )
        hint.setBezeled_(False)
        hint.setDrawsBackground_(False)
        hint.setEditable_(False)
        hint.setAlignment_(1)
        hint.setFont_(NSFont.systemFontOfSize_(10))
        hint.setTextColor_(theme_color(self.theme, "muted"))
        hint.setStringValue_("of budget")
        self.addSubview_(hint)
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, _rect):
        bounds = self.bounds()
        cx = bounds.size.width / 2
        cy = bounds.size.height / 2
        radius = min(bounds.size.width, bounds.size.height) / 2 - 10
        track = NSBezierPath.alloc().init()
        track.setLineWidth_(11)
        track.setLineCapStyle_(NS_ROUND_CAP)
        track.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (cx, cy), radius, 0, 360, False
        )
        theme_color(self.theme, "track").set()
        track.stroke()
        fraction = 0.0
        if self.percent is not None:
            fraction = max(0.0, min(1.0, float(self.percent) / 100.0))
        if fraction <= 0:
            return
        sweep = 360.0 * fraction
        arc = NSBezierPath.alloc().init()
        arc.setLineWidth_(11)
        arc.setLineCapStyle_(NS_ROUND_CAP)
        arc.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (cx, cy), radius, -90, -90 + sweep, False
        )
        usage_tone(self.theme, self.percent).set()
        arc.stroke()


class GraphView(NSView):
    def initWithFrame_series_theme_(self, frame, series, theme):
        self = objc_super(GraphView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.series = list(series or ())
        self.theme = as_theme(theme)
        if self.series:
            first = NSTextField.alloc().initWithFrame_(NSMakeRect(16, frame.size.height - 20, 90, 14))
            last = NSTextField.alloc().initWithFrame_(
                NSMakeRect(frame.size.width - 106, frame.size.height - 20, 90, 14)
            )
            peak_cents = max(cents for _day, cents in self.series)
            peak = NSTextField.alloc().initWithFrame_(
                NSMakeRect(frame.size.width - 120, 10, 104, 16)
            )
            for field, text, align, color in (
                (first, self.series[0][0][5:], 0, theme_color(self.theme, "muted")),
                (last, self.series[-1][0][5:], 2, theme_color(self.theme, "muted")),
                (peak, f"peak ${peak_cents / 100:.2f}", 2, theme_color(self.theme, "accent")),
            ):
                field.setBezeled_(False)
                field.setDrawsBackground_(False)
                field.setEditable_(False)
                field.setStringValue_(text)
                field.setFont_(NSFont.systemFontOfSize_(10))
                field.setTextColor_(color)
                field.setAlignment_(align)
                self.addSubview_(field)
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, _rect):
        bounds = self.bounds()
        theme_color(self.theme, "card").set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, 18, 18).fill()
        if not self.series:
            return
        peak = max(cents for _day, cents in self.series) or 1
        count = len(self.series)
        left, right, top, bottom = 18, 18, 28, 28
        plot_w = max(1, bounds.size.width - left - right)
        plot_h = max(1, bounds.size.height - top - bottom)
        theme_color(self.theme, "line").set()
        for step in (0.25, 0.5, 0.75):
            y = top + plot_h * (1 - step)
            grid = NSBezierPath.alloc().init()
            grid.setLineWidth_(1)
            grid.moveToPoint_((left, y))
            grid.lineToPoint_((left + plot_w, y))
            grid.stroke()

        def point_at(index: int, cents: int):
            span = max(count - 1, 1)
            x = left + (index / span) * plot_w
            y = top + plot_h * (1 - cents / peak)
            return x, y

        fill = NSBezierPath.alloc().init()
        x0, _y0 = point_at(0, self.series[0][1])
        fill.moveToPoint_((x0, top + plot_h))
        for index, (_day, cents) in enumerate(self.series):
            fill.lineToPoint_(point_at(index, cents))
        x_last, _ = point_at(count - 1, self.series[-1][1])
        fill.lineToPoint_((x_last, top + plot_h))
        fill.closePath()
        theme_color(self.theme, "accent_dim").set()
        fill.fill()

        line = NSBezierPath.alloc().init()
        line.setLineWidth_(2.4)
        line.setLineCapStyle_(NS_ROUND_CAP)
        line.setLineJoinStyle_(1)
        for index, (_day, cents) in enumerate(self.series):
            pt = point_at(index, cents)
            if index == 0:
                line.moveToPoint_(pt)
            else:
                line.lineToPoint_(pt)
        theme_color(self.theme, "accent").set()
        line.stroke()

        x, y = point_at(count - 1, self.series[-1][1])
        dot = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x - 4, y - 4, 8, 8))
        usage_tone(self.theme, None).set()
        theme_color(self.theme, "accent").set()
        dot.fill()


class GlowBarView(NSView):
    def initWithFrame_fraction_color_(self, frame, fraction, color):
        self = objc_super(GlowBarView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.fraction = max(0.0, min(1.0, float(fraction)))
        self.barColor = color
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, _rect):
        bounds = self.bounds()
        radius = bounds.size.height / 2
        NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.08).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, radius, radius).fill()
        width = max(bounds.size.height, bounds.size.width * self.fraction) if self.fraction else 0
        if width <= 0:
            return
        self.barColor.set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(0, 0, width, bounds.size.height), radius, radius
        ).fill()


class PieView(NSView):
    def initWithFrame_cursor_other_theme_(self, frame, cursor, other, theme):
        self = objc_super(PieView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.cursor_cents = max(0, int(cursor))
        self.other_cents = max(0, int(other))
        self.theme = as_theme(theme)
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, _rect):
        bounds = self.bounds()
        cx = bounds.size.width / 2
        cy = bounds.size.height / 2
        radius = min(bounds.size.width, bounds.size.height) / 2 - 3
        total = self.cursor_cents + self.other_cents
        if total <= 0:
            theme_color(self.theme, "track").set()
            NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(cx - radius, cy - radius, radius * 2, radius * 2)
            ).fill()
        else:
            start = -90.0
            slices = (
                (self.cursor_cents, "accent"),
                (self.other_cents, "other"),
            )
            for cents, role in slices:
                if cents <= 0:
                    continue
                sweep = 360.0 * cents / total
                path = NSBezierPath.alloc().init()
                path.moveToPoint_((cx, cy))
                path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
                    (cx, cy), radius, start, start + sweep, False
                )
                path.closePath()
                theme_color(self.theme, role).set()
                path.fill()
                start += sweep
        hole = radius * 0.52
        theme_color(self.theme, "card").set()
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(cx - hole, cy - hole, hole * 2, hole * 2)
        ).fill()


class AvatarView(NSView):
    def initWithFrame_name_color_(self, frame, name, color):
        self = objc_super(AvatarView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.fill = color
        letters = _initials(name)
        label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, frame.size.height / 2 - 9, frame.size.width, 18)
        )
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setAlignment_(1)
        label.setFont_(NSFont.boldSystemFontOfSize_(13 if frame.size.width >= 36 else 11))
        label.setTextColor_(NSColor.whiteColor())
        label.setStringValue_(letters)
        self.addSubview_(label)
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, _rect):
        self.fill.set()
        NSBezierPath.bezierPathWithOvalInRect_(self.bounds()).fill()


def _initials(name: str) -> str:
    parts = [bit for bit in (name or "").split() if bit]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()
