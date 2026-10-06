"""The phone-facing side: one port serving the page and a WebSocket that carries
state and commands.

A plain QTcpServer takes every connection and looks at the request: a WebSocket
upgrade is handed to QWebSocketServer, anything else gets the page (or a 404).
QHttpServer isn't used: PySide6 can't hand a QHttpServerResponse back to C++, so
every response it sent was empty.

Protocol (JSON text frames on the WebSocket):

    browser -> Lumea   {"type": "hello", "token": "..."}        resume a pairing
                       {"type": "pair", "pin": "123456"}        pair; answered with a token
                       {"type": "cmd", "name": "set_color", "args": ["#ff0000"]}
    Lumea -> browser   {"type": "welcome", "name": "<PC>", "token": "..."(after pair)}
                       {"type": "denied", "reason": "..."}      then the socket closes
                       {"type": "state", "state": {...}}        LumeaAPI.state(), on every change
                       {"type": "frame", "color": "#rrggbb"}    effect / music colour, <= 10/s
                       {"type": "info", "port": 8765, "phones": 2, "peers": [{"name", "url"}]}
                                                                 this server and the other Lumea PCs
                                                                 found on the network (discovery.py)
                       {"type": "error", "message": "..."}      a command was refused

Nothing but "hello" / "pair" is accepted before a socket is paired. Commands are
an explicit allow-list of LumeaAPI methods with checked argument types.
"""

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QSysInfo, QTimer, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer
from PySide6.QtWebSockets import QWebSocketServer

from .discovery import Discovery, lan_addresses  # noqa: F401  (lan_addresses: used via .server)

log = logging.getLogger(__name__)

DEFAULT_PORT = 8765
FRAME_INTERVAL_MS = 100
_MAX_HEAD = 8192                    # request head larger than this is dropped
_PAGE = Path(__file__).with_name("page.html")

# name -> argument types (a tuple per argument; type(None) where None is allowed)
_NONE = type(None)
COMMANDS = {
    "set_power": ((bool,),),
    "set_color": ((str,),),
    "set_brightness": ((int,),),
    "apply_preset": ((int,),),
    "save_preset": ((int,),),
    "set_target": ((str, _NONE),),
    "set_effect": ((str, _NONE),),
    "set_effect_speed": ((int,),),
    "set_music": ((str, _NONE),),
    "set_sensitivity": ((int,),),
    "set_checked": ((str,), (bool,)),
    "scan": (),
    "link": (),
    "rename": ((str,), (str,)),
    "forget": ((str,),),
    "set_msi_effect": ((str,),),
    "set_theme": ((str,),),
    "set_tray_color_icon": ((bool,),),
    "check_updates": (),
    "install_update": (),
}


class Server(QObject):
    clients_changed = Signal()

    def __init__(self, api, pairing, port):
        super().__init__()
        self._api = api
        self._pairing = pairing
        self.port = port
        self.name = QSysInfo.machineHostName()
        self._clients = {}                  # QWebSocket -> paired?
        self._page = _PAGE.read_bytes()

        self._ws = QWebSocketServer("Lumea", QWebSocketServer.SslMode.NonSecureMode, self)
        self._ws.newConnection.connect(self._on_connection)
        self.clients_changed.connect(self._send_info)
        self._tcp = QTcpServer(self)
        if not self._tcp.listen(QHostAddress(QHostAddress.SpecialAddress.Any), port):
            raise OSError(f"port {port} is in use")
        self._tcp.newConnection.connect(self._on_tcp)
        self._discovery = Discovery(self.name, port)
        self._discovery.peers_changed.connect(self._send_info)

        self._frame = None                  # newest effect / music colour not yet sent
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._send_frame)
        api.changed.connect(self._send_state)
        api.frame.connect(self._on_frame)

    @property
    def paired_clients(self):
        return sum(self._clients.values())

    def drop_clients(self):
        """After a pairing reset: their tokens are void, so close them."""
        for sock in list(self._clients):
            self._deny(sock, "Pairings were reset. Pair again with the new PIN.")
        self.clients_changed.emit()         # the panel shows the new PIN

    def stop(self):
        self._api.changed.disconnect(self._send_state)
        self._api.frame.disconnect(self._on_frame)
        self._frame_timer.stop()
        for sock in list(self._clients):
            # Cut its signals first: the sockets die with the server right after,
            # and a late "disconnected" would reach an already deleted socket.
            sock.disconnected.disconnect()
            sock.textMessageReceived.disconnect()
            sock.close()
        self._clients.clear()
        self._discovery.stop()
        self._ws.close()
        self._tcp.close()

    # ---- sockets ------------------------------------------------------------

    def _on_tcp(self):
        while self._tcp.hasPendingConnections():
            sock = self._tcp.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._route(s))
            sock.disconnected.connect(sock.deleteLater)

    def _route(self, sock):
        # Peek, don't read: a WebSocket upgrade must reach QWebSocketServer intact.
        head = bytes(sock.peek(_MAX_HEAD))
        if b"\r\n\r\n" not in head:
            if len(head) >= _MAX_HEAD:
                sock.abort()
            return                          # wait for the rest of the head
        sock.readyRead.disconnect()
        sock.disconnected.disconnect()
        if b"\r\nupgrade: websocket" in head.lower():
            self._ws.handleConnection(sock)
            return
        parts = head.split(b" ", 2)
        found = len(parts) > 1 and parts[0] == b"GET" and parts[1].split(b"?")[0] == b"/"
        body = self._page if found else b"Not found"
        sock.write(b"HTTP/1.1 " + (b"200 OK" if found else b"404 Not Found") + b"\r\n"
                   + b"Content-Type: " + (b"text/html" if found else b"text/plain") + b"; charset=utf-8\r\n"
                   + b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                   + b"Cache-Control: no-store\r\nConnection: close\r\n\r\n" + body)
        sock.disconnectFromHost()
        sock.disconnected.connect(sock.deleteLater)

    def _on_connection(self):
        sock = self._ws.nextPendingConnection()
        self._clients[sock] = False
        sock.textMessageReceived.connect(lambda text, s=sock: self._on_message(s, text))
        sock.disconnected.connect(lambda s=sock: self._on_disconnected(s))

    def _on_disconnected(self, sock):
        if self._clients.pop(sock, None) is not None:
            sock.deleteLater()
            self.clients_changed.emit()

    def _on_message(self, sock, text):
        try:
            msg = json.loads(text)
            kind = msg["type"]
        except (ValueError, KeyError, TypeError):
            return self._send(sock, {"type": "error", "message": "Bad message."})
        if not self._clients.get(sock):
            if kind == "hello" and self._pairing.check(msg.get("token")):
                self._welcome(sock)
            elif kind == "pair":
                token, why = self._pairing.pair(msg.get("pin", ""), sock.peerAddress().toString())
                if token:
                    self._welcome(sock, token)
                else:
                    self._deny(sock, why)
            else:
                self._deny(sock, "Not paired.")
            return
        if kind == "cmd":
            self._run(sock, msg.get("name"), msg.get("args", []))

    def _welcome(self, sock, token=None):
        self._clients[sock] = True
        reply = {"type": "welcome", "name": self.name}
        if token:
            reply["token"] = token
        self._send(sock, reply)
        self._send(sock, {"type": "state", "state": self._api.state()})
        self.clients_changed.emit()

    def _send_info(self):
        self._broadcast({"type": "info", "port": self.port, "phones": self.paired_clients,
                         "peers": self._discovery.peers()})

    def _deny(self, sock, reason):
        self._send(sock, {"type": "denied", "reason": reason})
        sock.close()

    def _run(self, sock, name, args):
        spec = COMMANDS.get(name)
        if spec is None or not isinstance(args, list) or len(args) != len(spec) or not all(
                isinstance(a, t) and not (isinstance(a, bool) and bool not in t) for a, t in zip(args, spec)):
            return self._send(sock, {"type": "error", "message": f"Unknown or malformed command {name!r}."})
        try:
            getattr(self._api, name)(*args)
        except Exception as e:
            log.exception("remote command %s failed", name)
            self._send(sock, {"type": "error", "message": str(e)})

    # ---- pushing --------------------------------------------------------------

    def _send_state(self):
        self._broadcast({"type": "state", "state": self._api.state()})

    def _on_frame(self, color):
        self._frame = color
        if not self._frame_timer.isActive():
            self._send_frame()              # first one right away, then at most every interval
            self._frame_timer.start()

    def _send_frame(self):
        if self._frame is None:
            self._frame_timer.stop()
            return
        self._broadcast({"type": "frame", "color": self._frame})
        self._frame = None

    def _broadcast(self, msg):
        text = json.dumps(msg)
        for sock, paired in self._clients.items():
            if paired:
                sock.sendTextMessage(text)

    @staticmethod
    def _send(sock, msg):
        sock.sendTextMessage(json.dumps(msg))
