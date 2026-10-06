"""Finds, installs, updates and runs plugins. See plugins/README.md for the whole picture.

Plugins are not part of the build. They live in the repo under plugins/<id>/ and are
listed in plugins/version.json. A packaged Lumea reads that index from GitHub (when
Settings opens), downloads a plugin the user installs into the app-data folder,
verifies every file's sha256, and loads it with importlib -- no restart. A source
run skips all of that and loads plugins/<id>/ straight from the repo, so a plugin
can be tried before it is published.

A plugin is a package whose __init__.py defines:

    class Plugin:
        def __init__(self, api):     # start; api is a plugin_api.LumeaAPI
        def stop(self):              # undo everything __init__ did
        def settings_widget(self):   # optional: QWidget shown under its Settings row

Everything runs on the Qt / asyncio loop (QNetworkAccessManager, no threads).
"""

import asyncio
import hashlib
import importlib.util
import json
import logging
import shutil
import sys
import time
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QObject, QStandardPaths, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

import plugin_runtime  # noqa: F401  makes PyInstaller bundle the libraries plugins may use
import updates
from plugin_api import API_VERSION

log = logging.getLogger(__name__)

INDEX_URL = f"https://raw.githubusercontent.com/{updates.REPO}/refs/heads/master/plugins/version.json"
_FILES_URL = INDEX_URL.rsplit("/", 1)[0]
_REPO_PLUGINS = Path(__file__).resolve().parent / "plugins"
_TIMEOUT_MS = 15_000
_META = "plugin.json"               # the index entry an installed copy came from


def compatible(entry):
    """None if this build can run the plugin described by an index entry, else why not."""
    try:
        major, minor = (int(x) for x in str(entry["api"]).split("."))
    except (KeyError, ValueError):
        return "Invalid plugin entry"
    if major != API_VERSION[0] or minor > API_VERSION[1]:
        return "Needs a newer Lumea"
    missing = [m for m in entry.get("requires", []) if not _importable(m)]
    if missing:
        # The build doesn't contain a library the plugin imports (plugin_runtime.py).
        return "Needs a newer Lumea"
    return None


def _importable(module):
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _version_key(text):
    return [int(p) if p.isdigit() else 0 for p in str(text).split(".")]


class PluginHost(QObject):
    """Owns the plugin list. `changed` fires when anything shown in Settings moved."""

    changed = Signal()

    def __init__(self, api, enabled, parent=None):
        super().__init__(parent)
        self._api = api
        self.enabled = set(enabled)            # ids the user switched on (persisted by the UI)
        self.dev = not getattr(sys, "frozen", False)
        root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self._root = _REPO_PLUGINS if self.dev else Path(root) / "plugins"
        self._nam = QNetworkAccessManager(self)
        self._index = {}                       # id -> entry, from version.json
        self.index_error = None                # why the last index fetch failed, if it did
        self._busy = {}                        # id -> "Installing…" while a download runs
        self._errors = {}                      # id -> last install / start error
        self.running = {}                      # id -> Plugin instance
        if self.dev:
            self._index = self._read_local_index()

    # ---- listing -----------------------------------------------------------

    def installed(self):
        """id -> entry of every plugin on disk (in a source run: every indexed one)."""
        if self.dev:
            return {pid: e for pid, e in self._index.items() if (self._root / pid).is_dir()}
        found = {}
        if self._root.is_dir():
            for meta in self._root.glob(f"*/{_META}"):
                try:
                    found[meta.parent.name] = json.loads(meta.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    log.warning("unreadable %s", meta)
        return found

    def entries(self):
        """Rows for Settings: everything installed or offered, sorted by name."""
        installed = self.installed()
        rows = []
        for pid in set(installed) | set(self._index):
            have, offer = installed.get(pid), self._index.get(pid)
            entry = offer or have
            rows.append({
                "id": pid,
                "name": entry.get("name", pid),
                "description": entry.get("description", ""),
                "installed": have["version"] if have else None,
                "available": offer["version"] if offer else None,
                "update": bool(have and offer and _version_key(offer["version"]) > _version_key(have["version"])),
                "problem": compatible(offer) if offer else None,
                "busy": self._busy.get(pid),
                "error": self._errors.get(pid),
                "running": pid in self.running,
            })
        return sorted(rows, key=lambda r: r["name"].lower())

    async def refresh(self):
        """Re-read the plugin index (GitHub, or the repo in a source run)."""
        if self.dev:
            self._index = self._read_local_index()
            self.changed.emit()
            return
        try:
            data = json.loads(await self._get(f"{INDEX_URL}?t={int(time.time())}"))
            self._index = data["plugins"]
            self.index_error = None
        except Exception as e:
            log.warning("plugin index fetch failed: %s", e)
            self.index_error = "Couldn't load the plugin list."
        self.changed.emit()

    # ---- install / update / remove ---------------------------------------

    async def install(self, pid):
        """Install, or update to, the indexed version. Running copies restart."""
        entry = self._index.get(pid)
        if self.dev or entry is None or pid in self._busy or compatible(entry):
            return
        self._busy[pid] = "Installing…"
        self._errors.pop(pid, None)
        self.changed.emit()
        try:
            files = {}
            for rel, digest in entry["files"].items():
                path = PurePosixPath(rel)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"bad file path {rel!r}")
                data = await self._get(f"{_FILES_URL}/{pid}/{rel}?t={int(time.time())}")
                if hashlib.sha256(data).hexdigest() != digest:
                    # Usually GitHub's few-minute cache serving a file older than the index.
                    raise ValueError(f"{rel} doesn't match the plugin list; try again in a few minutes")
                files[path] = data
            # Write everything to a staging folder, then swap it in, so a failed
            # download never leaves a half-updated plugin behind.
            staging = self._root / f".{pid}.new"
            shutil.rmtree(staging, ignore_errors=True)
            for path, data in files.items():
                target = staging.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            (staging / _META).write_text(json.dumps(entry, indent=2), encoding="utf-8")
            was_running = pid in self.running
            self._stop(pid)
            shutil.rmtree(self._root / pid, ignore_errors=True)
            staging.rename(self._root / pid)
            if was_running:
                self._start(pid)
        except Exception as e:
            log.exception("plugin %s install failed", pid)
            self._errors[pid] = f"Install failed: {e}"
        finally:
            self._busy.pop(pid, None)
            self.changed.emit()

    def remove(self, pid):
        if self.dev:
            return
        self._stop(pid)
        self.enabled.discard(pid)
        shutil.rmtree(self._root / pid, ignore_errors=True)
        self._errors.pop(pid, None)
        self.changed.emit()

    # ---- running ------------------------------------------------------------

    def set_enabled(self, pid, on):
        if on:
            self.enabled.add(pid)
            self._start(pid)
        else:
            self.enabled.discard(pid)
            self._stop(pid)
        self.changed.emit()

    def start_enabled(self):
        """At launch: start every installed plugin the user left on (no network)."""
        for pid in self.installed():
            if pid in self.enabled:
                self._start(pid)
        self.changed.emit()                    # a plugin that failed is now switched off

    def stop_all(self):
        for pid in list(self.running):
            self._stop(pid)

    def _start(self, pid):
        if pid in self.running:
            return
        entry = self.installed().get(pid)
        problem = compatible(entry) if entry else "Not installed"
        if problem:
            self._errors[pid] = problem
            self.enabled.discard(pid)
            return
        try:
            self.running[pid] = self._load(pid).Plugin(self._api)
            self._errors.pop(pid, None)
        except Exception as e:
            log.exception("plugin %s failed to start", pid)
            self._errors[pid] = f"Couldn't start: {e}"
            self.enabled.discard(pid)

    def _stop(self, pid):
        instance = self.running.pop(pid, None)
        if instance is not None:
            try:
                instance.stop()
            except Exception:
                log.exception("plugin %s failed to stop", pid)

    def _load(self, pid):
        # A fresh module every time, so an update or a re-enable runs the new code.
        name = f"lumea_plugin_{pid}"        # top-level, so "from . import x" inside the plugin works
        for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
            del sys.modules[key]
        folder = self._root / pid
        spec = importlib.util.spec_from_file_location(
            name, folder / "__init__.py", submodule_search_locations=[str(folder)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    # ---- helpers ------------------------------------------------------------

    def _read_local_index(self):
        try:
            return json.loads((_REPO_PLUGINS / "version.json").read_text(encoding="utf-8"))["plugins"]
        except (OSError, ValueError, KeyError) as e:
            log.warning("local plugin index unreadable: %s", e)
            return {}

    async def _get(self, url):
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(_TIMEOUT_MS)
        reply = self._nam.get(request)
        done = asyncio.get_running_loop().create_future()
        reply.finished.connect(lambda: done.done() or done.set_result(None))
        await done
        reply.deleteLater()
        if reply.error() != QNetworkReply.NetworkError.NoError:
            raise OSError(reply.errorString())
        return bytes(reply.readAll())
