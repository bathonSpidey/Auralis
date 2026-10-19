"""DJ mode: while you are listening, add a fresh song to your queue every so often.

Two ways to start a song, chosen with the `polling` setting:

- Polling (the default): Auralis watches Spotify itself, so it needs nothing
  else to be running. A listening session starts when music is playing; every
  `minutes` after that, one song is picked for the moment (it sees what is
  playing right now) and queued. Pausing for a while ends the session, so
  nothing is queued into silence.
- Triggered: something else (Home Assistant) calls `trigger()` when it decides
  it is time, and Auralis does no watching of its own.

The picks go through the same job queue as everything else, so they wait their
turn behind a request you made yourself.
"""

import asyncio
import logging
import time
from datetime import date
from typing import Awaitable, Callable, Optional

from web.jobs import DONE, FAILED, QueueFull

logger = logging.getLogger(__name__)

SOURCE = "dj"
TRIGGER_SOURCE = "ha"
ENABLED_KEY = "dj.enabled"
MINUTES_KEY = "dj.minutes"
POLLING_KEY = "dj.polling"
MIN_TRIGGER_GAP_SECONDS = 5 * 60  # a misfiring automation cannot flood the queue
HINT_MAX = 200
DEFAULT_MINUTES = 30
MIN_MINUTES, MAX_MINUTES = 10, 180
POLL_SECONDS = 60
PAUSE_GRACE_SECONDS = 10 * 60  # a short pause does not end the session
MAX_WAIT_SECONDS = 10 * 60
JOB_POLL_SECONDS = 2
DEFAULT_MAX_PER_DAY = 12

Notify = Callable[[dict], Awaitable[None]]


class Dj:
    def __init__(
        self,
        spotify,
        queue,
        store,
        notify: Optional[Notify] = None,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        max_per_day: int = DEFAULT_MAX_PER_DAY,
    ):
        self.spotify = spotify
        self.queue = queue
        self.store = store
        self.notify = notify
        self.clock = clock
        self.wall = wall
        self.max_per_day = max_per_day
        self._anchor: Optional[float] = None  # when the next song is counted from
        self._paused_since: Optional[float] = None
        self._today = date.fromtimestamp(wall())
        self._added_today = 0
        self.last: Optional[dict] = None  # {title, artist, at, playback}
        self._last_trigger: Optional[float] = None
        self._tasks: set = set()  # keeps background picks from being collected

    # ── settings (kept, so a restart does not forget them) ──────────────
    @property
    def enabled(self) -> bool:
        return bool(self.store.get_setting(ENABLED_KEY, False))

    @property
    def minutes(self) -> int:
        return int(self.store.get_setting(MINUTES_KEY, DEFAULT_MINUTES))

    @property
    def polling(self) -> bool:
        return bool(self.store.get_setting(POLLING_KEY, True))

    def configure(
        self,
        enabled: Optional[bool] = None,
        minutes: Optional[int] = None,
        polling: Optional[bool] = None,
    ) -> dict:
        if minutes is not None:
            if not MIN_MINUTES <= minutes <= MAX_MINUTES:
                raise ValueError(
                    f"Choose between {MIN_MINUTES} and {MAX_MINUTES} minutes"
                )
            self.store.set_setting(MINUTES_KEY, minutes)
        if polling is not None:
            self.store.set_setting(POLLING_KEY, polling)
            self._anchor = self._paused_since = None
        if enabled is not None:
            self.store.set_setting(ENABLED_KEY, enabled)
            self._anchor = self._paused_since = None  # a fresh session
        return self.status()

    def status(self) -> dict:
        next_at = None
        if self.enabled and self._anchor is not None:
            next_at = self.wall() + max(
                0, self._anchor + self.minutes * 60 - self.clock()
            )
        return {
            "enabled": self.enabled,
            "minutes": self.minutes,
            "polling": self.polling,
            "listening": self._anchor is not None,
            "next_at": next_at,
            "added_today": self._added_today,
            "max_per_day": self.max_per_day,
            "last": self.last,
        }

    # ── the loop ────────────────────────────────────────────────────────
    async def run(self) -> None:
        while True:
            await asyncio.sleep(POLL_SECONDS)
            try:
                await self.tick()
            except Exception:  # a bad minute must not stop the DJ
                logger.exception("DJ tick failed")

    async def tick(self) -> Optional[dict]:
        """One look at Spotify. Returns the finished job when it queued a song."""
        if not self.enabled or not self.polling:
            self._anchor = self._paused_since = None
            return None
        try:
            playing = await asyncio.to_thread(self.spotify.is_playing)
        except Exception as e:  # Spotify hiccup: look again next minute
            logger.warning("DJ could not read playback (%s)", e)
            return None
        now = self.clock()
        if not playing:
            if self._paused_since is None:
                self._paused_since = now
            elif now - self._paused_since >= PAUSE_GRACE_SECONDS:
                self._anchor = None  # the session is over
            return None
        self._paused_since = None
        if self._anchor is None:
            self._anchor = now  # the first song comes one interval into a session
            return None
        if now - self._anchor < self.minutes * 60 or self._capped():
            return None
        if self.queue.recent() and any(
            j["status"] in ("queued", "running") for j in self.queue.recent()
        ):
            return None  # you asked for something; the DJ waits for it
        self._anchor = now
        return await self._add_song()

    def _capped(self) -> bool:
        today = date.fromtimestamp(self.wall())
        if today != self._today:
            self._today, self._added_today = today, 0
        return self._added_today >= self.max_per_day

    # ── started from outside (Home Assistant) ───────────────────────────
    async def trigger(self, hint: str = "", require_playing: bool = True) -> dict:
        """Queue one song now, if the rules allow it. Answers at once; the pick
        itself takes a minute and is announced when it is done."""
        if not self.enabled:
            return _skipped("DJ mode is off")
        if self._capped():
            return _skipped(f"already added {self.max_per_day} songs today")
        now = self.wall()
        if (
            self._last_trigger is not None
            and now - self._last_trigger < MIN_TRIGGER_GAP_SECONDS
        ):
            return _skipped("too soon after the last song")
        if any(j["status"] in ("queued", "running") for j in self.queue.recent()):
            return _skipped("busy with another request")
        if require_playing:
            try:
                playing = await asyncio.to_thread(self.spotify.is_playing)
            except Exception as e:
                logger.warning("DJ could not read playback (%s)", e)
                return _skipped("could not read Spotify")
            if not playing:
                return _skipped("nothing is playing")
        self._last_trigger = now
        task = asyncio.create_task(
            self._add_song(clean_hint(hint), source=TRIGGER_SOURCE)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return {"status": "started"}

    async def _add_song(self, hint: str = "", source: str = SOURCE) -> Optional[dict]:
        try:
            job = self.queue.submit("song", source=source, depth="quick", prompt=hint)
        except QueueFull:
            return None  # try again next minute
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        snapshot = None
        while time.monotonic() < deadline:
            snapshot = self.queue.snapshot(job.id)
            if snapshot is None or snapshot["status"] in (DONE, FAILED):
                break
            await asyncio.sleep(JOB_POLL_SECONDS)
        if not snapshot or snapshot["status"] != DONE:
            logger.warning("DJ pick failed: %s", (snapshot or {}).get("error"))
            return snapshot
        outcome = snapshot["result"]["outcome"]
        self._added_today += 1
        self.last = {
            "title": outcome["track"]["title"],
            "artist": outcome["track"]["artist"],
            "at": self.wall(),
            "playback": outcome["playback"],
        }
        if self.notify:
            try:
                await self.notify(snapshot)
            except Exception:  # the song is queued either way
                logger.exception("DJ could not announce the song")
        return snapshot


def _skipped(reason: str) -> dict:
    return {"status": "skipped", "reason": reason}


def clean_hint(text: str) -> str:
    """A note about the moment, as one short line. It is context for the song
    picker, never an instruction, so it is kept small and plain."""
    return " ".join((text or "").split())[:HINT_MAX]
