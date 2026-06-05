"""Entry point: QApplication hosting the asyncio loop via qasync."""

import asyncio
import logging
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

import icon
from ui import LedController


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
    # Closing the window hides to the tray; quit happens via the tray menu.
    app.setQuitOnLastWindowClosed(False)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # The controller sets this to request shutdown. We do NOT call app.quit():
    # that stops the Qt loop out from under run_until_complete and qasync then
    # raises "Event loop stopped before Future completed".
    close_event = asyncio.Event()

    win = LedController(close_event)
    win.show()

    with loop:
        loop.run_until_complete(close_event.wait())
        _cancel_pending(loop)


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
