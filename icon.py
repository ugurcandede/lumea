"""App icons.

`app_icon()` is the static project icon (window / taskbar). `make_icon()` draws
the dynamic tray icon that reflects the current strip color, straight into a
QPixmap (no image-library round trip).
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

_SIZE = 64
_ICON_FILE = Path(__file__).resolve().parent / "assets" / "icon.png"


def app_icon() -> QIcon:
    """The static project icon (window / taskbar)."""
    return QIcon(str(_ICON_FILE))


def make_icon(color: QColor) -> QIcon:
    """A filled circle in `color` -- used as the tray icon (reflects the strip color)."""
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(color)
    painter.setPen(QPen(QColor(40, 40, 40), 2))
    painter.drawEllipse(7, 7, _SIZE - 14, _SIZE - 14)
    painter.end()
    return QIcon(pixmap)
