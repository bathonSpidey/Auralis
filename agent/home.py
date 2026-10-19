"""What the listener's home says right now (room temperature, light, who is in).

Home Assistant pushes these as plain key/value pairs. They are context for the
mood of a pick, never instructions, so everything is kept small and plain:
short snake_case keys, numbers, booleans and one-line text. Each value keeps
its own timestamp, so a sensor that stopped reporting quietly drops out of the
prompt instead of describing a room that no longer exists.
"""

import re
import time
from typing import Callable, Dict, Optional

SETTING_KEY = "home.context"
MAX_KEYS = 24
MAX_TEXT = 80
MAX_AGE_SECONDS = 3 * 60 * 60

_KEY = re.compile(r"[^a-z0-9]+")


class HomeError(ValueError):
    pass


def clean(values: Dict[str, object]) -> Dict[str, Optional[object]]:
    """Normalise one push. A value of None means "forget this key"."""
    if not isinstance(values, dict):
        raise HomeError("Send an object of key/value pairs")
    out: Dict[str, Optional[object]] = {}
    for raw_key, value in values.items():
        key = _KEY.sub("_", str(raw_key).strip().lower()).strip("_")[:40]
        if not key:
            raise HomeError(f"{raw_key!r} is not a usable key")
        if value is None:
            out[key] = None
        elif isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = round(value, 2)
        elif isinstance(value, str):
            text = " ".join(value.split())[:MAX_TEXT]
            out[key] = text or None
        else:
            raise HomeError(f"{key}: use a number, true/false or short text")
    return out


class HomeState:
    """The latest value of each thing the home has reported."""

    def __init__(
        self,
        store,
        wall: Callable[[], float] = time.time,
        max_age: float = MAX_AGE_SECONDS,
    ):
        self.store = store
        self.wall = wall
        self.max_age = max_age

    def update(self, values: Dict[str, object]) -> Dict[str, object]:
        """Merge a push into what is known; returns what is current now."""
        changes = clean(values)
        known = self._load()
        for key, value in changes.items():
            if value is None:
                known.pop(key, None)
            else:
                known[key] = [value, self.wall()]
        if len(known) > MAX_KEYS:
            raise HomeError(f"At most {MAX_KEYS} different keys")
        self.store.set_setting(SETTING_KEY, known)
        return self.current() or {}

    def current(self) -> Optional[Dict[str, object]]:
        """Values reported within the last few hours, or None if there are none."""
        now = self.wall()
        fresh = {
            key: value
            for key, (value, at) in self._load().items()
            if now - at <= self.max_age
        }
        return fresh or None

    def _load(self) -> dict:
        return dict(self.store.get_setting(SETTING_KEY, {}))
