# Lumea plugins

Optional add-ons that users install from **Settings › Plugins › Manage** (a page with **Installed** and
**Available** lists). They are **not part of the Lumea build**: a
plugin is published by merging it to `master`, and every Lumea already installed can download it — no app
release, no update.

## How it works

```
repo (master)                                  user's PC
plugins/version.json  ──(Plugins page opens)─▶ list: name, version, Install / Update / Remove
plugins/<id>/…        ──(Install/Update)───▶   %APPDATA%\ugurcandede\Lumea\plugins\<id>\
                                               (macOS: ~/Library/Application Support/ugurcandede/Lumea/plugins/<id>/)
```

1. Opening the Plugins page fetches `plugins/version.json` from
   `https://raw.githubusercontent.com/ugurcandede/Lumea/refs/heads/master/plugins/version.json`
   (`plugin_host.INDEX_URL`).
2. **Install / Update** downloads every file listed for the plugin, checks each against its sha256, writes
   them to a staging folder and swaps it in. A failed download leaves the old copy untouched.
3. The plugin is loaded with `importlib` — no restart. A running plugin is stopped and restarted on update.
4. The on/off switch is remembered; enabled plugins start with the app (from disk, no network).

**Source runs** (`python main.py`) skip the download: plugins load straight from this folder, so you can try
one before publishing it. Install / Update / Remove are hidden then.

## The rule that's easy to forget

A plugin is plain Python, run by the Python **inside** `Lumea.exe` / `Lumea.app`. That Python has no pip, and
PyInstaller put into it only the modules Lumea's own code imports — **standard library included**.

So a plugin can import only modules that are either

- imported by Lumea's own code (`PySide6.QtCore`, `json`, `asyncio`, `plugin_api`, …), or
- listed in [`plugin_runtime.py`](../plugin_runtime.py) — a never-called function whose imports exist just so
  PyInstaller bundles them.

Anything else fails with `ModuleNotFoundError` on users' machines, even though it works in a source run.
Adding a module to `plugin_runtime.py` changes the app, so it takes **a Lumea release** before any plugin can
rely on it — do that first, plugin second.

You don't have to track this by hand: `python tools/plugins.py check` (CI runs it on every change) fails if a
plugin imports something that isn't bundled, and `index` records what each plugin needs from
`plugin_runtime.py` as `"requires"`. A Lumea build that lacks a required module shows **"Needs a newer Lumea"**
instead of installing the plugin.

## Writing a plugin

```
plugins/
  version.json
  my_plugin/
    __init__.py      defines class Plugin
    …                any other files (more modules, html, images)
```

```python
# plugins/my_plugin/__init__.py
class Plugin:
    def __init__(self, api):          # start; api is plugin_api.LumeaAPI
        self.api = api
        api.changed.connect(self.on_change)

    def on_change(self):
        print(self.api.state()["color"])

    def stop(self):                   # undo everything __init__ did: timers, sockets, signal connections
        self.api.changed.disconnect(self.on_change)

    def settings_widget(self):        # optional: a QWidget shown under the plugin's row on the Plugins page.
        ...                           # Called again on every refresh of the list: return a new widget each time.
```

- Talk to the app **only** through `api` (`plugin_api.py`): `state()`, the `changed` / `frame` signals and the
  command methods. Don't import `ui`.
- Everything runs on the app's single event loop: no threads, no blocking calls. Use Qt (`QTimer`,
  `QNetworkAccessManager`, `QTcpServer`, …) or `async` code.
- Import your own modules relatively (`from . import page`); read your own files relative to `__file__`.
- If `__init__` raises, the plugin is switched off and the error is shown on the Plugins page.

## Publishing

1. Add or edit the entry in `version.json` — the four fields you own:

   ```json
   "my_plugin": {
     "name": "My plugin",
     "description": "One line shown on the Plugins page",
     "version": "1.0.0",
     "api": "1.0"
   }
   ```

   - `version`: bump it on every change, or installed copies won't be offered the update.
   - `api`: the `plugin_api.API_VERSION` you wrote against, as `"major.minor"`. A Lumea runs the plugin if the
     major matches and its minor is at least this. (`API_VERSION`: additions bump the minor; anything that
     could break an existing plugin bumps the major.)

2. `python tools/plugins.py index` — fills in `files` (sha256 of every file) and `requires`.
3. `python tools/plugins.py check` — must print `ok`.
4. Merge to `master`. Changes under `plugins/` don't trigger an app build; the plugin is live as soon as GitHub's
   cache (a few minutes) catches up.

## Troubleshooting

| The Plugins page says | Meaning |
|---|---|
| Needs a newer Lumea | The plugin's `api` is newer than this build, or it requires a module this build doesn't bundle. Update Lumea. |
| Install failed: … doesn't match the plugin list | GitHub's cache served a file older than `version.json`. Wait a few minutes and retry. |
| Couldn't start: … | `Plugin.__init__` raised; the log has the traceback. |
| Couldn't load the plugin list. | No network, or GitHub unreachable. Installed plugins still work. |

Trust: plugins are code downloaded from this repo's `master` and run with the user's rights — the same trust
the self-updater already places in this repo's releases. Anyone who can push to `master` can ship code to
every user, so protect the branch.
