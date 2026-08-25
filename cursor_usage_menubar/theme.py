from __future__ import annotations

from AppKit import NSColor

DARK = {
    "bg": (0.027, 0.031, 0.047, 1),
    "card": (0.071, 0.078, 0.118, 1),
    "tile": (0.098, 0.106, 0.157, 1),
    "line": (1, 1, 1, 0.08),
    "text": (0.93, 0.95, 0.97, 1),
    "muted": (0.55, 0.60, 0.68, 1),
    "accent": (0.239, 1.0, 0.824, 1),
    "accent_dim": (0.239, 1.0, 0.824, 0.18),
    "spike": (1.0, 0.42, 0.29, 1),
    "warn": (0.96, 0.76, 0.32, 1),
    "track": (1, 1, 1, 0.08),
    "bar": (0.239, 1.0, 0.824, 0.95),
    "other": (0.55, 0.47, 0.98, 1),
}

LIGHT = {
    "bg": (0.945, 0.941, 0.925, 1),
    "card": (1, 1, 1, 1),
    "tile": (0.965, 0.962, 0.95, 1),
    "line": (0.08, 0.09, 0.12, 0.1),
    "text": (0.10, 0.12, 0.16, 1),
    "muted": (0.38, 0.42, 0.48, 1),
    "accent": (0.02, 0.62, 0.54, 1),
    "accent_dim": (0.02, 0.62, 0.54, 0.14),
    "spike": (0.82, 0.22, 0.16, 1),
    "warn": (0.72, 0.48, 0.08, 1),
    "track": (0, 0, 0, 0.08),
    "bar": (0.02, 0.62, 0.54, 0.95),
    "other": (0.38, 0.32, 0.78, 1),
}

THEMES = ("dark", "light")


def as_theme(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in THEMES else "dark"


def theme_color(theme: str, role: str) -> NSColor:
    palette = LIGHT if as_theme(theme) == "light" else DARK
    red, green, blue, alpha = palette[role]
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, alpha)


def appearance_name(theme: str) -> str:
    return "NSAppearanceNameAqua" if as_theme(theme) == "light" else "NSAppearanceNameDarkAqua"


def usage_tone(theme: str, percent: int | None) -> NSColor:
    if percent is not None and percent >= 90:
        return theme_color(theme, "spike")
    if percent is not None and percent >= 75:
        return theme_color(theme, "warn")
    return theme_color(theme, "accent")
