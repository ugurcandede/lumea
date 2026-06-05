"""Entry point: QApplication hosting the asyncio loop via qasync."""

import asyncio
import logging
import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

import icon
from theme import STYLESHEET
from ui import LedController

# Named local socket (Windows named pipe / Unix domain socket) used to detect a
# running instance. Portable, so it works on the planned macOS port too.
_IPC_KEY = "Lumea-single-instance"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    # QSettings keys off these (Windows registry, no extra files).
    app.setOrganizationName("ugurcandede")
    app.setApplicationName("Lumea")
    app.setWindowIcon(icon.app_icon())
    app.setStyleSheet(STYLESHEET)
    # Closing the window hides to the tray; quit happens via the tray menu.
    app.setQuitOnLastWindowClosed(False)

    # If another instance already owns the socket, hand off to it and exit. The
    # running instance brings its (possibly tray-hidden) window to the front.
    if _ping_running_instance():
        logging.info("Another instance is already running; bringing it to front.")
        sys.exit(0)
    server = _claim_instance_socket()

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # The controller sets this to request shutdown. We do NOT call app.quit():
    # that stops the Qt loop out from under run_until_complete and qasync then
    # raises "Event loop stopped before Future completed".
    close_event = asyncio.Event()

    win = LedController(close_event)
    win.show()

    # A second launch connects to our socket instead of starting up; surface the
    # existing window when that happens.
    server.newConnection.connect(lambda: _drain_and_show(server, win))

    with loop:
        loop.run_until_complete(close_event.wait())
        _cancel_pending(loop)


def _ping_running_instance() -> bool:
    """True if another instance already holds the socket (connection succeeds)."""
    socket = QLocalSocket()
    socket.connectToServer(_IPC_KEY)
    connected = socket.waitForConnected(200)
    if connected:
        socket.disconnectFromServer()
    return connected


def _claim_instance_socket() -> QLocalServer:
    # removeServer clears a stale socket left by a crash (matters on Unix, where
    # the socket file outlives the process).
    QLocalServer.removeServer(_IPC_KEY)
    server = QLocalServer()
    server.listen(_IPC_KEY)
    return server


def _drain_and_show(server: QLocalServer, win: LedController) -> None:
    conn = server.nextPendingConnection()
    if conn is not None:
        conn.close()
    win.show_window()


def _cancel_pending(loop) -> None:
    # Best-effort: cancel leftover tasks (e.g. a reconnect mid-sleep) so they
    # don't log "Task was destroyed but it is pending" on exit.
    try:
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass


if __name__ == "__main__":
    main()
