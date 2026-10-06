"""Libraries downloaded plugins may import, beyond what Lumea itself uses.

Plugins are plain .py files run by the Python inside Lumea.exe / Lumea.app. That
Python has no pip: a plugin can import only what Nuitka packed into the build, and
Nuitka packs only modules it sees imported by the app's own code. So every
module a plugin needs that Lumea doesn't already import must be imported below.

Adding a module here takes a new Lumea release before any plugin can rely on it.
A plugin lists its needs under "requires" in plugins/version.json; the app checks
them before installing (older builds say "needs a newer Lumea" instead of crashing),
and `python tools/plugins.py check` fails CI if a requirement is missing here.

The function is never called: Nuitka follows imports by reading the code, so this
bundles the modules without loading them at startup.
"""


def _bundle():
    import segno                    # noqa: F401  QR codes (remote: pairing)
    import PySide6.QtHttpServer     # noqa: F401  (remote: the phone page)
    import PySide6.QtWebSockets     # noqa: F401  (remote: live state)
