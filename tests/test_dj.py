import asyncio

import pytest

from store.history import Store
from web import dj as dj_module
from web.dj import Dj
from web.jobs import JobQueue

SONG = {
    "id": 5,
    "track": {"uri": "spotify:track:abc", "title": "Slow Burn", "artist": "Someone"},
    "reason": "Flows on.",
    "playback": "queued",
    "dry_run": False,
}


class Time:
    """One clock the tests move by hand."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def minutes(self, n):
        self.now += n * 60


class FakeSpotify:
    def __init__(self):
        self.playing = True
        self.broken = False

    def is_playing(self):
        if self.broken:
            raise RuntimeError("Spotify hiccup")
        return self.playing


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(dj_module, "JOB_POLL_SECONDS", 0.01)
    time = Time()
    spotify = FakeSpotify()
    runs, told = [], []

    def runner(job, progress):
        runs.append(job)
        return {"kind": "song", "outcome": SONG}

    queue = JobQueue(runner, autostart=False)

    async def notify(snapshot):
        told.append(snapshot)

    store = Store(tmp_path / "dj.db")
    dj = Dj(spotify, queue, store, notify=notify, clock=time, wall=time)

    class World:
        pass

    w = World()
    w.time, w.spotify, w.runs, w.told = time, spotify, runs, told
    w.queue, w.store, w.dj = queue, store, dj

    async def tick():
        """One tick, with a stand-in worker finishing whatever it queues."""
        task = asyncio.create_task(dj.tick())
        while not task.done():
            queue.run_pending()
            await asyncio.sleep(0.01)
        return task.result()

    w.tick = lambda: asyncio.run(tick())
    return w


class TestSettings:
    def test_off_by_default_and_remembered(self, world, tmp_path):
        assert world.dj.enabled is False and world.dj.minutes == 30
        world.dj.configure(enabled=True, minutes=45)
        again = Dj(FakeSpotify(), world.queue, Store(tmp_path / "dj.db"))
        assert again.enabled is True and again.minutes == 45

    def test_the_interval_has_sane_bounds(self, world):
        with pytest.raises(ValueError):
            world.dj.configure(minutes=2)
        with pytest.raises(ValueError):
            world.dj.configure(minutes=500)


class TestSessions:
    def test_does_nothing_while_off(self, world):
        assert world.tick() is None
        assert world.runs == [] and world.dj.status()["listening"] is False

    def test_first_song_comes_one_interval_into_listening(self, world):
        world.dj.configure(enabled=True)
        assert world.tick() is None  # session starts, nothing queued yet
        assert world.dj.status()["listening"] is True
        world.time.minutes(29)
        assert world.tick() is None and world.runs == []
        world.time.minutes(2)
        snapshot = world.tick()
        assert snapshot["status"] == "done"
        job = world.runs[0]
        assert (job.kind, job.source, job.depth) == ("song", "dj", "quick")
        assert job.device_id == "queue-only"  # joins a queue, never starts music

    def test_then_one_song_every_interval(self, world):
        world.dj.configure(enabled=True, minutes=20)
        world.tick()
        for _ in range(3):
            world.time.minutes(21)
            world.tick()
        assert len(world.runs) == 3
        world.time.minutes(10)
        world.tick()
        assert len(world.runs) == 3

    def test_the_channel_is_told_and_the_last_song_is_kept(self, world):
        world.dj.configure(enabled=True, minutes=10)
        world.tick()
        world.time.minutes(11)
        world.tick()
        assert len(world.told) == 1
        last = world.dj.status()["last"]
        assert (last["title"], last["playback"]) == ("Slow Burn", "queued")
        assert world.dj.status()["added_today"] == 1

    def test_nothing_is_queued_into_silence(self, world):
        world.dj.configure(enabled=True, minutes=10)
        world.tick()
        world.spotify.playing = False
        world.time.minutes(30)
        world.tick()
        assert world.runs == []

    def test_a_short_pause_keeps_the_session(self, world):
        world.dj.configure(enabled=True, minutes=10)
        world.tick()
        world.spotify.playing = False
        world.time.minutes(3)
        world.tick()
        world.spotify.playing = True
        world.time.minutes(8)
        world.tick()
        assert len(world.runs) == 1  # 11 minutes since the session began

    def test_a_long_pause_ends_the_session(self, world):
        world.dj.configure(enabled=True, minutes=10)
        world.tick()
        world.spotify.playing = False
        world.tick()
        world.time.minutes(15)
        world.tick()
        assert world.dj.status()["listening"] is False
        world.spotify.playing = True
        world.tick()  # a new session starts: the clock restarts
        world.time.minutes(5)
        world.tick()
        assert world.runs == []

    def test_a_spotify_hiccup_is_skipped(self, world):
        world.dj.configure(enabled=True, minutes=10)
        world.tick()
        world.spotify.broken = True
        world.time.minutes(20)
        assert world.tick() is None and world.runs == []
        world.spotify.broken = False
        world.tick()
        assert len(world.runs) == 1

    def test_waits_while_you_have_a_request_running(self, world):
        world.dj.configure(enabled=True, minutes=10)
        world.tick()
        world.queue.submit("playlist", prompt="mine")  # not run yet
        world.time.minutes(11)

        async def tick_without_worker():
            return await world.dj.tick()

        assert asyncio.run(tick_without_worker()) is None
        assert world.runs == []

    def test_a_daily_cap_stops_a_runaway(self, world):
        world.dj.max_per_day = 2
        world.dj.configure(enabled=True, minutes=10)
        world.tick()
        for _ in range(5):
            world.time.minutes(11)
            world.tick()
        assert len(world.runs) == 2

    def test_a_failed_pick_does_not_announce_or_count(self, world):
        def broken(job, progress):
            raise RuntimeError("Claude is down")

        world.queue.runner = broken
        world.dj.configure(enabled=True, minutes=10)
        world.tick()
        world.time.minutes(11)
        world.tick()
        assert world.told == [] and world.dj.status()["added_today"] == 0

    def test_status_says_when_the_next_song_is_due(self, world):
        world.dj.configure(enabled=True, minutes=30)
        world.tick()
        world.time.minutes(10)
        status = world.dj.status()
        assert status["next_at"] == pytest.approx(world.time.now + 20 * 60)


class TestTriggered:
    """Home Assistant starts the song; Auralis only checks the rules."""

    def trigger(self, world, **kwargs):
        async def go():
            result = await world.dj.trigger(**kwargs)
            while world.dj._tasks:  # let the background pick finish
                world.queue.run_pending()
                await asyncio.sleep(0.01)
            return result

        return asyncio.run(go())

    def test_a_trigger_queues_one_song_and_announces_it(self, world):
        world.dj.configure(enabled=True, polling=False)
        assert self.trigger(world, hint="rainy evening, working at the desk") == {
            "status": "started"
        }
        job = world.runs[0]
        assert (job.kind, job.source, job.depth) == ("song", "ha", "quick")
        assert job.prompt == "rainy evening, working at the desk"
        assert len(world.told) == 1 and world.dj.status()["added_today"] == 1

    def test_nothing_happens_while_dj_mode_is_off(self, world):
        result = self.trigger(world)
        assert result == {"status": "skipped", "reason": "DJ mode is off"}
        assert world.runs == []

    def test_nothing_is_queued_into_silence(self, world):
        world.dj.configure(enabled=True)
        world.spotify.playing = False
        assert self.trigger(world)["reason"] == "nothing is playing"
        assert world.runs == []

    def test_require_playing_can_be_waived(self, world):
        world.dj.configure(enabled=True)
        world.spotify.playing = False
        assert self.trigger(world, require_playing=False)["status"] == "started"

    def test_a_second_call_too_soon_is_refused(self, world):
        world.dj.configure(enabled=True)
        assert self.trigger(world)["status"] == "started"
        world.time.minutes(2)
        assert self.trigger(world)["reason"] == "too soon after the last song"
        world.time.minutes(4)
        assert self.trigger(world)["status"] == "started"
        assert len(world.runs) == 2

    def test_the_daily_cap_applies(self, world):
        world.dj.max_per_day = 1
        world.dj.configure(enabled=True)
        assert self.trigger(world)["status"] == "started"
        world.time.minutes(10)
        assert "already added" in self.trigger(world)["reason"]

    def test_it_waits_behind_a_request_of_your_own(self, world):
        world.dj.configure(enabled=True)
        world.queue.submit("playlist", prompt="mine")
        assert self.trigger(world)["reason"] == "busy with another request"

    def test_a_spotify_hiccup_is_a_skip_not_an_error(self, world):
        world.dj.configure(enabled=True)
        world.spotify.broken = True
        assert self.trigger(world)["reason"] == "could not read Spotify"

    def test_the_hint_is_kept_short_and_on_one_line(self):
        text = "line one\n\n   line two " + "x" * 400
        cleaned = dj_module.clean_hint(text)
        assert "\n" not in cleaned and len(cleaned) <= dj_module.HINT_MAX
        assert dj_module.clean_hint(None) == ""


class TestPollingSwitch:
    def test_polling_is_on_by_default_and_can_be_turned_off(self, world):
        assert world.dj.polling is True
        assert world.dj.configure(polling=False)["polling"] is False

    def test_with_polling_off_auralis_does_not_watch_spotify(self, world):
        world.dj.configure(enabled=True, minutes=10, polling=False)
        world.spotify.broken = True  # any call to Spotify would raise
        world.tick()
        world.time.minutes(60)
        world.tick()
        assert world.runs == [] and world.dj.status()["listening"] is False
