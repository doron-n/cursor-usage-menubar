import unittest
from unittest.mock import Mock, patch

from cursor_usage_menubar.app import (
    handle_dock_reopen,
    pin_status_item_title,
    set_dock_badge,
)


class SetDockBadgeTest(unittest.TestCase):
    def test_sets_percent_badge(self):
        tile = Mock()
        app = Mock()
        app.dockTile.return_value = tile
        with patch("cursor_usage_menubar.app.NSApplication") as ns:
            ns.sharedApplication.return_value = app
            set_dock_badge(18)
        tile.setBadgeLabel_.assert_called_once_with("18%")

    def test_clears_badge_when_unknown(self):
        tile = Mock()
        app = Mock()
        app.dockTile.return_value = tile
        with patch("cursor_usage_menubar.app.NSApplication") as ns:
            ns.sharedApplication.return_value = app
            set_dock_badge(None)
        tile.setBadgeLabel_.assert_called_once_with("")

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
