"""Light theme stylesheet — shared visual language with the HomeWhiz app.

The look: a soft grey page (#EEF2F6) with white, rounded cards (18px) that
*float* on it via a soft drop shadow (applied in code) — that grey/white
contrast is the figure/ground separation. A single blue accent (#2563EB) on
neutral greys; muted section labels above pill controls; a full-width power
toggle that turns blue when on; status chips. Apply once on the QApplication;
widgets opt in via objectName.
"""

# -- palette (inlined in the QSS below) ------------------------------------
# page #EEF2F6  card #FFFFFF  border #E9EDF3  inset #F4F6FA
# text #1B2430  muted #6B7785  faint #9AA4B1
# primary #2563EB  hover #1D4ED8  ok-bg #E4F6EC  ok-fg #1B7F4B

STYLESHEET = """
* {
    font-family: "Segoe UI", "SF Pro Text", system-ui, sans-serif;
}

QWidget#root { background-color: #EEF2F6; }
QWidget#titleBar { background: transparent; }

/* Custom window controls (frameless window draws its own title bar). */
QPushButton#winBtn, QPushButton#winClose {
    background: transparent;
    border: none;
    color: #6B7785;
    font-size: 13px;
    font-weight: 700;
    min-width: 30px; max-width: 30px;
    min-height: 26px; max-height: 26px;
    border-radius: 7px;
}
QPushButton#winBtn:hover { background-color: #E1E6EE; color: #1B2430; }
QPushButton#winClose:hover { background-color: #DC2626; color: #FFFFFF; }

QLabel {
    color: #1B2430;
    font-size: 14px;
    background: transparent;
}
QLabel#h1 { font-size: 22px; font-weight: 700; }
QLabel#subtitle { color: #6B7785; font-size: 13px; }
QLabel#fieldLabel { color: #6B7785; font-size: 12px; font-weight: 600; }
QLabel#cardTitle { font-size: 15px; font-weight: 600; color: #1B2430; }
QLabel#cardSub { font-size: 12px; color: #8A93A1; }
QLabel#hint { color: #8A93A1; font-size: 12px; }
QLabel#status { color: #6B7785; font-size: 13px; }
QLabel#heroHex { color: #6B7785; font-size: 13px; font-weight: 600; }
QLabel#footer { color: #9AA4B1; font-size: 11px; padding-top: 2px; }
QLabel#footer a { color: #9AA4B1; text-decoration: none; }

/* Floating white cards (drop shadow added in code). */
QFrame#card {
    background-color: #FFFFFF;
    border: 1px solid #E9EDF3;
    border-radius: 18px;
}

/* Full-width primary action. */
QPushButton#primary {
    background-color: #2563EB;
    color: #FFFFFF;
    border: none;
    border-radius: 12px;
    padding: 12px 18px;
    font-size: 15px;
    font-weight: 600;
}
QPushButton#primary:hover { background-color: #1D4ED8; }
QPushButton#primary:pressed { background-color: #1A45C2; }
QPushButton#primary:disabled { background-color: #A9C0F2; }

/* The power toggle: grey when off, solid blue when on. Compact, hugs its text. */
QPushButton#power {
    background-color: #E7ECF3;
    color: #5B6573;
    border: none;
    border-radius: 9px;
    padding: 7px 22px;
    font-size: 13px;
    font-weight: 700;
    min-width: 84px;
}
QPushButton#power:hover { background-color: #DCE3EC; }
QPushButton#power[on="true"] { background-color: #2563EB; color: #FFFFFF; }
QPushButton#power[on="true"]:hover { background-color: #1D4ED8; }

/* Secondary pill buttons (Scan / Disconnect). */
QPushButton#pill {
    background-color: #FFFFFF;
    color: #41505F;
    border: 1px solid #D6DCE5;
    border-radius: 10px;
    padding: 11px 16px;
    font-size: 14px;
    font-weight: 600;
}
QPushButton#pill:hover { border-color: #2563EB; color: #2563EB; }
QPushButton#pill:pressed { background-color: #F1F4F9; }
QPushButton#pill:disabled { color: #B5BDC8; border-color: #E5E9F0; }

/* Compact per-device effect dropdown (Static / Rainbow) inside a device row. */
QPushButton#effectMenu {
    background: #FFFFFF;
    color: #41505F;
    border: 1px solid #D6DCE5;
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#effectMenu:hover { border-color: #2563EB; color: #2563EB; }

/* Device rows: light inset panels inside the white card → clear separation.
   Blue-tinted with a blue border when ticked into the control group. */
QFrame#deviceRow {
    background-color: #F4F6FA;
    border: 1px solid #F4F6FA;
    border-radius: 12px;
}
QFrame#deviceRow:hover { background-color: #EEF2F8; border-color: #DCE3EC; }
QFrame#deviceRow[selected="true"] {
    background-color: #EAF1FE;
    border: 1px solid #2563EB;
}
/* A saved strip absent from the last scan: dimmed, clearly inactive. */
QFrame#deviceRow[unavailable="true"] {
    background-color: #F1F3F7;
    border-color: #EAEDF2;
}
QFrame#deviceRow[unavailable="true"] QLabel#cardTitle { color: #A3ABB7; }
QFrame#deviceRow[unavailable="true"] QLabel#cardSub { color: #B4BAC5; }

QScrollArea#deviceScroll { background: transparent; border: none; }
QScrollArea#deviceScroll > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical {
    background: #CBD3DE; border-radius: 4px; min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: #B4BECC; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QCheckBox { spacing: 0; }
QCheckBox::indicator {
    width: 20px; height: 20px;
    border: 1px solid #C2CAD6;
    border-radius: 6px;
    background: #FFFFFF;
}
QCheckBox::indicator:hover { border-color: #2563EB; }
QCheckBox::indicator:checked {
    background: #2563EB;
    border-color: #2563EB;
    image: none;
}
QCheckBox::indicator:disabled { background: #EDEFF3; border-color: #DDE2EA; }

QLabel#chip {
    font-size: 12px;
    font-weight: 600;
    padding: 5px 12px;
    border-radius: 11px;
    background-color: #EAEDF1;
    color: #6B7785;
}
QLabel#chip[connected="true"] { background-color: #E4F6EC; color: #1B7F4B; }
QLabel#chip[stale="true"] { background-color: #ECEEF2; color: #9AA4B1; }

/* Rename popup + tray menu inherit the app sheet — keep them on-brand. */
QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #D6DCE5;
    border-radius: 10px;
    padding: 9px 12px;
    font-size: 14px;
    color: #1B2430;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
}
QLineEdit:focus { border: 1px solid #2563EB; }
QLineEdit#hexInput {
    padding: 6px 10px;
    font-size: 13px;
    font-weight: 600;
    color: #41505F;
    min-width: 86px;
    max-width: 100px;
}
QMenu {
    background-color: #FFFFFF;
    border: 1px solid #E3E8EF;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 18px;
    border-radius: 7px;
    color: #1B2430;
    font-size: 13px;
}
QMenu::item:selected { background-color: #EFF4FF; color: #1B2430; }
QMenu::separator { height: 1px; background: #E9EDF3; margin: 5px 8px; }

/* Brightness master dimmer: grey groove, blue fill, white handle. */
QSlider#brightness::groove:horizontal {
    height: 6px; border-radius: 3px; background: #E7ECF3;
}
QSlider#brightness::sub-page:horizontal {
    height: 6px; border-radius: 3px; background: #2563EB;
}
QSlider#brightness::add-page:horizontal {
    height: 6px; border-radius: 3px; background: #E7ECF3;
}
QSlider#brightness::handle:horizontal {
    width: 18px; height: 18px; margin: -6px 0;
    border-radius: 9px; background: #FFFFFF; border: 2px solid #2563EB;
}
QSlider#brightness::handle:horizontal:hover { border-color: #1D4ED8; }
"""
