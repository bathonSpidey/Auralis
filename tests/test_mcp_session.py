import pytest

from auralis_mcp.session import (
    RunRules,
    RunSession,
    read_outcome,
    read_verified,
    write_rules,
)
from models.artist import Artist
from models.playlist import Playlist
from models.song import Song


def song(n, artist=None, title=None):
    artist = artist or f"Artist {n}"
    return Song(
        id=str(n),
        uri=f"spotify:track:{n}",
        name=title or f"Song {n}",
        artists=[Artist(name=artist, uri=f"spotify:artist:{artist}")],
    )


class FakeSpotify:
    def __init__(self, fail_adding=False):
        self.fail_adding = fail_adding
        self.created = []
        self.added = []
        self.deleted = []

    def create_playlist(self, name, description=""):
        self.created.append((name, description))
        return Playlist(id="p1", href="h", uri="spotify:playlist:p1", name=name)

    def add_to_playlist(self, playlist_id, uris):
        if self.fail_adding:
            raise RuntimeError("spotify down")
        self.added.append((playlist_id, list(uris)))

    def delete_playlist(self, uri):
        self.deleted.append(uri)


def make_session(tmp_path, spotify=None, tracks=10, **rules):
    spotify = spotify or FakeSpotify()
    write_rules(tmp_path, RunRules(min_songs=3, max_songs=8, **rules))
    session = RunSession(spotify, tmp_path)
    session.remember([song(n) for n in range(1, tracks + 1)])
    return session, spotify


def uris(*numbers):
    return [f"spotify:track:{n}" for n in numbers]


def pairs(*numbers):
    return [[f"Song {n}", f"Artist {n}"] for n in numbers]


class TestRules:
    def test_a_valid_playlist_is_created_and_recorded(self, tmp_path):
        session, spotify = make_session(tmp_path)
        result = session.submit("Drive", "desc", uris(1, 2, 3))
        assert result["ok"] is True
        assert spotify.created == [("Drive", "desc")]
        assert spotify.added == [("p1", uris(1, 2, 3))]
        outcome = read_outcome(tmp_path)
        assert outcome["playlist_url"] == "https://open.spotify.com/playlist/p1"
        assert [t["title"] for t in outcome["tracks"]] == ["Song 1", "Song 2", "Song 3"]

    def test_unverified_uris_are_rejected(self, tmp_path):
        session, spotify = make_session(tmp_path)
        result = session.submit("Drive", "", uris(1, 2, 99))
        assert result["ok"] is False
        assert "spotify:track:99" in result["violations"][0]
        assert spotify.created == []

    def test_duplicates_are_rejected(self, tmp_path):
        session, _ = make_session(tmp_path)
        violations = session.submit("Drive", "", uris(1, 1, 2, 3))["violations"]
        assert any("same song" in v and "Song 1" in v for v in violations)

    @pytest.mark.parametrize("count", [2, 9])
    def test_length_is_bounded(self, tmp_path, count):
        session, _ = make_session(tmp_path, tracks=12)
        result = session.submit("Drive", "", uris(*range(1, count + 1)))
        assert any("between 3 and 8" in v for v in result["violations"])

    def test_excluded_tracks_are_rejected_by_name(self, tmp_path):
        session, _ = make_session(tmp_path, excluded_tracks=[["Song 2", "Artist 2"]])
        violations = session.submit("Drive", "", uris(1, 2, 3))["violations"]
        assert any("Song 2" in v and "disliked" in v for v in violations)

    def test_another_release_of_an_excluded_song_is_still_excluded(self, tmp_path):
        session, spotify = make_session(
            tmp_path, excluded_tracks=[["Opalite", "Taylor Swift"]]
        )
        session.remember(
            [
                song(31, "Taylor Swift", "Opalite"),
                song(32, "Taylor Swift", "Opalite - Single Version"),
            ]
        )
        for variant in (31, 32):
            violations = session.submit("Drive", "", uris(1, 2, variant))["violations"]
            assert any("disliked" in v for v in violations)
        assert spotify.created == []

    def test_two_releases_of_one_song_count_as_a_duplicate(self, tmp_path):
        session, _ = make_session(tmp_path)
        session.remember(
            [song(41, "Band", "Anthem"), song(42, "Band", "Anthem (Remastered 2011)")]
        )
        violations = session.submit("Drive", "", uris(1, 41, 42))["violations"]
        assert any("same song" in v for v in violations)

    def test_artist_cap(self, tmp_path):
        session, _ = make_session(tmp_path, max_per_artist=2)
        session.remember([song(n, "Same Band") for n in (21, 22, 23)])
        violations = session.submit("Drive", "", uris(21, 22, 23, 1))["violations"]
        assert any("Same Band appears 3 times" in v for v in violations)

    def test_familiar_tracks_are_capped_at_the_allowance(self, tmp_path):
        session, _ = make_session(
            tmp_path, familiar_tracks=pairs(1, 2, 3, 4, 5, 6), familiar_allowance=2
        )
        violations = session.submit("Drive", "", uris(1, 2, 3, 7))["violations"]
        assert any("at most 2" in v for v in violations)

    def test_familiar_tracks_within_the_allowance_pass(self, tmp_path):
        session, _ = make_session(
            tmp_path, familiar_tracks=pairs(1, 2), familiar_allowance=2
        )
        assert session.submit("Drive", "", uris(1, 2, 3))["ok"] is True

    def test_all_violations_are_reported_together(self, tmp_path):
        session, _ = make_session(tmp_path, excluded_tracks=pairs(1))
        violations = session.submit("", "", uris(1, 99))["violations"]
        assert len(violations) >= 4  # name, unknown, length, excluded

    def test_name_length_limit(self, tmp_path):
        session, _ = make_session(tmp_path)
        violations = session.submit("x" * 101, "", uris(1, 2, 3))["violations"]
        assert any("too long" in v for v in violations)


class TestSubmission:
    def test_only_one_playlist_per_run(self, tmp_path):
        session, spotify = make_session(tmp_path)
        session.submit("One", "", uris(1, 2, 3))
        second = session.submit("Two", "", uris(4, 5, 6))
        assert second["ok"] is False
        assert "already created" in second["violations"][0]
        assert len(spotify.created) == 1

    def test_a_rejected_submission_can_be_retried(self, tmp_path):
        session, spotify = make_session(tmp_path)
        assert session.submit("Drive", "", uris(1, 2))["ok"] is False
        assert session.submit("Drive", "", uris(1, 2, 3))["ok"] is True

    def test_dry_run_validates_and_records_without_touching_spotify(self, tmp_path):
        session, spotify = make_session(tmp_path, dry_run=True)
        result = session.submit("Drive", "", uris(1, 2, 3))
        assert result["ok"] is True
        assert "dry run" in result["message"]
        assert result["playlist_url"] is None
        assert spotify.created == []
        assert read_outcome(tmp_path)["dry_run"] is True

    def test_a_failed_add_rolls_the_playlist_back(self, tmp_path):
        session, spotify = make_session(tmp_path, spotify=FakeSpotify(fail_adding=True))
        with pytest.raises(RuntimeError, match="spotify down"):
            session.submit("Drive", "", uris(1, 2, 3))
        assert spotify.deleted == ["spotify:playlist:p1"]
        assert read_outcome(tmp_path) is None

    def test_a_rejected_submission_leaves_no_outcome(self, tmp_path):
        session, _ = make_session(tmp_path)
        session.submit("Drive", "", uris(1))
        assert read_outcome(tmp_path) is None


class TestVerifiedTracks:
    def test_verified_tracks_survive_a_new_session(self, tmp_path):
        make_session(tmp_path)
        second = RunSession(FakeSpotify(), tmp_path)
        assert second.submit("Drive", "", uris(1, 2, 3))["ok"] is True

    def test_verified_file_records_artist_for_the_service(self, tmp_path):
        make_session(tmp_path)
        entry = read_verified(tmp_path)["spotify:track:1"]
        assert entry["artist"] == "Artist 1"
        assert entry["artist_uri"] == "spotify:artist:Artist 1"


class TestSubmitSong:
    def test_a_fresh_verified_song_is_accepted(self, tmp_path):
        session, _ = make_session(tmp_path)
        result = session.submit_song("spotify:track:1", "fits the mood")
        assert result["ok"] is True
        outcome = read_outcome(tmp_path)
        assert outcome["kind"] == "song"
        assert outcome["track"]["title"] == "Song 1"

    def test_unverified_song_is_rejected(self, tmp_path):
        session, _ = make_session(tmp_path)
        result = session.submit_song("spotify:track:99", "why")
        assert result["ok"] is False and "never returned" in result["violations"][0]

    def test_excluded_and_familiar_songs_are_rejected_whatever_the_release(
        self, tmp_path
    ):
        session, _ = make_session(
            tmp_path,
            excluded_tracks=pairs(1),
            familiar_tracks=[["Anthem", "Band"]],
        )
        session.remember([song(41, "Band", "Anthem (Remastered 2011)")])
        assert (
            "suggested before"
            in session.submit_song("spotify:track:1", "x")["violations"][0]
        )
        assert (
            "already in"
            in session.submit_song("spotify:track:41", "x")["violations"][0]
        )
        assert read_outcome(tmp_path) is None

    def test_a_reason_is_required(self, tmp_path):
        session, _ = make_session(tmp_path)
        assert session.submit_song("spotify:track:1", " ")["ok"] is False

    def test_only_one_song_per_run(self, tmp_path):
        session, _ = make_session(tmp_path)
        session.submit_song("spotify:track:1", "x")
        assert session.submit_song("spotify:track:2", "x")["ok"] is False
