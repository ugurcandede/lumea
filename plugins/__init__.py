"""Optional add-ons, switched on per plugin in Settings > Plugins (off by default).

A plugin is a class with:

    name = "Remote control"            # Settings row title; also its saved key
    description = "One line under it"

    def __init__(self, api):           # start: api is a plugins.api.LumeaAPI
    def stop(self):                    # undo everything __init__ did
    def settings_widget(self):         # optional: QWidget shown under the row while on

Plugins only talk to the app through LumeaAPI. If __init__ raises, the plugin is
reported and switched back off.

PLUGINS is a fixed list rather than a scan of this folder: PyInstaller only bundles
modules it can see imported, so a discovered plugin would be missing from the exe.
"""

PLUGINS = []
