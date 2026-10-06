"""The Remote control panel on the Plugins page: address, PIN, QR, devices, port."""

import segno
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from .server import lan_addresses

QR_SIZE = 116


def pair_url(ip, port, pin):
    """What the QR holds: the page pairs itself with the PIN from the URL."""
    return f"http://{ip}:{port}/?pin={pin}"


class Panel(QWidget):
    def __init__(self, plugin):
        super().__init__()
        self._plugin = plugin

        self._qr = QLabel()
        self._qr.setFixedSize(QR_SIZE, QR_SIZE)
        self._info = QLabel()
        self._info.setWordWrap(True)
        self._info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        reset = QPushButton("Reset pairings")
        reset.setToolTip("New PIN; every paired phone has to pair again")
        reset.clicked.connect(self._reset)

        self._port = QSpinBox()
        self._port.setRange(1024, 65535)
        self._port.setFixedWidth(84)        # its default (~117 px) pushes the row past the page
        self._port.setValue(plugin.server.port)
        self._port.setToolTip("The port phones connect to. Pick another if something else uses it.")
        apply = QPushButton("Apply")
        apply.clicked.connect(self._apply_port)
        self._port_note = QLabel()
        self._port_note.setWordWrap(True)
        port_row = QHBoxLayout()
        port_row.setContentsMargins(0, 0, 0, 0)
        port_row.addWidget(QLabel("Port"))
        port_row.addWidget(self._port)
        port_row.addWidget(apply)
        port_row.addStretch()

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.addWidget(self._info, 1)
        text.addLayout(port_row)
        text.addWidget(self._port_note)
        text.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(12)
        lay.addWidget(self._qr, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(text, 1)

        self._watch()
        self.refresh()

    def _watch(self):
        # Bound method of this widget: Qt drops it when the Plugins page rebuilds the panel.
        self._plugin.server.clients_changed.connect(self.refresh)

    def refresh(self):
        plugin = self._plugin
        pin, port = plugin.pairing.pin, plugin.server.port
        ips = lan_addresses() or ["127.0.0.1"]
        n = plugin.server.paired_clients
        self._info.setText(
            "Scan with your phone, or open<br>"
            f"<b>http://{ips[0]}:{port}</b> and enter PIN <b>{pin[:3]} {pin[3:]}</b>"
            + (f"<br>Also on: {', '.join(ips[1:])}" if len(ips) > 1 else "")
            + f"<br>{n} device{'s' if n != 1 else ''} connected")
        pixmap = QPixmap()
        pixmap.loadFromData(_qr_png(pair_url(ips[0], port, pin)), "PNG")
        self._qr.setPixmap(pixmap.scaled(QR_SIZE, QR_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.FastTransformation))

    def _apply_port(self):
        try:
            self._plugin.set_port(self._port.value())
        except OSError as e:
            self._port_note.setText(f"Couldn't use it: {e}. Still on {self._plugin.server.port}.")
            self._port.setValue(self._plugin.server.port)
            return
        self._port_note.setText("Phones paired before still work; open the new address on them.")
        self._watch()
        self.refresh()

    def _reset(self):
        self._plugin.reset()                # drop_clients -> clients_changed -> refresh


def _qr_png(text):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    segno.make(text, error="m").save(buf, kind="png", scale=4, border=2)
    buf.close()
    return bytes(data)
