import time

import pytest

from agent.schemas import PlaylistOutcome, SongOutcome, TrackInfo
from models.song_key import song_key
from store import history
from store.history import DISLIKE, LIKE, Store

DAY = 86400


class Clock:
    def __init__(self):
        self.now = 1_800_000_000

    def __call__(self):
        return self.now

    def advance(self, days=0, seconds=0):
        self.now += days * DAY + seconds


def track(n, title=None, artist=None, uri=None):
    return TrackInfo(
        uri=uri or f"spotify:track:{n}",
        title=title or f"Song {n}",
        artist=artist or f"Artist {n}",
        album=f"Album {n}",
        year="2024",
    )


def playlist(*tracks, name="Mix"):
    return PlaylistOutcome(
        name=name,
        reason="because",
        research="notes",
        playlist_url="https://open.spotify.com/playlist/p1",
        tracks=list(tracks),
        playback="none",
        dry_run=False,
    )


def song(t):
    return SongOutcome(track=t, reason="because", playback="none", dry_run=False)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return Store(tmp_path / "data" / "auralis.db", clock=clock)


class TestHistory:
    def test_records_a_playlist_with_its_tracks_in_order(self, store):
        sid = store.record_playlist(
            playlist(track(1), track(2), track(3)), "neon drive", "auto", "web"
        )
        [entry] = store.history()
        assert entry["id"] == sid and entry["kind"] == "playlist"
        assert entry["prompt"] == "neon drive" and entry["depth"] == "auto"
        assert entry["source"] == "web" and entry["name"] == "Mix"
        assert [t["title"] for t in entry["tracks"]] == ["Song 1", "Song 2", "Song 3"]
        assert all(t["rating"] is None for t in entry["tracks"])

    def test_records_a_song(self, store):
        store.record_song(song(track(1)), "quick", "discord")
        [entry] = store.history()
        assert entry["kind"] == "song" and entry["prompt"] is None
        assert entry["source"] == "discord" and entry["name"] == "Song 1"

    def test_newest_first_and_paged(self, store, clock):
        for n in range(1, 6):
            clock.advance(seconds=60)
            store.record_song(song(track(n)), "quick", "web")
        assert [e["name"] for e in store.history(limit=2)] == ["Song 5", "Song 4"]
        assert [e["name"] for e in store.history(limit=2, offset=2)] == [
            "Song 3",
            "Song 2",
        ]

    def test_data_survives_reopening_and_is_shared_between_instances(
        self, store, tmp_path
    ):
        store.record_song(song(track(1)), "quick", "web")
        other = Store(tmp_path / "data" / "auralis.db")
        assert other.history()[0]["name"] == "Song 1"
        other.record_song(song(track(2)), "quick", "web")
        assert len(store.history()) == 2


class TestBackToBackRule:
    def test_only_songs_from_the_latest_creations_are_listed(self, store):
        store.record_song(song(track(1)), "quick", "web")
        store.record_playlist(playlist(track(2), track(3)), "x", "auto", "web")
        store.record_song(song(track(4)), "quick", "web")
        recent = store.recent_songs(2)
        assert sorted(recent) == [
            ("Song 2", "Artist 2"),
            ("Song 3", "Artist 3"),
            ("Song 4", "Artist 4"),
        ]
        assert ("Song 1", "Artist 1") not in recent

    def test_nothing_recorded_means_nothing_excluded(self, store):
        assert store.recent_songs(2) == []

    def test_a_song_repeated_across_the_window_is_listed_once(self, store):
        store.record_song(song(track(1)), "quick", "web")
        store.record_song(song(track(1)), "quick", "web")
        assert store.recent_songs(2) == [("Song 1", "Artist 1")]


class TestRatings:
    def test_like_dislike_and_back_to_neutral(self, store):
        sid = store.record_playlist(playlist(track(1), track(2)), "x", "auto", "web")
        store.rate_track(sid, "spotify:track:1", LIKE)
        store.rate_track(sid, "spotify:track:2", DISLIKE)
        ratings = {t["title"]: t["rating"] for t in store.history()[0]["tracks"]}
        assert ratings == {"Song 1": LIKE, "Song 2": DISLIKE}
        store.rate_track(sid, "spotify:track:1", DISLIKE)  # change of mind
        store.rate_track(sid, "spotify:track:2", None)  # back to neutral
        ratings = {t["title"]: t["rating"] for t in store.history()[0]["tracks"]}
        assert ratings == {"Song 1": DISLIKE, "Song 2": None}
        assert [r["title"] for r in store.ratings()] == ["Song 1"]

    def test_a_rating_follows_the_song_across_suggestions_and_releases(self, store):
        first = store.record_song(song(track(1, "Anthem", "Band")), "quick", "web")
        store.record_song(
            song(track(2, "Anthem - Remastered 2011", "Band", uri="spotify:track:alt")),
            "quick",
            "web",
        )
        store.rate_track(first, "spotify:track:1", LIKE)
        newest = store.history()[0]["tracks"][0]
        assert newest["uri"] == "spotify:track:alt" and newest["rating"] == LIKE

    def test_the_tab_lists_everything_rated_newest_change_first(self, store, clock):
        sid = store.record_playlist(
            playlist(track(1), track(2), track(3)), "x", "auto", "web"
        )
        for n, rating in ((1, LIKE), (2, DISLIKE), (3, LIKE)):
            clock.advance(seconds=10)
            store.rate_track(sid, f"spotify:track:{n}", rating)
        assert [r["title"] for r in store.ratings()] == ["Song 3", "Song 2", "Song 1"]
        assert [r["title"] for r in store.ratings(LIKE)] == ["Song 3", "Song 1"]
        assert [r["title"] for r in store.ratings(DISLIKE)] == ["Song 2"]

    def test_changing_a_rating_from_the_tab(self, store):
        sid = store.record_song(song(track(1)), "quick", "web")
        store.rate_track(sid, "spotify:track:1", LIKE)
        key = song_key("Song 1", "Artist 1")
        store.change_rating(key, DISLIKE)
        assert store.ratings()[0]["rating"] == DISLIKE
        store.change_rating(key, None)
        assert store.ratings() == []
        assert store.history()[0]["tracks"][0]["rating"] is None

    def test_rating_something_unknown_is_an_error(self, store):
        sid = store.record_song(song(track(1)), "quick", "web")
        with pytest.raises(KeyError):
            store.rate_track(sid, "spotify:track:nope", LIKE)
        with pytest.raises(KeyError):
            store.change_rating("nobody|nothing", LIKE)

    def test_only_like_dislike_or_none_are_valid(self, store):
        sid = store.record_song(song(track(1)), "quick", "web")
        with pytest.raises(ValueError):
            store.rate_track(sid, "spotify:track:1", "love")
        assert store.ratings() == []

    def test_taste_signals_are_the_latest_likes_and_dislikes(self, store, clock):
        sid = store.record_playlist(
            playlist(*[track(n) for n in range(1, 6)]), "x", "auto", "web"
        )
        for n, rating in ((1, LIKE), (2, LIKE), (3, DISLIKE), (4, LIKE)):
            clock.advance(seconds=10)
            store.rate_track(sid, f"spotify:track:{n}", rating)
        signals = store.taste_signals(limit=2)
        assert signals[LIKE] == [("Song 4", "Artist 4"), ("Song 2", "Artist 2")]
        assert signals[DISLIKE] == [("Song 3", "Artist 3")]


class TestPruning:
    def test_old_history_goes_but_ratings_stay(self, store, clock):
        sid = store.record_playlist(playlist(track(1), track(2)), "x", "auto", "web")
        store.rate_track(sid, "spotify:track:1", LIKE)
        clock.advance(days=history.RETENTION_DAYS + 1)
        assert store.prune() == 1
        assert store.history() == []
        assert [r["title"] for r in store.ratings()] == ["Song 1"]

    def test_recent_history_is_kept(self, store, clock):
        store.record_song(song(track(1)), "quick", "web")
        clock.advance(days=history.RETENTION_DAYS - 1)
        assert store.prune() == 0
        assert len(store.history()) == 1

    def test_the_number_of_suggestions_is_capped(self, store, monkeypatch):
        monkeypatch.setattr(history, "MAX_SUGGESTIONS", 3)
        for n in range(1, 7):
            store.record_song(song(track(n)), "quick", "web")
        assert [e["name"] for e in store.history()] == ["Song 6", "Song 5", "Song 4"]

    def test_pruned_suggestions_take_their_tracks_with_them(self, store, clock):
        store.record_playlist(playlist(track(1), track(2)), "x", "auto", "web")
        clock.advance(days=history.RETENTION_DAYS + 1)
        store.prune()
        with store._connect() as db:
            assert (
                db.execute("SELECT COUNT(*) FROM suggestion_tracks").fetchone()[0] == 0
            )

    def test_the_file_stays_small_however_long_it_is_used(
        self, tmp_path, clock, monkeypatch
    ):
        monkeypatch.setattr(history, "MAX_SUGGESTIONS", 40)
        store = Store(tmp_path / "big.db", clock=clock)
        for n in range(120):
            clock.advance(seconds=60)
            store.record_playlist(
                playlist(*[track(n * 30 + i) for i in range(30)]),
                "p" * 80,
                "deep",
                "web",
            )
        assert len(store.history(limit=1000)) == 40
        with store._connect() as db:
            assert (
                db.execute("SELECT COUNT(*) FROM suggestion_tracks").fetchone()[0]
                == 1200
            )
        # 120 creations went through; the file holds only the 40 newest
        assert (tmp_path / "big.db").stat().st_size < 600_000


class TestSettings:
    def test_settings_round_trip_and_default(self, tmp_path):
        store = Store(tmp_path / "s.db")
        assert store.get_setting("dj.enabled", False) is False
        store.set_setting("dj.enabled", True)
        store.set_setting("dj.minutes", 45)
        store.set_setting("dj.minutes", 20)  # replaces
        reopened = Store(tmp_path / "s.db")
        assert reopened.get_setting("dj.enabled") is True
        assert reopened.get_setting("dj.minutes") == 20

    def test_an_existing_v1_database_is_upgraded_and_keeps_its_history(self, tmp_path):
        import sqlite3

        path = tmp_path / "old.db"
        db = sqlite3.connect(path)
        db.executescript(history._MIGRATIONS[1])
        db.execute("PRAGMA user_version = 1")
        db.execute(
            "INSERT INTO suggestions (created_at, kind, depth, source, name, reason) "
            "VALUES (?, 'song', 'quick', 'web', 'Old', 'r')",
            (int(time.time()) - DAY,),
        )
        db.commit()
        db.close()
        store = Store(path)
        store.set_setting("dj.enabled", True)
        assert store.get_setting("dj.enabled") is True
        assert [h["name"] for h in store.history()] == ["Old"]
