"""Who may drive Lumea: a 6-digit PIN pairs a browser, which then keeps a token.

Only sha256 hashes of the tokens are stored. A wrong PIN costs the sender a try;
after MAX_TRIES it is locked out for LOCKOUT seconds, so the PIN can't be guessed.
Reset draws a new PIN and forgets every paired browser.
"""

import hashlib
import json
import os
import time

from PySide6.QtCore import QSettings

_KEY = "plugin_remote-control"
MAX_TRIES = 5
LOCKOUT = 60


class Pairing:
    def __init__(self):
        settings = QSettings()
        self.pin = settings.value(f"{_KEY}/pin") or _new_pin()
        self._tokens = set(json.loads(settings.value(f"{_KEY}/tokens", "[]")))
        self._fails = {}                    # peer -> (failed tries, locked until)
        self._save()

    def pair(self, pin, peer):
        """A new token for a correct PIN, else None plus why."""
        tries, until = self._fails.get(peer, (0, 0))
        if time.monotonic() < until:
            return None, f"Too many wrong PINs. Try again in {int(until - time.monotonic()) + 1} s."
        if str(pin).strip() != self.pin:
            tries += 1
            locked = time.monotonic() + LOCKOUT if tries >= MAX_TRIES else 0
            self._fails[peer] = (0 if locked else tries, locked)
            return None, "Wrong PIN."
        self._fails.pop(peer, None)
        token = os.urandom(16).hex()
        self._tokens.add(_digest(token))
        self._save()
        return token, None

    def check(self, token):
        return isinstance(token, str) and _digest(token) in self._tokens

    def reset(self):
        self.pin = _new_pin()
        self._tokens.clear()
        self._fails.clear()
        self._save()

    def _save(self):
        settings = QSettings()
        settings.setValue(f"{_KEY}/pin", self.pin)
        settings.setValue(f"{_KEY}/tokens", json.dumps(sorted(self._tokens)))


def _new_pin():
    return f"{int.from_bytes(os.urandom(4), 'big') % 1_000_000:06d}"


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()
