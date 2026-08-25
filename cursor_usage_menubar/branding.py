from __future__ import annotations

from pathlib import Path

ICON_FILE = "app-icon.png"


def icon_path() -> Path:
    return Path(__file__).resolve().parent / "assets" / ICON_FILE


def app_icon():
    from AppKit import NSImage

    path = icon_path()
    if not path.is_file():
        return None
    return NSImage.alloc().initWithContentsOfFile_(str(path))


def apply_app_icon() -> None:
    image = app_icon()
    if image is None:
        return
    try:
        from AppKit import NSApplication

        NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception:
        return
