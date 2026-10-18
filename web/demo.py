"""Canned stand-ins so the UI can be built and shown without Spotify or Claude."""

import tempfile
import time
from pathlib import Path

from agent.depth import Depth
from agent.schemas import PlaylistOutcome, SongOutcome, TrackInfo
from models.device import Device
from store.history import DISLIKE, LIKE, Store

STAGE_SECONDS = 1.2

TRACKS = [
    ("Maria También", "Khruangbin", "Con Todo El Mundo", "2018"),
    ("Brokendate", "Com Truise", "Galactic Melt", "2011"),
    ("Oban", "Jaga Jazzist", "Starfire", "2015"),
    ("Flight", "Hidden Orchestra", "Archipelago", "2012"),
    ("Roygbiv", "Boards of Canada", "Music Has the Right to Children", "1998"),
    ("Looped", "Kiasmos", "Kiasmos", "2014"),
    ("Yèkèrmo Sèw", "Mulatu Astatke", "Ethiopiques 4", "1969"),
    ("Window", "The Album Leaf", "In a Safe Place", "2004"),
    ("Panacea", "Disasterpeace", "Hyper Light Drifter OST", "2016"),
    ("Monday Loop", "Tomppabeats", "Harbor", "2016"),
]


def _track(i: int) -> TrackInfo:
    title, artist, album, year = TRACKS[i % len(TRACKS)]
    return TrackInfo(
        uri=f"spotify:track:demo{i:02d}",
        title=title,
        artist=artist,
        album=album,
        year=year,
    )


class DemoSpotify:
    def devices(self):
        return [
            Device(id="pc", is_active=True, name="Spidey's PC", type="Computer"),
            Device(id="kitchen", is_active=False, name="Kitchen", type="Speaker"),
            Device(id="office", is_active=False, name="KazukiBTOffice", type="Speaker"),
        ]

    def logged_in(self):
        return True


class DemoAuralis:
    def __init__(self, store: Store):
        self.store = store

    def _walk(self, stages, progress):
        for stage in stages:
            progress and progress(stage)
            time.sleep(STAGE_SECONDS)

    def playlist_generator(
        self,
        prompt,
        depth=Depth.AUTO,
        dry_run=False,
        device_id=None,
        source="web",
        progress=None,
    ):
        self._walk(("taste", "scout", "curate", "finish"), progress)
        outcome = PlaylistOutcome(
            name="Midnight Compile",
            reason=(
                "It opens with warm groove, builds through jazz-electronic and IDM for the "
                "focused middle, then eases down through math rock and film score. Sixteen "
                "tracks fills about an hour without the very long pieces."
            ),
            research=(
                "A late-night focus session. Mostly instrumental with steady momentum, "
                "spread across post-rock, krautrock, electronica and jazz. Your recent "
                "ambient and neoclassical staples appear only as brief breathers."
            ),
            playlist_url=None if dry_run else "https://open.spotify.com/playlist/demo",
            tracks=[_track(i) for i in range(10)],
            playback="none",
            dry_run=dry_run,
        )
        if not dry_run:
            outcome.id = self.store.record_playlist(
                outcome, prompt, Depth(depth).value, source
            )
        return outcome

    def song_of_the_moment_suggestion(
        self,
        depth=Depth.QUICK,
        dry_run=False,
        device_id=None,
        source="web",
        progress=None,
    ):
        self._walk(("taste", "pick", "finish"), progress)
        outcome = SongOutcome(
            track=TrackInfo(
                uri="spotify:track:demofeel",
                title="Feel",
                artist="Hiroshi Yoshimura",
                album="Green",
                year="1986",
            ),
            reason=(
                "Your night listening leans ambient and neoclassical. This is a step to Japan: "
                "soft, glassy keys that suit a quiet autumn evening."
            ),
            playback="none",
            dry_run=dry_run,
        )
        if not dry_run:
            outcome.id = self.store.record_song(outcome, Depth(depth).value, source)
        return outcome

    def commit_playlist(
        self, preview, prompt, depth=Depth.AUTO, device_id=None, source="web"
    ):
        self._walk(("create",), None)
        result = preview.model_copy(
            update={
                "dry_run": False,
                "playlist_url": "https://open.spotify.com/playlist/demo",
                "playback": "playing" if device_id else "none",
            }
        )
        result.id = self.store.record_playlist(
            result, prompt, Depth(depth).value, source
        )
        return result

    def commit_song(self, preview, depth=Depth.QUICK, device_id=None, source="web"):
        self._walk(("create",), None)
        result = preview.model_copy(
            update={"dry_run": False, "playback": "playing" if device_id else "none"}
        )
        result.id = self.store.record_song(result, Depth(depth).value, source)
        return result


def build_demo():
    path = Path(tempfile.gettempdir()) / "auralis-demo.db"
    path.unlink(missing_ok=True)
    clock = [time.time() - 5 * 86400]
    store = Store(path, clock=lambda: clock[0])

    def at(hours):
        clock[0] += hours * 3600

    def seed(name, prompt, depth, source, indices):
        outcome = PlaylistOutcome(
            name=name,
            reason="Seeded example for the demo.",
            research="",
            playlist_url="https://open.spotify.com/playlist/demo",
            tracks=[_track(i) for i in indices],
            playback="none",
            dry_run=False,
        )
        return store.record_playlist(outcome, prompt, depth, source)

    first = seed(
        "Neon Tokyo After Dark",
        "80s Japanese city pop and its modern revival",
        "deep",
        "web",
        range(0, 7),
    )
    at(30)
    second = seed(
        "Rainy Sunday Kitchen",
        "Rainy Sunday cooking, something warm",
        "auto",
        "discord",
        range(3, 9),
    )
    at(20)
    store.record_song(
        SongOutcome(
            track=_track(8),
            reason="A quiet pivot toward game scores.",
            playback="none",
            dry_run=False,
        ),
        "quick",
        "schedule",
    )
    store.rate_track(first, "spotify:track:demo00", LIKE)
    store.rate_track(first, "spotify:track:demo03", LIKE)
    store.rate_track(second, "spotify:track:demo06", DISLIKE)
    clock[0] = time.time()
    return DemoAuralis(store), store, DemoSpotify()
