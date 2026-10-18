import json
from pathlib import Path

import pytest

from agent.auralis import Auralis, AuralisError
from agent.depth import PLANS, Depth
from agent.schemas import PlaylistOutcome, SongOutcome
from auralis_mcp.session import RunSession
from models.album import Album
from models.artist import Artist
from models.playlist import Playlist
from models.song import Song
from spotify.client import SpotifyError
from spotify.library import NoDeviceError


def make_song(name="Track", artist="Artist"):
    return Song(
        id=name,
        uri=f"spotify:track:{name}",
        name=name,
        artists=[Artist(name=artist, uri=f"spotify:artist:{artist}")],
        album=Album(name="Album", release_date="2024-01-01"),
    )


CATALOGUE = [make_song(f"T{n}", f"Band {n}") for n in range(1, 13)]
URIS = [song.uri for song in CATALOGUE]


class FakeSpotify:
    def __init__(self, playing=False, has_device=True):
        self.playing = playing
        self.has_device = has_device
        self.created = []
        self.deleted = []
        self.played = []
        self.queued = []

    # listening
    def recently_played(self):
        return [make_song("Recent", "Recent Artist")]

    def top_tracks(self, limit=20, time_range="medium_term"):
        return [make_song(f"Top-{time_range}", "Top Artist")]

    def liked_songs_sample(self, count=20):
        return [make_song("Liked", "Liked Artist")]

    def user_playlists(self):
        return []

    def artist_genres(self, artist_uris):
        return {uri: ["indie", "pop"] for uri in artist_uris}

    # playlists (used by the real gate)
    def create_playlist(self, name, description=""):
        self.created.append(name)
        return Playlist(id="p1", href="h", uri="spotify:playlist:p1", name=name)

    def add_to_playlist(self, playlist_id, uris):
        pass

    def delete_playlist(self, uri):
        self.deleted.append(uri)

    # playback
    def is_playing(self):
        return self.playing

    def play_playlist(self, uri, device_id=None):
        if not self.has_device and device_id is None:
            raise NoDeviceError("none")
        self.played.append(("playlist", uri, device_id))

    def play_track(self, uri, device_id=None):
        if not self.has_device and device_id is None:
            raise NoDeviceError("none")
        self.played.append(("track", uri, device_id))

    def queue_track(self, uri, device_id=None):
        self.queued.append(uri)


class ScriptedAdvisor:
    """Plays the scout, curator and song picker against the real MCP session,
    so the gate's rules are the real ones."""

    def __init__(
        self,
        spotify,
        scout_uris=URIS,
        curator_attempts=(URIS[:8],),
        song_attempts=(URIS[0:1],),
    ):
        self.spotify = spotify
        self.scout_uris = scout_uris
        self.curator_attempts = curator_attempts
        self.song_attempts = song_attempts
        self.calls = []
        self.submit_results = []

    def advise(
        self,
        system_prompt,
        user_prompt,
        schema,
        *,
        mcp_config=None,
        allowed_tools=(),
        builtin_tools=(),
        max_budget_usd=None,
    ):
        env = mcp_config["mcpServers"]["auralis"]["env"]
        stage = env["AURALIS_STAGE"]
        self.calls.append(
            {
                "stage": stage,
                "system": system_prompt,
                "user": user_prompt,
                "builtin_tools": tuple(builtin_tools),
                "allowed_tools": tuple(allowed_tools),
                "budget": max_budget_usd,
                "schema": schema,
            }
        )
        session = RunSession(self.spotify, Path(env["AURALIS_RUN_DIR"]))
        if stage == "scout":
            session.remember(CATALOGUE)
            return {
                "interpretation": "Looked for upbeat tracks.",
                "candidates": [
                    {"uri": uri, "title": "x", "artist": "y", "why": "fits"}
                    for uri in self.scout_uris
                ],
            }
        if stage == "curator":
            for uris in self.curator_attempts:
                result = session.submit("Drive", "a description", uris)
                self.submit_results.append(result)
                if result["ok"]:
                    break
            return {"playlist_name": "Drive", "reason": "Because."}
        for uris in self.song_attempts:
            session.remember(CATALOGUE)
            result = session.submit_song(uris[0], "Nice.")
            self.submit_results.append(result)
            if result["ok"]:
                break
        return {"reason": "Because."}


def make_auralis(tmp_path, spotify=None, **advisor_args):
    spotify = spotify or FakeSpotify()
    advisor = ScriptedAdvisor(spotify, **advisor_args)
    return Auralis(spotify, advisor, runs_dir=tmp_path / "runs"), spotify, advisor


class FakeScraper:
    def get_trending_songs(self, country):
        return f"trending-{country}" if country != "jp" else None


class TestContext:
    def test_includes_every_part_of_the_listening_profile(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path)
        context = auralis.build_context()
        assert context["my_recently_played_songs"][0]["name"] == "Recent"
        assert context["my_top_tracks_this_month"][0]["name"] == "Top-short_term"
        assert context["my_top_tracks_overall"][0]["name"] == "Top-medium_term"
        assert context["my_liked_songs_sample"][0]["name"] == "Liked"
        assert context["my_current_weather"] is None
        assert "viral_charts" not in context

    def test_context_is_json_serialisable_and_leaves_out_ids_and_albums(self, tmp_path):
        context = make_auralis(tmp_path)[0].build_context()
        text = json.dumps(context)
        assert "spotify:track" not in text and "Album" not in text

    def test_genres_are_counted_across_distinct_artists(self, tmp_path):
        context = make_auralis(tmp_path)[0].build_context()
        assert context["my_recent_genre_distribution"] == {"indie": 2, "pop": 2}

    def test_unavailable_charts_are_left_out(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path)
        auralis.scrapper = FakeScraper()
        assert auralis.build_context()["trending_charts"] == [
            "trending-de",
            "trending-us",
            "trending-in",
        ]


class TestLikedSongsAreOptional:
    def test_a_missing_scope_degrades_instead_of_failing(self, tmp_path, caplog):
        spotify = FakeSpotify()

        def forbidden(count=20):
            raise SpotifyError(403, "Insufficient client scope")

        spotify.liked_songs_sample = forbidden
        auralis, _, _ = make_auralis(tmp_path, spotify=spotify)
        context = auralis.build_context()
        assert context["my_liked_songs_sample"] == []
        assert "spotify.login" in caplog.text


class TestPlaylist:
    def test_scout_then_curator_create_the_playlist(self, tmp_path):
        auralis, spotify, advisor = make_auralis(tmp_path)
        outcome = auralis.playlist_generator("upbeat morning")
        assert isinstance(outcome, PlaylistOutcome)
        assert [c["stage"] for c in advisor.calls] == ["scout", "curator"]
        assert spotify.created == ["Drive"]
        assert outcome.name == "Drive" and outcome.reason == "Because."
        assert outcome.research == "Looked for upbeat tracks."
        assert outcome.playlist_url == "https://open.spotify.com/playlist/p1"
        assert [t.uri for t in outcome.tracks] == URIS[:8]
        assert outcome.dry_run is False

    def test_dry_run_creates_and_plays_nothing(self, tmp_path):
        auralis, spotify, _ = make_auralis(tmp_path)
        outcome = auralis.playlist_generator("upbeat", dry_run=True)
        assert outcome.dry_run is True and outcome.playlist_url is None
        assert len(outcome.tracks) == 8
        assert spotify.created == [] and spotify.played == []
        assert outcome.playback == "none"

    def test_the_curator_gets_the_pool_and_the_scouts_notes(self, tmp_path):
        auralis, _, advisor = make_auralis(tmp_path)
        auralis.playlist_generator("upbeat morning")
        curator = advisor.calls[1]
        assert "Looked for upbeat tracks." in curator["user"]
        assert URIS[3] in curator["user"] and "T4 - Band 4" in curator["user"]

    def test_the_scout_has_no_write_stage_and_the_curator_has_no_web(self, tmp_path):
        auralis, _, advisor = make_auralis(tmp_path)
        auralis.playlist_generator("upbeat morning", depth=Depth.DEEP)
        scout, curator = advisor.calls
        assert "WebSearch" in scout["builtin_tools"]
        assert curator["builtin_tools"] == ()
        assert "WebSearch" not in curator["allowed_tools"]

    @pytest.mark.parametrize("depth", list(Depth))
    def test_depth_controls_web_access_budget_and_guidance(self, tmp_path, depth):
        auralis, _, advisor = make_auralis(tmp_path)
        auralis.playlist_generator("upbeat morning", depth=depth)
        scout = advisor.calls[0]
        plan = PLANS[depth]
        assert scout["builtin_tools"] == plan.builtin_tools
        assert scout["budget"] == plan.budget_usd
        assert plan.guidance in scout["system"]
        assert ("WebSearch" in scout["builtin_tools"]) == (depth != Depth.QUICK)

    def test_unverified_and_excluded_candidates_never_reach_the_curator(self, tmp_path):
        auralis, _, advisor = make_auralis(
            tmp_path,
            scout_uris=URIS + ["spotify:track:invented"],
            curator_attempts=(URIS[2:10],),
        )
        auralis.playlist_generator("upbeat", excluded=[("T2", "Band 2")])
        pool = advisor.calls[1]["user"]
        assert "invented" not in pool and "T2 - Band 2" not in pool
        assert "T3 - Band 3" in pool

    def test_a_scout_with_too_few_usable_tracks_is_an_error(self, tmp_path):
        auralis, spotify, advisor = make_auralis(tmp_path, scout_uris=URIS[:3])
        with pytest.raises(AuralisError, match="only 3"):
            auralis.playlist_generator("upbeat")
        assert [c["stage"] for c in advisor.calls] == ["scout"]
        assert spotify.created == []

    def test_the_gate_rejects_an_excluded_song_and_the_curator_recovers(self, tmp_path):
        auralis, spotify, advisor = make_auralis(
            tmp_path, curator_attempts=(URIS[:8], URIS[1:9])
        )
        outcome = auralis.playlist_generator("upbeat", excluded=[("T1", "Band 1")])
        assert advisor.submit_results[0]["ok"] is False
        assert "T1 - Band 1" in advisor.submit_results[0]["violations"][0]
        assert [t.uri for t in outcome.tracks] == URIS[1:9]
        assert spotify.created == ["Drive"]

    def test_familiar_songs_are_limited_by_the_gate(self, tmp_path):
        spotify = FakeSpotify()
        spotify.recently_played = lambda: CATALOGUE[:6]
        auralis, _, advisor = make_auralis(tmp_path, spotify=spotify)
        with pytest.raises(AuralisError):
            auralis.playlist_generator("upbeat")
        assert "at most 4" in advisor.submit_results[0]["violations"][0]

    def test_a_curator_that_never_submits_is_retried_once_then_fails(self, tmp_path):
        auralis, spotify, advisor = make_auralis(tmp_path, curator_attempts=(URIS[:2],))
        with pytest.raises(AuralisError, match="did not produce"):
            auralis.playlist_generator("upbeat")
        assert [c["stage"] for c in advisor.calls] == ["scout", "curator", "curator"]
        assert "previous attempt" in advisor.calls[2]["user"]
        assert spotify.created == []

    def test_the_length_target_sets_the_rules_and_the_prompt(self, tmp_path):
        auralis, _, advisor = make_auralis(tmp_path)
        with pytest.raises(AuralisError, match="need 14"):  # pool of 12 is too small
            auralis.playlist_generator("a 1 hour drive")
        scout = advisor.calls[0]["user"]
        assert "14-22 tracks" in scout and "target about 17" in scout

    def test_each_request_sees_the_request_and_profile(self, tmp_path):
        auralis, _, advisor = make_auralis(tmp_path)
        auralis.playlist_generator("neon city drive")
        scout = advisor.calls[0]
        assert "neon city drive" in scout["user"]
        assert "my_recently_played_songs" in scout["user"]


class TestPlaylistPlayback:
    def test_plays_on_an_active_idle_device(self, tmp_path):
        auralis, spotify, _ = make_auralis(tmp_path)
        outcome = auralis.playlist_generator("upbeat")
        assert outcome.playback == "playing"
        assert spotify.played == [("playlist", "spotify:playlist:p1", None)]

    def test_never_interrupts_what_is_already_playing(self, tmp_path):
        auralis, spotify, _ = make_auralis(tmp_path, spotify=FakeSpotify(playing=True))
        assert auralis.playlist_generator("upbeat").playback == "none"
        assert spotify.played == []

    def test_no_active_device_just_makes_the_playlist(self, tmp_path):
        auralis, spotify, _ = make_auralis(
            tmp_path, spotify=FakeSpotify(has_device=False)
        )
        outcome = auralis.playlist_generator("upbeat")
        assert outcome.playback == "none" and spotify.created == ["Drive"]

    def test_a_chosen_device_plays_even_when_nothing_is_active(self, tmp_path):
        auralis, spotify, _ = make_auralis(
            tmp_path, spotify=FakeSpotify(has_device=False, playing=True)
        )
        outcome = auralis.playlist_generator("upbeat", device_id="kitchen")
        assert outcome.playback == "playing"
        assert spotify.played == [("playlist", "spotify:playlist:p1", "kitchen")]


class TestSong:
    def test_picks_and_plays_a_song_with_no_web_by_default(self, tmp_path):
        auralis, spotify, advisor = make_auralis(tmp_path)
        outcome = auralis.song_of_the_moment_suggestion()
        assert isinstance(outcome, SongOutcome)
        assert outcome.track.uri == URIS[0] and outcome.reason == "Because."
        assert outcome.playback == "playing"
        call = advisor.calls[0]
        assert call["stage"] == "song" and call["builtin_tools"] == ()
        assert spotify.played == [("track", URIS[0], None)]

    def test_queues_when_something_is_already_playing(self, tmp_path):
        auralis, spotify, _ = make_auralis(tmp_path, spotify=FakeSpotify(playing=True))
        outcome = auralis.song_of_the_moment_suggestion()
        assert outcome.playback == "queued" and spotify.queued == [URIS[0]]

    def test_no_device_still_returns_the_song(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path, spotify=FakeSpotify(has_device=False))
        outcome = auralis.song_of_the_moment_suggestion()
        assert outcome.playback == "none" and outcome.track.title == "T1"

    def test_dry_run_plays_nothing(self, tmp_path):
        auralis, spotify, _ = make_auralis(tmp_path)
        assert auralis.song_of_the_moment_suggestion(dry_run=True).playback == "none"
        assert spotify.played == [] and spotify.queued == []

    def test_the_gate_forces_a_discovery_and_the_picker_recovers(self, tmp_path):
        spotify = FakeSpotify()
        spotify.recently_played = lambda: [CATALOGUE[0]]
        auralis, _, advisor = make_auralis(
            tmp_path, spotify=spotify, song_attempts=(URIS[0:1], URIS[1:2])
        )
        outcome = auralis.song_of_the_moment_suggestion()
        assert "already in" in advisor.submit_results[0]["violations"][0]
        assert outcome.track.uri == URIS[1]

    def test_excluded_songs_are_refused(self, tmp_path):
        auralis, _, advisor = make_auralis(
            tmp_path, song_attempts=(URIS[0:1], URIS[1:2])
        )
        outcome = auralis.song_of_the_moment_suggestion(excluded=[("T1", "Band 1")])
        assert advisor.submit_results[0]["ok"] is False
        assert outcome.track.uri == URIS[1]

    def test_a_picker_that_never_chooses_fails(self, tmp_path):
        auralis, _, advisor = make_auralis(
            tmp_path, song_attempts=(["spotify:track:nope"],)
        )
        with pytest.raises(AuralisError, match="No song"):
            auralis.song_of_the_moment_suggestion()
        assert len(advisor.calls) == 2

    def test_depth_deep_enables_web_for_the_song_too(self, tmp_path):
        auralis, _, advisor = make_auralis(tmp_path)
        auralis.song_of_the_moment_suggestion(depth=Depth.DEEP)
        assert "WebSearch" in advisor.calls[0]["builtin_tools"]


class TestWorkspace:
    def test_a_successful_run_leaves_nothing_behind(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path)
        auralis.playlist_generator("upbeat")
        assert list((tmp_path / "runs").iterdir()) == []

    def test_a_failed_run_is_kept_for_debugging(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path, scout_uris=URIS[:2])
        with pytest.raises(AuralisError):
            auralis.playlist_generator("upbeat")
        [kept] = list((tmp_path / "runs").iterdir())
        assert (kept / "rules.json").exists()

    def test_only_the_newest_failures_are_kept(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path, scout_uris=URIS[:2])
        for _ in range(14):
            with pytest.raises(AuralisError):
                auralis.playlist_generator("upbeat")
        assert len(list((tmp_path / "runs").iterdir())) == 10


class TestSongCountEstimate:
    @pytest.mark.parametrize(
        "prompt, expected",
        [
            ("a 2 hour road trip", 34),
            ("one hour workout", 17),
            ("30 minutes of focus", 9),
            ("a quick pick-me-up", 8),
            ("saturday party", 25),
            ("rainy mood", None),
        ],
    )
    def test_estimate(self, tmp_path, prompt, expected):
        auralis = make_auralis(tmp_path)[0]
        assert auralis._estimate_target_song_count(prompt) == expected
