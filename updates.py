"""Checks GitHub for a release newer than the running build and installs it --
port of taplock-windows' updates.py, plus the Homebrew path from taplock-app.

Unauthenticated GitHub API calls are limited to 60 an hour per IP; the app
checks at launch and once a day, far below that. A dismissed version stays
hidden until a newer one is published.

How the update is installed depends on where this process runs from:

- Windows, frozen: the new exe is downloaded next to the running one, the
  running one is renamed out of the way (Windows refuses to delete or overwrite
  a running exe but allows renaming it), the download moves into place and a
  detached relauncher starts it once we have quit.
- macOS, frozen, running from the bundle Homebrew installed: `brew upgrade
  --cask` replaces the bundle on disk, then the app quits and reopens itself.
  brew would normally quit the app first (the cask's `uninstall quit:`), but it
  never quits an app it finds among its own parent processes. Only the bundle
  the Caskroom symlink points at qualifies: a copy running from anywhere else
  (a dev build, a hand-copied app) is not what brew replaces.
- Anything else, including a source checkout, gets the release page.

Everything runs on the Qt loop: QNetworkAccessManager for the API call and the
download, QProcess for brew. No threads (see CLAUDE.md).
"""

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QProcess, QProcessEnvironment, QSettings, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

log = logging.getLogger(__name__)

REPO = "ugurcandede/Lumea"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/latest/download/Lumea-windows.exe"
CHECK_INTERVAL_MS = 24 * 3600 * 1000
_API = f"https://api.github.com/repos/{REPO}/releases/latest"
_TIMEOUT_MS = 10_000
_DOWNLOAD_TIMEOUT_MS = 120_000
# Long enough for this process to exit and release the single-instance socket,
# so the new exe does not find us still running and bow out.
_RELAUNCH_DELAY_SECONDS = 2
_CASK = "lumea"
_BUNDLE_NAME = "Lumea.app"


@dataclass(frozen=True)
class Update:
    version: str
    url: str


def is_newer(candidate, current):
    """Numeric dot-separated comparison: 1.10.0 is newer than 1.9.3. Non-numeric
    parts ("dev.abc1234", "0.0.0-local") count as 0, so source runs and local
    builds see the banner -- handy for testing it."""

    def parts(text):
        return [int(p) if p.isdigit() else 0 for p in text.split(".")]

    a, b = parts(candidate), parts(current)
    width = max(len(a), len(b))
    return a + [0] * (width - len(a)) > b + [0] * (width - len(b))


def parse_release(data, current, dismissed=None):
    """The release in `data` if newer than `current` and not dismissed."""
    try:
        release = json.loads(data)
        tag, url = release["tag_name"], release["html_url"]
    except (ValueError, KeyError, TypeError):
        return None
    latest = tag[1:] if tag.startswith("v") else tag
    if not is_newer(latest, current) or latest == dismissed:
        return None
    return Update(latest, url)


def current_version():
    return QCoreApplication.applicationVersion() or "dev"


def dismissed_version():
    return QSettings().value("update_dismissed_version", None)


def dismiss(latest):
    QSettings().setValue("update_dismissed_version", latest)


def install_kind():
    """"exe" (Windows self-swap), "brew" (macOS Homebrew) or None (release page)."""
    if not getattr(sys, "frozen", False):
        return None
    if sys.platform == "win32":
        return "exe"
    if sys.platform == "darwin" and brew_prefix() is not None:
        return "brew"
    return None


# ---- macOS / Homebrew ------------------------------------------------------

def _bundle():
    # Lumea.app/Contents/MacOS/Lumea -> Lumea.app
    return Path(sys.executable).resolve().parents[2]


def brew_prefix():
    """The Homebrew prefix managing this app, if this process runs from the
    bundle brew installed (the target of the Caskroom symlink)."""
    running = _bundle()
    for prefix in ("/opt/homebrew", "/usr/local"):
        caskroom = Path(prefix, "Caskroom", _CASK)
        if not os.access(f"{prefix}/bin/brew", os.X_OK) or not caskroom.is_dir():
            continue
        if any((d / _BUNDLE_NAME).resolve() == running for d in caskroom.iterdir()):
            return prefix
    return None


def installed_version():
    """The version of the bundle on disk, read fresh -- after an upgrade it
    differs from the one this process loaded at launch."""
    try:
        return (_bundle() / "Contents/Resources/version.txt").read_text().strip()
    except OSError:
        return ""


def brew_log_path():
    return Path.home() / "Library/Logs" / f"{_CASK}-update.log"


def _relaunch_mac(bundle):
    # Reopen once this process has gone. By path, not bundle id: another copy
    # with the same id may be registered with LaunchServices.
    script = f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.2; done; open '{bundle}'"
    subprocess.Popen(["/bin/sh", "-c", script], start_new_session=True)


# ---- Windows / exe swap ----------------------------------------------------

def cleanup_previous(exe=None):
    """Remove the exe a previous update renamed out of the way."""
    exe = Path(exe or sys.executable)
    try:
        exe.with_name(exe.name + ".old").unlink(missing_ok=True)
    except OSError:
        pass  # still locked or not ours to delete; try again next launch


def swap_executable(exe, new):
    """Put `new` where `exe` is, keeping the running exe as `<exe>.old`.
    Rolls back and re-raises if the second step fails."""
    exe, new = Path(exe), Path(new)
    old = exe.with_name(exe.name + ".old")
    old.unlink(missing_ok=True)
    os.rename(exe, old)
    try:
        os.rename(new, exe)
    except OSError:
        os.rename(old, exe)
        raise


def _relaunch_windows(exe):
    # ping is the usual console-free sleep; `start` detaches the new process.
    command = f'ping -n {_RELAUNCH_DELAY_SECONDS + 1} 127.0.0.1 >nul & start "" "{exe}"'
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(["cmd", "/c", command], creationflags=flags, close_fds=True)


class UpdateChecker(QObject):
    found = Signal(object)        # Update, or None when up to date
    installed = Signal()          # the new build is in place and relaunching; quit now
    install_failed = Signal(str)  # "not_in_brew_yet" | "brew_error" | "download" | "exe_swap"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)

    def check(self):
        request = QNetworkRequest(QUrl(_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setTransferTimeout(_TIMEOUT_MS)
        reply = self._nam.get(request)

        def done():
            reply.deleteLater()
            if reply.error() != QNetworkReply.NetworkError.NoError:
                log.debug("update check failed: %s", reply.errorString())
                return  # keep whatever was shown; the daily check tries again
            self.found.emit(parse_release(bytes(reply.readAll()), current_version(), dismissed_version()))

        reply.finished.connect(done)

    def install(self):
        kind = install_kind()
        if kind == "exe":
            self._install_exe()
        elif kind == "brew":
            self._install_brew(brew_prefix())

    def _install_exe(self):
        exe = Path(sys.executable)
        new = exe.with_name(exe.name + ".new")
        request = QNetworkRequest(QUrl(DOWNLOAD_URL))
        request.setTransferTimeout(_DOWNLOAD_TIMEOUT_MS)
        reply = self._nam.get(request)

        def done():
            reply.deleteLater()
            data = bytes(reply.readAll())
            # A redirect to an error page must never replace the app.
            if reply.error() != QNetworkReply.NetworkError.NoError or not data.startswith(b"MZ"):
                self.install_failed.emit("download")
                return
            try:
                new.write_bytes(data)
                swap_executable(exe, new)
                _relaunch_windows(exe)
            except OSError:
                new.unlink(missing_ok=True)
                self.install_failed.emit("exe_swap")
                return
            self.installed.emit()

        reply.finished.connect(done)

    def _install_brew(self, prefix):
        log_path = brew_log_path()
        script = (
            f'echo "--- $(date)" >> "{log_path}"\n'
            # brew's auto-update runs at most once a day, so the tap can still
            # hold the previous cask; refresh it first. Offline, try anyway.
            f'"{prefix}/bin/brew" update --quiet >> "{log_path}" 2>&1\n'
            f'"{prefix}/bin/brew" upgrade --cask {_CASK} >> "{log_path}" 2>&1\n'
        )
        env = QProcessEnvironment.systemEnvironment()
        # Launched from Finder the app has no shell PATH; brew needs git and curl.
        env.insert("PATH", f"{prefix}/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        env.insert("HOMEBREW_NO_ENV_HINTS", "1")
        process = QProcess(self)
        process.setProcessEnvironment(env)
        current = current_version()

        def finished(code, _status):
            process.deleteLater()
            if code == 0 and is_newer(installed_version(), current):
                _relaunch_mac(_bundle())
                self.installed.emit()
                return
            # Success with an unchanged bundle means brew had no newer version
            # yet -- the tap is bumped a few minutes after the GitHub release.
            self.install_failed.emit("not_in_brew_yet" if code == 0 else "brew_error")

        process.finished.connect(finished)
        process.start("/bin/sh", ["-c", script])
