"""Theme: two palettes (light / dark) and the QSS built from them.

The UI is achromatic on purpose: the only colour on the page is the one being
sent to the strips, so it never competes with an accent. Widgets opt into the
sheet via objectName / dynamic properties; custom-painted widgets (checkbox,
switch, picker) read `current` for the same tokens. `apply()` swaps both at
runtime, so a theme change needs no restart.
"""

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

PALETTES = {
    "light": dict(
        panel="#FFFFFF", inset="#F3F4F7", hover="#EAECF0", line="#E5E7EB",
        ink="#16181D", muted="#6B7280", faint="#A0A6B1",
        primary_bg="#16181D", primary_hover="#2A2D33", primary_fg="#FFFFFF",
        disabled_bg="#E9EBEF", disabled_fg="#A0A6B1", handle="#FFFFFF",
        ok="#1E8E5A", ok_dot="#22A06B", swatch_border="rgba(0,0,0,0.12)",
    ),
    "dark": dict(
        panel="#1A1C21", inset="#24272D", hover="#2B2F36", line="#2E3138",
        ink="#EEF0F3", muted="#9AA1AC", faint="#6B7280",
        primary_bg="#EEF0F3", primary_hover="#FFFFFF", primary_fg="#16181D",
        disabled_bg="#2A2D34", disabled_fg="#6B7280", handle="#EEF0F3",
        ok="#4ED39A", ok_dot="#3DCB8A", swatch_border="rgba(255,255,255,0.14)",
    ),
}

# The palette in force; custom-painted widgets read it at paint time.
current = dict(PALETTES["light"])

SANS = '"SF Pro Text", "Segoe UI", system-ui, sans-serif'
MONO = '"SF Mono", Menlo, Consolas, monospace'


def resolve(mode):
    """'auto' | 'light' | 'dark' -> the palette name to use."""
    if mode in PALETTES:
        return mode
    hints = QGuiApplication.styleHints()
    dark = getattr(hints, "colorScheme", None) and hints.colorScheme() == Qt.ColorScheme.Dark
    return "dark" if dark else "light"


def apply(app, mode):
    """Install the palette for `mode` on the app; returns the palette name."""
    name = resolve(mode)
    current.clear()
    current.update(PALETTES[name])
    app.setStyleSheet(_SHEET.substitute(current, sans=SANS, mono=MONO))
    return name


_SHEET = Template("""
* { font-family: $sans; font-size: 13px; color: $ink; }

/* Frameless translucent window; the rounded panel inside is the visible body. */
QWidget#window { background: transparent; }
QFrame#panel { background-color: $panel; border: 1px solid $line; border-radius: 14px; }
QWidget#titleBar, QLabel { background: transparent; }
QFrame#rule { background-color: $line; border: none; }

QLabel#appName { font-size: 14px; font-weight: 600; }
QLabel#sectionLabel { color: $muted; font-size: 12px; font-weight: 500; }
QLabel#connLabel, QLabel#statusText { color: $muted; font-size: 12px; }
QLabel#hint { color: $faint; font-size: 12px; }
QLabel#rowName { font-size: 13px; font-weight: 500; }
QLabel#rowSub { color: $muted; font-size: 11px; }
QLabel#value { color: $muted; font-size: 12px; font-weight: 500; font-family: $mono; }
QLabel#rowStatus { font-size: 12px; font-weight: 500; color: $muted; }
QLabel#rowStatus[state="ok"] { color: $ok; }
QLabel#rowStatus[state="stale"] { color: $faint; }
QLabel#menuHeader { padding: 4px 10px 6px 10px; }
QLabel#credits { font-size: 11px; color: $faint; line-height: 16px; }

/* Title-bar buttons (settings, minimize, close) -- icon only. */
QPushButton#winBtn {
    background: transparent; border: none; border-radius: 6px;
    min-width: 28px; max-width: 28px; min-height: 24px; max-height: 24px;
}
QPushButton#winBtn:hover { background-color: $inset; }

/* Edit-target chips: All + each live strip. Checked = ink-filled. */
QPushButton#chip {
    min-height: 24px; max-height: 24px; padding: 0 11px; border-radius: 13px;
    border: 1px solid $line; background-color: $panel; font-size: 12px; font-weight: 500;
}
QPushButton#chip:hover { border-color: $muted; }
QPushButton#chip:checked { background-color: $primary_bg; color: $primary_fg; border-color: $primary_bg; }

QPushButton#ghost {
    min-height: 26px; max-height: 26px; padding: 0 12px; border-radius: 8px;
    border: 1px solid $line; background-color: $panel; font-size: 12px; font-weight: 500;
}
QPushButton#ghost:hover { border-color: $muted; }
QPushButton#ghost:disabled { color: $disabled_fg; }
QPushButton#primary {
    min-height: 28px; max-height: 28px; padding: 0 14px; border-radius: 8px; border: none;
    background-color: $primary_bg; color: $primary_fg; font-size: 12px; font-weight: 600;
}
QPushButton#primary:hover { background-color: $primary_hover; }
QPushButton#primary:disabled { background-color: $disabled_bg; color: $disabled_fg; }

/* Power pill: outlined when off, ink-filled when on. */
QPushButton#power {
    min-height: 24px; max-height: 24px; padding: 0 12px 0 10px; border-radius: 13px;
    border: 1px solid $line; background-color: $panel; color: $disabled_fg;
    font-size: 12px; font-weight: 600;
}
QPushButton#power:hover { border-color: $muted; }
QPushButton#power[on="true"] { background-color: $primary_bg; color: $primary_fg; border-color: $primary_bg; }
QPushButton#power:disabled { color: $disabled_fg; border-color: $disabled_bg; background-color: $panel; }

QPushButton#menuBtn {
    min-height: 22px; max-height: 22px; padding: 0 9px; border-radius: 7px;
    border: 1px solid $line; background-color: $panel; font-size: 12px; font-weight: 500;
}
QPushButton#menuBtn:hover { border-color: $muted; }

/* Segmented control (Settings > Theme). */
QWidget#segment { background-color: $inset; border-radius: 9px; }
QPushButton#segBtn {
    min-height: 22px; max-height: 22px; padding: 0 12px; border-radius: 7px; border: none;
    background: transparent; color: $muted; font-size: 12px; font-weight: 500;
}
QPushButton#segBtn:checked { background-color: $panel; color: $ink; font-weight: 600; }

/* Device rows: inset panels; focused = ink outline; stale = faint text. */
QFrame#deviceRow { background-color: $inset; border: 1px solid $inset; border-radius: 10px; }
QFrame#deviceRow:hover { background-color: $hover; border-color: $hover; }
QFrame#deviceRow[focused="true"] { border-color: $ink; }
QFrame#deviceRow[unavailable="true"] QLabel#rowName { color: $faint; }
QFrame#deviceRow[unavailable="true"] QLabel#rowSub { color: $faint; }
QFrame#emptyRow { border: 1px dashed $line; border-radius: 10px; }

QScrollArea#deviceScroll { background: transparent; border: none; }
QScrollArea#deviceScroll > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 2px; }
QScrollBar::handle:vertical { background: $line; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QLineEdit {
    background-color: $panel; border: 1px solid $line; border-radius: 8px; padding: 6px 10px;
    selection-background-color: $ink; selection-color: $panel;
}
QLineEdit:focus { border-color: $ink; }
QLineEdit#hexInput {
    background-color: $inset; border: 1px solid $inset; border-radius: 7px; padding: 0 4px;
    min-height: 22px; max-height: 22px; min-width: 62px; max-width: 62px;
    font-family: $mono; font-size: 12px; font-weight: 500;
}
QLineEdit#hexInput:focus { border-color: $ink; }
QLineEdit#hexInput:disabled { color: $faint; }

QSlider#brightness::groove:horizontal { height: 4px; border-radius: 2px; background: $inset; }
QSlider#brightness::sub-page:horizontal { height: 4px; border-radius: 2px; background: $primary_bg; }
QSlider#brightness::add-page:horizontal { height: 4px; border-radius: 2px; background: $inset; }
QSlider#brightness::handle:horizontal {
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
    background: $handle; border: 2px solid $primary_bg;
}
QSlider#brightness::sub-page:horizontal:disabled { background: $disabled_bg; }
QSlider#brightness::handle:horizontal:disabled { border-color: $disabled_bg; }

/* Menus (tray, row context, effect picker) share the panel look. */
QMenu { background-color: $panel; border: 1px solid $line; border-radius: 10px; padding: 6px; min-width: 190px; }
QMenu::item { padding: 6px 10px; border-radius: 6px; font-size: 13px; }
QMenu::item:selected { background-color: $inset; }
QMenu::item:disabled { color: $faint; }
QMenu::separator { height: 1px; background: $line; margin: 4px 6px; }
QMenu::icon { padding-left: 4px; }

QToolTip { background-color: $ink; color: $panel; border: none; padding: 4px 8px; font-size: 11px; }
QDialog { background-color: $panel; }
QDialog QPushButton {
    min-height: 26px; padding: 0 14px; border-radius: 8px;
    border: 1px solid $line; background-color: $panel; font-size: 12px; font-weight: 500;
}
QDialog QPushButton:default { background-color: $primary_bg; color: $primary_fg; border-color: $primary_bg; }
""")
