"""Finds the other PCs on the network running Remote control, so a phone can switch
between them.

Every instance broadcasts a small UDP beacon every few seconds and listens for the
others'. A PC that goes quiet for a while drops off the list. If the port can't be
bound, discovery is just off; nothing else depends on it.
"""

import json
import os
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkInterface, QUdpSocket

PORT = 8767
BEACON_MS = 3000
FORGET_AFTER = 10          # seconds without a beacon

# Adapters a phone can't reach: Hyper-V / WSL switches, VM and container bridges.
_VIRTUAL = ("vethernet", "virtualbox", "vmware", "hyper-v", "wsl", "docker", "bluetooth")


def lan_entries():
    """(ip, broadcast) of this PC's IPv4 addresses a phone on the same network could
    reach, likeliest first. Virtual adapters are left out: Windows sends a plain
    255.255.255.255 broadcast out of whichever adapter comes first, often Hyper-V's."""
    found = []
    for iface in QNetworkInterface.allInterfaces():
        flags = iface.flags()
        if (not (flags & QNetworkInterface.InterfaceFlag.IsRunning)
                or flags & QNetworkInterface.InterfaceFlag.IsLoopBack
                or any(v in iface.humanReadableName().lower() for v in _VIRTUAL)):
            continue
        for entry in iface.addressEntries():
            ip = entry.ip()
            if ip.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol and not ip.isLinkLocal():
                found.append((ip.toString(), entry.broadcast()))
    return sorted(found, key=lambda e: _home_network_rank(e[0]))


def lan_addresses():
    return [ip for ip, _ in lan_entries()]


def _home_network_rank(ip):
    # Home routers hand out 192.168.x most, then 10.x, then 172.16-31.x.
    a, b = (int(x) for x in ip.split(".")[:2])
    if a == 192 and b == 168:
        return 0
    if a == 10:
        return 1
    if a == 172 and 16 <= b <= 31:
        return 2
    return 3


class Discovery(QObject):
    peers_changed = Signal()

    def __init__(self, name, http_port):
        super().__init__()
        self._me = os.urandom(8).hex()         # tells our own beacons apart
        self._name = name
        self.http_port = http_port
        self._peers = {}                       # id -> (name, host, port, last seen)
        self._sock = QUdpSocket(self)
        mode = QAbstractSocket.BindFlag.ShareAddress | QAbstractSocket.BindFlag.ReuseAddressHint
        self.active = self._sock.bind(QHostAddress(QHostAddress.SpecialAddress.AnyIPv4), PORT, mode)
        if not self.active:
            return
        self._sock.readyRead.connect(self._read)
        self._timer = QTimer(self)
        self._timer.setInterval(BEACON_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

    def peers(self):
        """Other Lumea PCs, as [{"name", "url"}], sorted by name."""
        return sorted(({"name": n, "url": f"http://{h}:{p}/"} for n, h, p, _ in self._peers.values()),
                      key=lambda x: x["name"].lower())

    def stop(self):
        if self.active:
            self._timer.stop()
        self._sock.close()

    def _tick(self):
        entries = lan_entries()
        beacon = json.dumps({"lumea": 1, "id": self._me, "name": self._name, "port": self.http_port,
                             "hosts": [ip for ip, _ in entries]}).encode()
        # Out of each real adapter, so the beacon (and its sender address) is the LAN one.
        targets = [b for _, b in entries if not b.isNull()] or [QHostAddress(QHostAddress.SpecialAddress.Broadcast)]
        for target in targets:
            self._sock.writeDatagram(beacon, target, PORT)
        cutoff = time.monotonic() - FORGET_AFTER
        stale = [k for k, (*_, seen) in self._peers.items() if seen < cutoff]
        for k in stale:
            del self._peers[k]
        if stale:
            self.peers_changed.emit()

    def _read(self):
        while self._sock.hasPendingDatagrams():
            dg = self._sock.receiveDatagram(1024)
            try:
                msg = json.loads(bytes(dg.data()))
                if msg.get("lumea") != 1 or msg["id"] == self._me:
                    continue
                name, port = str(msg["name"])[:64], int(msg["port"])
                hosts = [str(h) for h in msg.get("hosts", [])][:8]
            except (ValueError, KeyError, TypeError):
                continue
            # The sender's own LAN address, not just where the datagram came from:
            # a PC with VM / WSL adapters may still send from one of those.
            host = dg.senderAddress().toString()      # IPv4: the socket is bound to AnyIPv4
            if hosts and host not in hosts:
                host = hosts[0]
            known = self._peers.get(msg["id"])
            self._peers[msg["id"]] = (name, host, port, time.monotonic())
            if known is None or known[:3] != (name, host, port):
                self.peers_changed.emit()
