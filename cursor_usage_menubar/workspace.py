from __future__ import annotations

import time

from AppKit import (
    NSApp,
    NSAppearance,
    NSBackingStoreBuffered,
    NSButton,
    NSButtonTypeSwitch,
    NSCursor,
    NSFont,
    NSImageView,
    NSMakeRect,
    NSPopUpButton,
    NSSearchField,
    NSSegmentedControl,
    NSScrollView,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRange, NSObject, NSPointInRect
from objc import python_method
from objc import super as objc_super

from cursor_usage_menubar.analytics import (
    BURST_WINDOW_MS,
    FAST_WINDOW_MS,
    burst_member_ids,
    burst_reason,
    daily_spend_series,
    month_start_date,
    member_events,
    member_models,
    member_stats,
    recent_spend_cents,
    view_pool_cents,
)
from cursor_usage_menubar.branding import app_icon
from cursor_usage_menubar.breakdown import (
    CHILD_H,
    FOOTER_H,
    FlippedView,
    _color_for,
)
from cursor_usage_menubar.cursor_pricing import (
    MODEL_FILTERS,
    cursor_model_forecast,
    filter_models,
    forecast_card_captions,
    pool_cents,
    search_models,
    sort_models,
)
from cursor_usage_menubar.formatters import actual_usage_caption, dollars
from cursor_usage_menubar.models import UsageSnapshot
from cursor_usage_menubar.prefs import load_prefs, save_prefs
from cursor_usage_menubar.theme import appearance_name, as_theme, theme_color, usage_tone
from cursor_usage_menubar.ui import (
    AvatarView,
    GaugeView,
    GlowBarView,
    GraphView,
    PieView,
    add_symbol,
    make_card,
    money_font,
    symbol_image,
)
from cursor_usage_menubar.users import (
    SORT_BY_LABELS,
    SORT_BY_OPTIONS,
    listed_members,
    member_cap_fraction,
    member_cap_percent,
    ordered_members,
)

WINDOW_WIDTH = 880
PAD = 22
USER_ROW_H = 90
MODEL_ROW_H = 84
TABS = ("overview", "models", "users")
TAB_SYMBOLS = ("chart.xyaxis.line", "cpu", "person.2")
MODEL_SORTS = ("usage", "name", "tokens")
MODEL_SORT_LABELS = ("Usage", "Name", "Tokens")
MODEL_FILTER_LABELS = {
    "all": "All models",
    "cursor": "Cursor models",
    "other": "Other models",
}


class UserHitRow(FlippedView):
    def initWithFrame_userId_target_(self, frame, user_id, target):
        self = objc_super(UserHitRow, self).initWithFrame_(frame)
        if self is None:
            return None
        self.user_id = int(user_id)
        self.click_target = target
        return self

    def resetCursorRects(self):
        self.addCursorRect_cursor_(self.bounds(), NSCursor.pointingHandCursor())

    def mouseUp_(self, event):
        loc = self.convertPoint_fromView_(event.locationInWindow(), None)
        if NSPointInRect(loc, self.bounds()):
            self.click_target.openUser_(self.user_id)


class WorkspaceController(NSObject):
    _instance = None

    def init(self):
        self = objc_super(WorkspaceController, self).init()
        self.window = None
        self.snapshot = None
        self.tab = "overview"
        self.theme = as_theme(load_prefs().get("theme"))
        self.auto_expanded = False
        self.model_filter = "all"
        self.model_sort = "usage"
        self.model_sort_desc = True
        self.model_query = ""
        self.user_sort = "usage"
        self.user_sort_desc = True
        self.user_query = ""
        self.spikes_only = False
        self.selected_user_id = None
        self._search = None
        self._keep_search_focus = False
        return self

    @classmethod
    def shared(cls):
        if cls._instance is None:
            cls._instance = cls.alloc().init()
        return cls._instance

    def show_tab_(self, snapshot: UsageSnapshot, tab: str | None = None):
        self.snapshot = snapshot
        if tab in TABS:
            self.tab = tab
        self.theme = as_theme(load_prefs().get("theme"))
        self._ensure_window()
        self._apply_appearance()
        self.render()
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    @python_method
    def _ensure_window(self):
        if self.window is not None and self._window_alive():
            return
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(80, 80, WINDOW_WIDTH, 760),
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Cursor Usage")
        self.window.setReleasedWhenClosed_(False)
        self.window.setMinSize_((700, 560))
        try:
            self.window.setTitlebarAppearsTransparent_(True)
            self.window.setMovableByWindowBackground_(True)
        except Exception:
            pass
        self.window.center()

    @python_method
    def _window_alive(self):
        try:
            self.window.isVisible()
            return True
        except Exception:
            return False

    @python_method
    def _apply_appearance(self):
        try:
            self.window.setAppearance_(
                NSAppearance.appearanceNamed_(appearance_name(self.theme))
            )
        except Exception:
            pass
        self.window.setBackgroundColor_(theme_color(self.theme, "bg"))

    def tabChanged_(self, sender):
        idx = int(sender.selectedSegment())
        if 0 <= idx < len(TABS):
            self.tab = TABS[idx]
        if self.tab != "users":
            self.selected_user_id = None
        self._keep_search_focus = False
        self.render()

    def openUser_(self, user_id):
        self.selected_user_id = int(user_id)
        self.tab = "users"
        self._keep_search_focus = False
        self.render()

    def closeUser_(self, _sender):
        self.selected_user_id = None
        self.render()

    def themeChanged_(self, sender):
        self.theme = "dark" if int(sender.state()) == 1 else "light"
        save_prefs({"theme": self.theme})
        self._apply_appearance()
        self.render()

    def toggleAuto_(self, _sender):
        self.auto_expanded = not self.auto_expanded
        self.render()

    def filterChanged_(self, sender):
        idx = int(sender.indexOfSelectedItem())
        if 0 <= idx < len(MODEL_FILTERS):
            self.model_filter = MODEL_FILTERS[idx]
        self.render()

    def modelSortChanged_(self, sender):
        idx = int(sender.indexOfSelectedItem())
        if 0 <= idx < len(MODEL_SORTS):
            self.model_sort = MODEL_SORTS[idx]
        self.render()

    def modelDirChanged_(self, sender):
        self.model_sort_desc = int(sender.indexOfSelectedItem()) == 0
        self.render()

    def sortByChanged_(self, sender):
        idx = int(sender.indexOfSelectedItem())
        if 0 <= idx < len(SORT_BY_OPTIONS):
            self.user_sort = SORT_BY_OPTIONS[idx]
        self.render()

    def sortDirChanged_(self, sender):
        self.user_sort_desc = int(sender.indexOfSelectedItem()) == 0
        self.render()

    def spikeFilterChanged_(self, sender):
        self.spikes_only = int(sender.indexOfSelectedItem()) == 1
        self.render()

    def controlTextDidChange_(self, notification):
        text = str(notification.object().stringValue() or "")
        if self.tab == "models":
            self.model_query = text
        else:
            self.user_query = text
        self._keep_search_focus = True
        self.render()

    @python_method
    def render(self):
        snap = self.snapshot
        if snap is None:
            return
        width = int(self.window.contentView().bounds().size.width or WINDOW_WIDTH)
        height = max(760, self._layout_height(snap, width))
        scroll = NSScrollView.alloc().initWithFrame_(self.window.contentView().bounds())
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(0)
        scroll.setDrawsBackground_(True)
        scroll.setBackgroundColor_(theme_color(self.theme, "bg"))
        scroll.setAutoresizingMask_(18)
        doc = FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        doc.setWantsLayer_(True)
        doc.layer().setBackgroundColor_(theme_color(self.theme, "bg").CGColor())
        y = PAD
        y = self._chrome(doc, snap, y, width)
        if self.tab == "models":
            y = self._models(doc, snap, y, width)
        elif self.tab == "users":
            y = self._users(doc, snap, y, width)
        else:
            y = self._overview(doc, snap, y, width)
        self._footer(doc, y, width)
        scroll.setDocumentView_(doc)
        self.window.setContentView_(scroll)
        if self._keep_search_focus and self._search is not None:
            self.window.makeFirstResponder_(self._search)
            editor = self._search.currentEditor()
            if editor is not None:
                end = len(str(self._search.stringValue() or ""))
                editor.setSelectedRange_(NSMakeRange(end, 0))
        self._keep_search_focus = False

    @python_method
    def _layout_height(self, snap, width):
        height = PAD + 128
        if self.tab == "overview":
            height += 188 + 72 + 36 + 228
            height += USER_ROW_H * max(
                1,
                len(burst_member_ids(snap.events, listed_members(snap), now_ms=_now_ms())),
            )
        elif self.tab == "models":
            models = self._visible_models(snap)
            height += 48
            for model in models:
                height += MODEL_ROW_H
                if model.is_auto and self.auto_expanded:
                    height += CHILD_H * max(1, len(model.children))
                elif model.is_auto:
                    height += 22
        else:
            member = self._selected_member(snap)
            if member is not None:
                models = member_models(snap.events, member)
                height += 90 + 168 + 110 + 140 + 220 + 48 + MODEL_ROW_H * max(1, len(models))
            else:
                height += 48 + 140 + USER_ROW_H * max(1, len(self._visible_users(snap)))
        return height + FOOTER_H + PAD

    @python_method
    def _chrome(self, doc, snap, y, width):
        mark = NSImageView.alloc().initWithFrame_(NSMakeRect(PAD, y, 36, 36))
        mark.setWantsLayer_(True)
        icon = app_icon()
        if icon is not None:
            mark.setImage_(icon)
            try:
                mark.layer().setCornerRadius_(9)
                mark.layer().setMasksToBounds_(True)
            except Exception:
                pass
        doc.addSubview_(mark)
        self._label(doc, "Cursor Usage", PAD + 46, y - 2, 360, 26, size=22, bold=True)
        toggle = NSButton.alloc().initWithFrame_(
            NSMakeRect(width - PAD - 120, y + 6, 120, 24)
        )
        toggle.setButtonType_(NSButtonTypeSwitch)
        toggle.setTitle_("Dark mode")
        toggle.setState_(1 if self.theme == "dark" else 0)
        toggle.setTarget_(self)
        toggle.setAction_("themeChanged:")
        doc.addSubview_(toggle)
        today = time.strftime("%Y-%m-%d")
        cycle = f"{month_start_date(_now_ms()).isoformat()} → {today}"
        self._label(
            doc,
            f"{snap.view_label()} · {cycle}",
            PAD + 46,
            y + 24,
            width - PAD * 2 - 180,
            16,
            size=12,
            secondary=True,
        )
        tabs = NSSegmentedControl.alloc().initWithFrame_(
            NSMakeRect(PAD, y + 52, 420, 32)
        )
        tabs.setSegmentCount_(3)
        try:
            from AppKit import NSSegmentSwitchTrackingSelectOne

            tabs.setTrackingMode_(NSSegmentSwitchTrackingSelectOne)
        except Exception:
            tabs.setTrackingMode_(0)
        for index, title in enumerate(("Overview", "Models", "Users")):
            image = symbol_image(TAB_SYMBOLS[index], 13)
            if image is not None:
                tabs.setImage_forSegment_(image, index)
            tabs.setLabel_forSegment_(title, index)
            tabs.setWidth_forSegment_(136, index)
        tabs.setSelectedSegment_(TABS.index(self.tab) if self.tab in TABS else 0)
        tabs.setTarget_(self)
        tabs.setAction_("tabChanged:")
        doc.addSubview_(tabs)
        return y + 96

    @python_method
    def _overview(self, doc, snap, y, width):
        y = self._hero(doc, snap, y, width, users_count=len(listed_members(snap)))
        y = self._section(doc, "SPEND THIS CYCLE", y, "chart.xyaxis.line")
        series = daily_spend_series(
            snap.events,
            cycle_start=snap.cycle_start,
            cycle_end=snap.cycle_end,
            now_ms=_now_ms(),
        )
        graph = GraphView.alloc().initWithFrame_series_theme_(
            NSMakeRect(PAD, y, width - PAD * 2, 200), series, self.theme
        )
        doc.addSubview_(graph)
        y += 216
        if not series:
            self._label(
                doc,
                "No dated usage events yet — the graph fills in as Cursor returns timestamps.",
                PAD + 16,
                y - 48,
                width - PAD * 2 - 32,
                18,
                size=12,
                secondary=True,
            )
        members = listed_members(snap)
        flagged = burst_member_ids(snap.events, members, now_ms=_now_ms())
        y = self._section(doc, "SPEND SPIKES", y, "flame.fill")
        if not flagged:
            self._label(
                doc,
                "No one is burning budget unusually fast in the last 6–24 hours.",
                PAD,
                y,
                width - PAD * 2,
                18,
                size=12,
                secondary=True,
            )
            return y + 28
        by_id = {member.user_id: member for member in members}
        for user_id in flagged:
            member = by_id.get(user_id)
            if member is None:
                continue
            y = self._user_row(doc, member, y, width, spike=True, clickable=True)
        return y

    @python_method
    def _models(self, doc, snap, y, width):
        y = self._toolbar(
            doc,
            y,
            width,
            query=self.model_query,
            extra="models",
        )
        models = self._visible_models(snap)
        total = sum(m.total_cents for m in models) or 1
        if not models:
            self._label(doc, "No models match this filter.", PAD, y, 400, 18, size=12, secondary=True)
            return y + 22
        for model in models:
            y = self._model_row(doc, model, total, y, width, nested=False)
            if not model.is_auto:
                continue
            if self.auto_expanded:
                for child in model.children:
                    y = self._model_row(doc, child, total, y, width, nested=True)
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
                self._label(
                    doc,
                    f"{len(model.children)} models routed by Auto",
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
    def _users(self, doc, snap, y, width):
        member = self._selected_member(snap)
        if member is not None:
            return self._user_detail(doc, snap, member, y, width)
        y = self._toolbar(doc, y, width, query=self.user_query, extra="users")
        members = self._visible_users(snap)
        y = self._pool_pie(
            doc, view_pool_cents(snap.events, members, snap.models), y, width
        )
        if not members:
            self._label(
                doc,
                "No users in this view. Pick a billing group, or switch to Global.",
                PAD,
                y,
                width - PAD * 2,
                18,
                size=12,
                secondary=True,
            )
            return y + 22
        now_ms = _now_ms()
        flagged = burst_member_ids(snap.events, members, now_ms=now_ms)
        for member in members:
            y = self._user_row(
                doc,
                member,
                y,
                width,
                spike=member.user_id in flagged,
                now_ms=now_ms,
                clickable=True,
            )
        return y

    @python_method
    def _visible_models(self, snap):
        models = filter_models(snap.models, self.model_filter)
        models = search_models(models, self.model_query)
        return sort_models(models, self.model_sort, self.model_sort_desc)

    @python_method
    def _visible_users(self, snap):
        now_ms = _now_ms()
        members = listed_members(snap)
        recent = {
            member.user_id: recent_spend_cents(snap.events, member, now_ms=now_ms)
            for member in members
        }
        flagged = burst_member_ids(snap.events, members, now_ms=now_ms)
        return ordered_members(
            snap,
            sort_by=self.user_sort,
            descending=self.user_sort_desc,
            query=self.user_query,
            spikes_only=self.spikes_only,
            recent_by_id=recent,
            burst_ids=flagged,
        )

    @python_method
    def _selected_member(self, snap):
        if self.selected_user_id is None:
            return None
        for member in listed_members(snap):
            if member.user_id == self.selected_user_id:
                return member
        return None

    @python_method
    def _user_detail(self, doc, snap, member, y, width):
        now_ms = _now_ms()
        stats = member_stats(snap.events, member)
        models = stats["models"]
        back = NSButton.alloc().initWithFrame_(NSMakeRect(PAD, y, 90, 28))
        back.setTitle_("← Users")
        back.setBezelStyle_(1)
        back.setTarget_(self)
        back.setAction_("closeUser:")
        doc.addSubview_(back)
        name = member.name or member.email or str(member.user_id)
        avatar = AvatarView.alloc().initWithFrame_name_color_(
            NSMakeRect(PAD + 102, y - 4, 44, 44), name, _color_for(name)
        )
        doc.addSubview_(avatar)
        self._label(doc, name, PAD + 156, y - 4, width - PAD * 2 - 160, 26, size=22, bold=True)
        y += 36
        email = member.email or "—"
        self._label(
            doc,
            f"{email} · user {member.user_id}",
            PAD + 156,
            y,
            width - PAD * 2 - 160,
            16,
            size=12,
            secondary=True,
        )
        y += 36
        remaining = (
            None
            if member.limit_cents is None
            else member.limit_cents - member.spend_cents
        )
        pct = member_cap_percent(member)
        last6 = recent_spend_cents(
            snap.events, member, now_ms=now_ms, window_ms=FAST_WINDOW_MS
        )
        last24 = recent_spend_cents(
            snap.events, member, now_ms=now_ms, window_ms=BURST_WINDOW_MS
        )
        share = ""
        if snap.spent_cents:
            share = f"{int(round(100 * member.spend_cents / snap.spent_cents))}% of this view"
        spike = burst_reason(snap.events, member, now_ms=now_ms)
        hero = make_card(NSMakeRect(PAD, y, width - PAD * 2, 156), self.theme)
        gauge = GaugeView.alloc().initWithFrame_percent_theme_(
            NSMakeRect(12, 10, 136, 136), pct, self.theme
        )
        hero.addSubview_(gauge)
        inner = width - PAD * 2 - 168
        tile_w = (inner - 20) // 2
        facts = [
            ("dollarsign.circle", "Spent", dollars(member.spend_cents)),
            ("creditcard", "Cap", dollars(member.limit_cents) if member.limit_cents else "—"),
            ("arrow.uturn.backward", "Remaining", dollars(remaining) if remaining is not None else "—"),
            ("flame.fill" if spike else "clock", "Last 24h", dollars(last24)),
        ]
        for index, (symbol, title, value) in enumerate(facts):
            col = index % 2
            row = index // 2
            self._tile(
                hero,
                156 + col * (tile_w + 12),
                12 + row * 68,
                tile_w,
                60,
                symbol,
                title,
                value,
            )
        doc.addSubview_(hero)
        y += 168
        y = self._top_models(doc, stats["top_models"], y, width)
        y = self._pool_pie(doc, stats.get("pool") or pool_cents(models), y, width)
        extras = [
            ("Last 6h", dollars(last6)),
            ("Requests", str(stats["requests"])),
            ("Tokens", f"{stats['input_tokens']:,} in / {stats['output_tokens']:,} out"),
            ("First seen", _when(stats["first_ms"])),
            ("Last seen", _when(stats["last_ms"])),
            ("Share", share or "—"),
        ]
        col_w = (width - PAD * 2 - 12) // 2
        for index, (title, value) in enumerate(extras):
            col = index % 2
            row = index // 2
            x = PAD + col * (col_w + 12)
            yy = y + row * 40
            self._label(doc, title, x, yy, col_w, 14, size=11, secondary=True)
            self._label(doc, value, x, yy + 14, col_w, 18, size=13, bold=True)
        y += 40 * ((len(extras) + 1) // 2) + 8
        if spike:
            self._label(doc, spike, PAD, y, width - PAD * 2, 18, size=13, color=theme_color(self.theme, "spike"))
            y += 26
        y = self._section(doc, "SPEND THIS CYCLE", y, "chart.xyaxis.line")
        series = daily_spend_series(
            member_events(snap.events, member),
            cycle_start=snap.cycle_start,
            cycle_end=snap.cycle_end,
            now_ms=now_ms,
        )
        graph = GraphView.alloc().initWithFrame_series_theme_(
            NSMakeRect(PAD, y, width - PAD * 2, 200), series, self.theme
        )
        doc.addSubview_(graph)
        y += 216
        if not series:
            self._label(
                doc,
                "No dated events for this user in the current fetch.",
                PAD + 16,
                y - 48,
                width - PAD * 2 - 32,
                18,
                size=12,
                secondary=True,
            )
        y = self._section(doc, "MODELS", y, "cpu")
        total = sum(model.total_cents for model in models) or 1
        if not models:
            self._label(
                doc,
                "No per-model events for this user yet.",
                PAD,
                y,
                width - PAD * 2,
                18,
                size=12,
                secondary=True,
            )
            return y + 22
        for model in models:
            y = self._model_row(doc, model, total, y, width, nested=False)
        return y

    @python_method
    def _pool_pie(self, doc, pool, y, width):
        cursor, other = pool
        y = self._section(doc, "CURSOR VS OTHER", y, "chart.pie")
        card = make_card(NSMakeRect(PAD, y, width - PAD * 2, 118), self.theme, 16)
        pie = PieView.alloc().initWithFrame_cursor_other_theme_(
            NSMakeRect(16, 10, 98, 98), cursor, other, self.theme
        )
        card.addSubview_(pie)
        total = cursor + other
        cursor_pct = int(round(100 * cursor / total)) if total else 0
        other_pct = 100 - cursor_pct if total else 0
        add_symbol(card, "circle.fill", 132, 28, 10, theme_color(self.theme, "accent"))
        self._label(card, "Cursor models", 148, 24, 220, 18, size=13, bold=True)
        self._label(
            card,
            f"{dollars(cursor)} · {cursor_pct}%",
            148,
            42,
            220,
            16,
            size=12,
            secondary=True,
        )
        add_symbol(card, "circle.fill", 132, 70, 10, theme_color(self.theme, "other"))
        self._label(card, "Other models", 148, 66, 220, 18, size=13, bold=True)
        self._label(
            card,
            f"{dollars(other)} · {other_pct}%",
            148,
            84,
            220,
            16,
            size=12,
            secondary=True,
        )
        doc.addSubview_(card)
        return y + 130

    @python_method
    def _top_models(self, doc, models, y, width):
        y = self._section(doc, "TOP 3 MODELS", y, "cpu")
        card_w = width - PAD * 2
        gap = 10
        tile_w = (card_w - gap * 2) // 3
        total = sum(model.total_cents for model in models) or 1
        for index in range(3):
            x = PAD + index * (tile_w + gap)
            if index < len(models):
                model = models[index]
                pct = int(round(100 * model.total_cents / total)) if total else 0
                self._tile(
                    doc,
                    x,
                    y,
                    tile_w,
                    72,
                    "cpu",
                    f"#{index + 1} · {model.request_count} req",
                    model.label,
                )
                self._label(
                    doc,
                    f"{dollars(model.total_cents)} · {pct}%",
                    x + 10,
                    y + 52,
                    tile_w - 20,
                    16,
                    size=11,
                    secondary=True,
                )
            else:
                self._tile(doc, x, y, tile_w, 72, "cpu", f"#{index + 1}", "—")
        return y + 86

    @python_method
    def _hero(self, doc, snap, y, width, users_count=None):
        card_w = width - PAD * 2
        card = make_card(NSMakeRect(PAD, y, card_w, 168), self.theme, 20)
        gauge = GaugeView.alloc().initWithFrame_percent_theme_(
            NSMakeRect(14, 16, 136, 136), snap.percent, self.theme
        )
        card.addSubview_(gauge)
        spent = dollars(snap.spent_cents) if snap.spent_cents is not None else "—"
        budget = dollars(snap.limit_cents) if snap.limit_cents else "—"
        remaining = dollars(snap.remaining_cents) if snap.remaining_cents is not None else "—"
        budget_title = "Global budget" if snap.scope == "team" else "Monthly budget"
        tile_w = (card_w - 178 - 16) // 2
        tiles = (
            ("dollarsign.circle", "Spent", spent),
            ("creditcard", budget_title, budget),
            ("arrow.uturn.backward", "Remaining", remaining),
            ("person.2", "People", "—" if users_count is None else str(users_count)),
        )
        for index, (symbol, title, value) in enumerate(tiles):
            col = index % 2
            row = index // 2
            self._tile(
                card,
                162 + col * (tile_w + 10),
                16 + row * 72,
                tile_w,
                64,
                symbol,
                title,
                value,
            )
        doc.addSubview_(card)
        y += 180
        caption = actual_usage_caption(snap.percent, users_count, scope=snap.scope)
        self._label(doc, caption, PAD + 4, y - 8, card_w, 16, size=11, secondary=True)
        forecast = cursor_model_forecast(snap)
        if forecast is None:
            title = "If you'd used only Cursor models · —"
            sub = "Not enough token data to estimate"
            fraction = 0.0
        else:
            title, sub = forecast_card_captions(forecast)
            fraction = 0.0 if forecast.percent is None else min(1.0, forecast.percent / 100.0)
        y = self._section(doc, title.upper() if len(title) < 40 else title, y + 6, "sparkles")
        bar = GlowBarView.alloc().initWithFrame_fraction_color_(
            NSMakeRect(PAD, y, card_w, 10),
            fraction,
            theme_color(self.theme, "accent"),
        )
        doc.addSubview_(bar)
        self._label(doc, sub, PAD, y + 16, card_w, 16, size=11, secondary=True)
        return y + 42

    @python_method
    def _tile(self, parent, x, y, w, h, symbol, title, value):
        tile = make_card(NSMakeRect(x, y, w, h), self.theme, 14)
        try:
            tile.layer().setBackgroundColor_(theme_color(self.theme, "tile").CGColor())
        except Exception:
            pass
        add_symbol(tile, symbol, 10, 10, 14, theme_color(self.theme, "accent"))
        self._label(tile, title, 30, 10, w - 40, 14, size=10, secondary=True)
        field = self._label(tile, value, 10, 28, w - 20, 26, size=16, bold=True)
        try:
            field.setFont_(money_font(16))
        except Exception:
            pass
        parent.addSubview_(tile)

    @python_method
    def _section(self, doc, title, y, symbol=None):
        if symbol:
            add_symbol(doc, symbol, PAD, y + 1, 13, theme_color(self.theme, "accent"))
            self._label(doc, title, PAD + 20, y, 520, 16, size=11, bold=True, secondary=True)
        else:
            self._label(doc, title, PAD, y, 520, 16, size=11, bold=True, secondary=True)
        return y + 22

    @python_method
    def _toolbar(self, doc, y, width, query, extra):
        frame = NSMakeRect(PAD, y, 220, 26)
        search = self._search if self._keep_search_focus and self._search is not None else None
        if search is not None:
            search.removeFromSuperview()
            search.setFrame_(frame)
            if str(search.stringValue() or "") != query:
                search.setStringValue_(query)
        else:
            search = NSSearchField.alloc().initWithFrame_(frame)
            search.setStringValue_(query)
            search.setPlaceholderString_("Filter…")
            search.setDelegate_(self)
        doc.addSubview_(search)
        self._search = search
        if extra == "models":
            pool = NSPopUpButton.alloc().initWithFrame_pullsDown_(
                NSMakeRect(PAD + 232, y, 150, 26), False
            )
            pool.addItemsWithTitles_([MODEL_FILTER_LABELS[key] for key in MODEL_FILTERS])
            pool.selectItemAtIndex_(MODEL_FILTERS.index(self.model_filter))
            pool.setTarget_(self)
            pool.setAction_("filterChanged:")
            doc.addSubview_(pool)
            by = NSPopUpButton.alloc().initWithFrame_pullsDown_(
                NSMakeRect(width - PAD - 210, y, 110, 26), False
            )
            by.addItemsWithTitles_(list(MODEL_SORT_LABELS))
            by.selectItemAtIndex_(MODEL_SORTS.index(self.model_sort))
            by.setTarget_(self)
            by.setAction_("modelSortChanged:")
            doc.addSubview_(by)
            direction = NSPopUpButton.alloc().initWithFrame_pullsDown_(
                NSMakeRect(width - PAD - 92, y, 92, 26), False
            )
            direction.addItemsWithTitles_(["Desc", "Asc"])
            direction.selectItemAtIndex_(0 if self.model_sort_desc else 1)
            direction.setTarget_(self)
            direction.setAction_("modelDirChanged:")
            doc.addSubview_(direction)
        else:
            spike = NSPopUpButton.alloc().initWithFrame_pullsDown_(
                NSMakeRect(PAD + 232, y, 130, 26), False
            )
            spike.addItemsWithTitles_(["All users", "Spikes only"])
            spike.selectItemAtIndex_(1 if self.spikes_only else 0)
            spike.setTarget_(self)
            spike.setAction_("spikeFilterChanged:")
            doc.addSubview_(spike)
            by = NSPopUpButton.alloc().initWithFrame_pullsDown_(
                NSMakeRect(width - PAD - 210, y, 110, 26), False
            )
            by.addItemsWithTitles_(list(SORT_BY_LABELS))
            by.selectItemAtIndex_(
                SORT_BY_OPTIONS.index(self.user_sort)
                if self.user_sort in SORT_BY_OPTIONS
                else 0
            )
            by.setTarget_(self)
            by.setAction_("sortByChanged:")
            doc.addSubview_(by)
            direction = NSPopUpButton.alloc().initWithFrame_pullsDown_(
                NSMakeRect(width - PAD - 92, y, 92, 26), False
            )
            direction.addItemsWithTitles_(["Desc", "Asc"])
            direction.selectItemAtIndex_(0 if self.user_sort_desc else 1)
            direction.setTarget_(self)
            direction.setAction_("sortDirChanged:")
            doc.addSubview_(direction)
        return y + 36

    @python_method
    def _model_row(self, doc, model, total, y, width, nested=False):
        x = PAD + (36 if nested else 0)
        row_w = width - PAD * 2 - (36 if nested else 0)
        card = make_card(NSMakeRect(x, y, row_w, MODEL_ROW_H - 10), self.theme, 16)
        frac = min(1.0, model.total_cents / total) if total else 0
        chip = AvatarView.alloc().initWithFrame_name_color_(
            NSMakeRect(12, 18, 32, 32), model.label, _color_for(model.label)
        )
        card.addSubview_(chip)
        self._label(card, model.label, 54, 10, row_w - 180, 18, size=13, bold=not nested)
        self._label(
            card,
            f"{dollars(model.total_cents)} · {int(round(100 * frac))}%",
            row_w - 150,
            10,
            134,
            18,
            size=12,
            secondary=True,
        )
        if model.is_auto and not nested:
            button = NSButton.alloc().initWithFrame_(NSMakeRect(row_w - 178, 8, 24, 22))
            button.setBezelStyle_(5)
            button.setTitle_("›" if not self.auto_expanded else "˅")
            button.setTarget_(self)
            button.setAction_("toggleAuto:")
            card.addSubview_(button)
        bar = GlowBarView.alloc().initWithFrame_fraction_color_(
            NSMakeRect(54, 34, row_w - 74, 8), frac, _color_for(model.label)
        )
        card.addSubview_(bar)
        tokens = f"{model.input_tokens:,} in / {model.output_tokens:,} out"
        if nested or model.request_count:
            tokens = f"{model.request_count} requests · {tokens}"
        self._label(card, tokens, 54, 48, row_w - 74, 16, size=11, secondary=True)
        doc.addSubview_(card)
        return y + (CHILD_H if nested else MODEL_ROW_H)

    @python_method
    def _user_row(self, doc, member, y, width, spike=False, now_ms=None, clickable=False):
        row_w = width - PAD * 2
        card = make_card(NSMakeRect(PAD, y, row_w, USER_ROW_H - 10), self.theme, 16)
        name = member.name or member.email or str(member.user_id)
        frac = member_cap_fraction(member)
        pct = member_cap_percent(member)
        spent = dollars(member.spend_cents)
        amount = f"{spent} · {pct}%" if pct is not None else spent
        avatar = AvatarView.alloc().initWithFrame_name_color_(
            NSMakeRect(14, 22, 42, 42), name, _color_for(name)
        )
        card.addSubview_(avatar)
        self._label(card, name, 68, 12, row_w - 240, 18, size=13, bold=True)
        self._label(card, amount, row_w - 168, 12, 150, 18, size=12, secondary=True)
        if spike:
            reason = burst_reason(self.snapshot.events, member, now_ms=now_ms or _now_ms())
            add_symbol(card, "flame.fill", row_w - 280, 14, 12, theme_color(self.theme, "spike"))
            self._label(
                card,
                reason or "Spike",
                row_w - 264,
                12,
                92,
                18,
                size=11,
                color=theme_color(self.theme, "spike"),
            )
        bar = GlowBarView.alloc().initWithFrame_fraction_color_(
            NSMakeRect(68, 36, row_w - 92, 8),
            frac,
            theme_color(self.theme, "spike") if spike else usage_tone(self.theme, pct),
        )
        card.addSubview_(bar)
        detail = member.email or f"User {member.user_id}"
        if member.limit_cents:
            detail = f"{detail} · cap {dollars(member.limit_cents)}"
        self._label(card, detail, 68, 50, row_w - 160, 16, size=11, secondary=True)
        if clickable:
            add_symbol(card, "chevron.right", row_w - 28, 52, 12, theme_color(self.theme, "muted"))
            hit = UserHitRow.alloc().initWithFrame_userId_target_(
                NSMakeRect(0, 0, row_w, USER_ROW_H - 10),
                member.user_id,
                self,
            )
            card.addSubview_(hit)
        doc.addSubview_(card)
        return y + USER_ROW_H

    @python_method
    def _footer(self, doc, y, width):
        add_symbol(doc, "info.circle", PAD, y + 12, 12, theme_color(self.theme, "muted"))
        self._label(
            doc,
            "Unofficial Cursor APIs — they can change or break without notice.",
            PAD + 18,
            y + 8,
            width - PAD * 2 - 18,
            32,
            size=11,
            secondary=True,
        )

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
            field.setTextColor_(theme_color(self.theme, "muted"))
        elif color is not None:
            field.setTextColor_(color)
        else:
            field.setTextColor_(theme_color(self.theme, "text"))
        parent.addSubview_(field)
        return field


def _now_ms() -> int:
    return int(time.time() * 1000)


def _when(ms: int | None) -> str:
    if not ms:
        return "—"
    return time.strftime("%b %d, %H:%M", time.localtime(ms / 1000))


def show_workspace(snapshot: UsageSnapshot, tab: str | None = None) -> None:
    WorkspaceController.shared().show_tab_(snapshot, tab)


def refresh_workspace_if_visible(snapshot: UsageSnapshot) -> None:
    ctrl = WorkspaceController._instance
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
