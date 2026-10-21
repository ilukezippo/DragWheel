"""Dark / light theme. Colours are read from here by every window, so switching is instant.

mode: "system" (follow Windows' app theme), "dark" or "light".
Stylesheets are written as templates with $tokens (e.g. "$bg", "$text") and filled by sheet().
"""
from __future__ import annotations

import sys
from string import Template

DARK = {
    "bg": "#1c1c1e", "surface": "#2c2c2e", "border": "#3a3a3c", "button": "#3a3a3c", "hover": "#48484a",
    "text": "#f5f5f7", "dim": "#a1a1a6", "faint": "#8e8e93", "side": "#232326",
    "canvas": "#141416", "check_a": "#2a2a2d", "check_b": "#222225",
    "accent": "#ff8a00", "accent2": "#ffb347", "on_accent": "#1c1c1e",
    "danger": "#ff453a", "ok": "#30d158", "link": "#ffb347",
}
LIGHT = {
    "bg": "#f5f5f7", "surface": "#ffffff", "border": "#d1d1d6", "button": "#e5e5ea", "hover": "#d8d8dd",
    "text": "#1c1c1e", "dim": "#6e6e73", "faint": "#8e8e93", "side": "#ebebf0",
    "canvas": "#dcdce1", "check_a": "#cfcfd4", "check_b": "#e4e4e9",
    "accent": "#ff8a00", "accent2": "#ffb347", "on_accent": "#1c1c1e",
    "danger": "#e0352b", "ok": "#28a745", "link": "#c25e00",
}

# translucent colours for painted surfaces (r, g, b, a)
DARK_RGBA = {
    "panel": (28, 28, 30, 238),        # wheel disc, toast, float
    "ring": (44, 44, 46, 245),         # wheel centre
    "ring_hover": (58, 58, 60, 250),
    "wedge": (255, 255, 255, 10),      # idle slice tint
    "line": (255, 255, 255, 28),       # outlines
    "shadow": (0, 0, 0, 90),
    "grip": (255, 255, 255, 28),
    "close": (0, 0, 0, 150),
    "busy_track": (255, 255, 255, 40),
}
LIGHT_RGBA = {
    "panel": (250, 250, 252, 242),
    "ring": (232, 232, 237, 250),
    "ring_hover": (214, 214, 220, 252),
    "wedge": (0, 0, 0, 9),
    "line": (0, 0, 0, 30),
    "shadow": (0, 0, 0, 55),
    "grip": (0, 0, 0, 18),
    "close": (0, 0, 0, 90),
    "busy_track": (0, 0, 0, 30),
}

_mode = "system"


def set_mode(mode: str | None):
    global _mode
    _mode = mode if mode in ("dark", "light") else "system"


def mode() -> str:
    return _mode


def _windows_prefers_dark() -> bool | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return None


def is_dark() -> bool:
    if _mode == "dark":
        return True
    if _mode == "light":
        return False
    win = _windows_prefers_dark()
    if win is not None:
        return win
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Light
    except Exception:
        return True


def pal() -> dict:
    return DARK if is_dark() else LIGHT


def hexc(name: str) -> str:
    return pal()[name]


def color(name: str):
    """QColor for a palette entry (hex or translucent)."""
    from PySide6.QtGui import QColor
    rgba = (DARK_RGBA if is_dark() else LIGHT_RGBA).get(name)
    if rgba:
        return QColor(*rgba)
    return QColor(pal()[name])


def sheet(template: str) -> str:
    return Template(template).safe_substitute(pal())
