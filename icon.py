"""App icons via Pillow.

`app_icon()` is the static project icon (window / taskbar). `make_icon()` draws
the dynamic tray icon that reflects the current strip color. Pillow is kept
isolated here so the dependency is easy to drop.
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtGui import QColor, QIcon, QPixmap

_SIZE = 64
_ICON_FILE = Path(__file__).resolve().parent / "assets" / "icon.png"


def app_icon() -> QIcon:
    """The static project icon (window / taskbar)."""
    return QIcon(str(_ICON_FILE))


def make_icon(color: QColor) -> QIcon:
    """A filled circle in `color` -- used as the tray icon (reflects the strip color)."""
    image = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        [6, 6, _SIZE - 6, _SIZE - 6],
        fill=(color.red(), color.green(), color.blue(), 255),
        outline=(40, 40, 40, 255),
        width=2,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return QIcon(pixmap)
