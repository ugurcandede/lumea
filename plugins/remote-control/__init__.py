"""Remote control: drive Lumea from a phone, tablet or another PC's browser on the
same network. Pair once with the PIN (or the QR) shown on the Plugins page.

server.py serves the page and the WebSocket on one port, pairing.py decides who may
connect, panel.py is the Plugins-page panel. See plugins/README.md for the plugin
contract.
"""

from PySide6.QtCore import QSettings

from .pairing import Pairing
from .panel import Panel
from .server import DEFAULT_PORT, Server, lan_addresses

_PORT_KEY = "plugin_remote-control/port"


class Plugin:
    def __init__(self, api):
        self.api = api
        self.pairing = Pairing()
        port = QSettings().value(_PORT_KEY, DEFAULT_PORT, type=int)
        self.server = Server(api, self.pairing, port)     # raises if the port is taken
        api.show_status(f"Remote control: {self.address()}")

    def stop(self):
        self.server.stop()

    def settings_widget(self):
        return Panel(self)

    def address(self):
        ips = lan_addresses()
        return f"http://{ips[0] if ips else 'localhost'}:{self.server.port}"

    def set_port(self, port):
        """Move to another port. Raises (and keeps the current one) if it's taken."""
        if port == self.server.port:
            return
        new = Server(self.api, self.pairing, port)
        self.server.stop()
        self.server = new
        QSettings().setValue(_PORT_KEY, port)
        self.api.show_status(f"Remote control moved to {self.address()}")

    def reset(self):
        self.pairing.reset()
        self.server.drop_clients()
