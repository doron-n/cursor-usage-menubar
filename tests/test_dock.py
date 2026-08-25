import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rumps import events
from rumps.rumps import NSApp

from cursor_usage_menubar.app import (
    CursorUsageApp,
    handle_dock_reopen,
    install_dock_reopen,
    pin_status_item_title,
    set_dock_badge,
)


class SetDockBadgeTest(unittest.TestCase):
    def test_sets_percent_badge(self):
        tile = Mock()
        app = Mock()
        app.dockTile.return_value = tile
        with (
            patch("cursor_usage_menubar.app.NSApplication") as ns,
            patch("cursor_usage_menubar.app.load_prefs", return_value={"dock_badge": True}),
        ):
            ns.sharedApplication.return_value = app
            set_dock_badge(18)
        tile.setBadgeLabel_.assert_called_once_with("18%")

    def test_clears_badge_when_pref_disabled(self):
        tile = Mock()
        app = Mock()
        app.dockTile.return_value = tile
        with (
            patch("cursor_usage_menubar.app.NSApplication") as ns,
            patch("cursor_usage_menubar.app.load_prefs", return_value={"dock_badge": False}),
        ):
            ns.sharedApplication.return_value = app
            set_dock_badge(18)
        tile.setBadgeLabel_.assert_called_once_with(None)

    def test_clears_badge_when_unknown(self):
        tile = Mock()
        app = Mock()
        app.dockTile.return_value = tile
        with (
            patch("cursor_usage_menubar.app.NSApplication") as ns,
            patch("cursor_usage_menubar.app.load_prefs", return_value={"dock_badge": True}),
        ):
            ns.sharedApplication.return_value = app
            set_dock_badge(None)
        tile.setBadgeLabel_.assert_called_once_with(None)

    def test_swallows_appkit_errors(self):
        with patch("cursor_usage_menubar.app.NSApplication") as ns:
            ns.sharedApplication.side_effect = RuntimeError("no app")
            set_dock_badge(18)


class PinStatusItemTitleTest(unittest.TestCase):
    def test_sets_button_title_and_visible(self):
        button = Mock()
        item = Mock()
        item.button.return_value = button
        nsapp = Mock(nsstatusitem=item)
        pin_status_item_title(nsapp, "18%")
        item.setVisible_.assert_called_once_with(True)
        button.setTitle_.assert_called_once_with("18%")

    def test_missing_item_is_noop(self):
        pin_status_item_title(Mock(spec=[]), "18%")


class HandleDockReopenTest(unittest.TestCase):
    def test_clicks_status_item_button(self):
        button = Mock()
        item = Mock()
        item.button.return_value = button
        nsapp = Mock(nsstatusitem=item)
        self.assertTrue(handle_dock_reopen(nsapp))
        button.performClick_.assert_called_once_with(None)

    def test_missing_item_still_returns_true(self):
        self.assertTrue(handle_dock_reopen(Mock(spec=[])))


class InstallDockReopenTest(unittest.TestCase):
    def test_installs_callable_on_rumps_nsapp(self):
        install_dock_reopen()
        self.assertTrue(
            callable(
                getattr(
                    NSApp,
                    "applicationShouldHandleReopen_hasVisibleWindows_",
                    None,
                )
            )
        )

    def test_swallows_install_errors(self):
        class RaisingTarget:
            def __setattr__(self, name, value):
                raise RuntimeError("PyObjC rejected method")

        fake_module = SimpleNamespace(NSApp=RaisingTarget())
        with patch.dict("sys.modules", {"rumps.rumps": fake_module}):
            install_dock_reopen()


class CursorUsageAppTest(unittest.TestCase):
    def test_uses_stable_application_name_and_placeholder_title(self):
        with patch("cursor_usage_menubar.app.rumps.App.__init__") as init:
            CursorUsageApp()
        init.assert_called_once_with(
            "Cursor Usage",
            title="—",
            quit_button=None,
        )

    def test_menu_keeps_workspace_and_settings_actions(self):
        import inspect

        source = inspect.getsource(CursorUsageApp._rebuild_info)
        self.assertIn("Open Cursor Usage", source)
        self.assertIn("Settings", source)
        self.assertIn("view_settings", source)
        self.assertNotIn("version_label", source)
        self.assertNotIn("Open Cursor Dashboard", source)

    def test_registers_before_start_callback_that_pins_current_title(self):
        self.assertIn(CursorUsageApp._pin_status_item_title, events.before_start.callbacks)
        item = Mock()
        button = Mock()
        item.button.return_value = button
        app = CursorUsageApp.__new__(CursorUsageApp)
        app._nsapp = Mock(nsstatusitem=item)
        app._title = "18%"

        app._pin_status_item_title()

        item.setVisible_.assert_called_once_with(True)
        button.setTitle_.assert_called_once_with("18%")
