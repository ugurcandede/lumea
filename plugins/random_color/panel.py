from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class Panel(QWidget):
    """A live readout of the app state, plus one command button."""

    def __init__(self, api, on_random):
        super().__init__()
        self.api = api
        self.swatch = QLabel()
        self.swatch.setFixedSize(18, 18)
        self.text = QLabel()
        button = QPushButton("Random color")
        button.clicked.connect(on_random)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.swatch)
        lay.addWidget(self.text, 1)
        lay.addWidget(button)
        # Bound methods of this QWidget: Qt drops the connections when the panel
        # is deleted (the Plugins page rebuilds it), so no manual disconnect.
        api.changed.connect(self.refresh)
        api.frame.connect(self.show_frame)
        self.refresh()

    def refresh(self):
        s = self.api.state()
        live = s["effect"] or (f"music: {s['music']}" if s["music"] else None)
        self.text.setText(f"{'On' if s['power'] else 'Off'} · {s['color']} · {s['brightness']}%"
                          + (f" · {live}" if live else ""))
        if not live:
            self.paint(s["color"])

    def show_frame(self, color):
        self.paint(color)

    def paint(self, color):
        self.swatch.setStyleSheet(f"background:{color}; border-radius:9px; border:1px solid #8888;")
