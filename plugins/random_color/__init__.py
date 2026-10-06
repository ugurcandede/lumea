"""Random color: shows how a plugin reads, follows and drives Lumea.

Read plugins/README.md first. Everything here goes through `api` (plugin_api.LumeaAPI).
"""

from PySide6.QtCore import QRandomGenerator

from .panel import Panel


class Plugin:
    def __init__(self, api):
        self.api = api
        api.show_status("Random color plugin started.")

    def stop(self):
        self.api.show_status("Random color plugin stopped.")

    def settings_widget(self):
        # Called again on every refresh of the Plugins page: return a new widget.
        return Panel(self.api, self.random_color)

    def random_color(self):
        # Qt's generator, not the random module: Lumea's build doesn't include `random`
        # (tools/plugins.py check would refuse it; see plugins/README.md).
        self.api.set_color(f"#{QRandomGenerator.global_().bounded(0x1000000):06x}")
