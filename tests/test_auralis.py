import json
from pathlib import Path

import pytest

from agent.auralis import Auralis, AuralisError
from agent.depth import PLANS, Depth
from agent.schemas import PlaylistOutcome, SongOutcome, TrackInfo
from auralis_mcp.session import RunSession
from models.album import Album
from models.artist import Artist
from models.playlist import Playlist
from models.song import Song
from spotify.client import SpotifyError
from store.history import DISLIKE, LIKE, Store
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
    def active_device(self):
        return object() if self.has_device else None

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

    def liked_songs(self, limit=1000):
        return [make_song(f"Liked{n}", f"Liked Artist {n}") for n in range(30)]

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


def make_auralis(tmp_path, spotify=None, store=None, **advisor_args):
    spotify = spotify or FakeSpotify()
    advisor = ScriptedAdvisor(spotify, **advisor_args)
    auralis = Auralis(spotify, advisor, runs_dir=tmp_path / "runs", store=store)
    return auralis, spotify, advisor


def eight_without(*numbers):
    """Eight track URIs, skipping T<n> for each given n."""
    skipped = {URIS[n - 1] for n in numbers}
    return [uri for uri in URIS if uri not in skipped][:8]


def make_store(tmp_path):
    return Store(tmp_path / "auralis.db")


def past_song(store, n):
    """Record song n as a past creation and return its history id."""
    t = TrackInfo(uri=URIS[n - 1], title=f"T{n}", artist=f"Band {n}")
    return store.record_song(
        SongOutcome(track=t, reason="r", playback="none", dry_run=False), "quick", "web"
    )


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
        sample = context["my_liked_songs_sample"]
        assert len(sample) == 20 and all(s["name"].startswith("Liked") for s in sample)
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


class FakeWeather:
    def __init__(self, hour, month=10):
        from datetime import datetime

        from models.location import Location
        from models.location_temperature import Temperature
        from src.weather_api_connector import Conditions

        self.found = Conditions(
            location=Location(name="Rastatt", country="DE", lat=48.8, lon=8.2),
            weather=Temperature(
                temp=11.7,
                feels_like=10.4,
                pressure=1030,
                humidity=59,
                dew_point=3.9,
                uvi=0.6,
                clouds=0,
                visibility=10000,
                wind_speed=2.2,
                wind_deg=8,
                weather=[{"main": "Clear", "description": "clear sky"}],
            ),
            now=datetime(2026, month, 19, hour, 5),
        )

    def conditions(self, city=None):
        return self.found


class TestWeatherAndTime:
    def test_weather_place_and_local_time_reach_the_prompt_context(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path)
        auralis.weather = FakeWeather(hour=22, month=12)
        context = auralis.build_context()
        assert context["my_current_weather"]["temperature"] == 11.7
        assert context["my_current_weather"]["weather"]["description"] == "clear sky"
        assert context["my_current_location"] == {"country": "DE", "city": "Rastatt"}
        assert context["time_of_day"] == "night"
        assert context["season"] == "winter"

    def test_without_weather_time_still_comes_from_the_clock(self, tmp_path):
        context = make_auralis(tmp_path)[0].build_context()
        assert context["time_of_day"] in {
            "morning",
            "afternoon",
            "evening",
            "night",
            "late night",
        }
        assert context["my_current_location"] is None

    def test_failed_weather_lookup_is_not_fatal(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path)
        auralis.weather = type("Down", (), {"conditions": lambda self, c=None: None})()
        assert auralis.build_context()["my_current_weather"] is None


class TestCurrentDevice:
    def test_current_means_the_playing_or_last_used_device(self, tmp_path):
        spotify = FakeSpotify()
        spotify.current_device = lambda: type("D", (), {"id": "last-speaker"})()
        auralis, _, _ = make_auralis(tmp_path, spotify=spotify)
        assert auralis._start_playlist("spotify:playlist:p1", "current") is True
        assert spotify.played == [("playlist", "spotify:playlist:p1", "last-speaker")]

    def test_no_current_device_means_nothing_plays(self, tmp_path):
        spotify = FakeSpotify()
        spotify.current_device = lambda: None
        auralis, _, _ = make_auralis(tmp_path, spotify=spotify)
        assert auralis._start_playlist("spotify:playlist:p1", "current") is False
        assert auralis._play_song({"uri": "spotify:track:x"}, "current") == "none"
        assert spotify.played == []


class TestLikedSongsAreOptional:
    def test_a_missing_scope_degrades_instead_of_failing(self, tmp_path, caplog):
        spotify = FakeSpotify()

        def forbidden(limit=1000):
            raise SpotifyError(403, "Insufficient client scope")

        spotify.liked_songs = forbidden
        auralis, _, _ = make_auralis(tmp_path, spotify=spotify)
        context = auralis.build_context()
        assert context["my_liked_songs_sample"] == []
        assert "spotify.login" in caplog.text


class TestLikedSongsAreKnown:
    def test_every_liked_song_not_just_the_sample_counts_as_familiar(self, tmp_path):
        spotify = FakeSpotify()
        liked = [make_song(f"T{n}", f"Band {n}") for n in range(1, 13)]
        spotify.liked_songs = lambda limit=1000: liked
        auralis, _, advisor = make_auralis(tmp_path, spotify=spotify)
        with pytest.raises(AuralisError):
            auralis.playlist_generator("upbeat")
        assert "at most 4" in advisor.submit_results[0]["violations"][0]


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
    def test_picks_a_song_with_no_web_by_default_and_queues_it(self, tmp_path):
        auralis, spotify, advisor = make_auralis(tmp_path)
        outcome = auralis.song_of_the_moment_suggestion()
        assert isinstance(outcome, SongOutcome)
        assert outcome.track.uri == URIS[0] and outcome.reason == "Because."
        call = advisor.calls[0]
        assert call["stage"] == "song" and call["builtin_tools"] == ()
        # Spotify is open: queued, never started on its own
        assert outcome.playback == "queued"
        assert spotify.queued == [URIS[0]] and spotify.played == []

    def test_queues_even_while_something_is_playing(self, tmp_path):
        auralis, spotify, _ = make_auralis(tmp_path, spotify=FakeSpotify(playing=True))
        outcome = auralis.song_of_the_moment_suggestion()
        assert outcome.playback == "queued" and spotify.queued == [URIS[0]]

    def test_a_chosen_device_plays_the_song(self, tmp_path):
        auralis, spotify, _ = make_auralis(tmp_path)
        outcome = auralis.song_of_the_moment_suggestion(device_id="kitchen")
        assert outcome.playback == "playing"
        assert spotify.played == [("track", URIS[0], "kitchen")]
        assert spotify.queued == []

    def test_no_device_still_returns_the_song(self, tmp_path):
        spotify = FakeSpotify(has_device=False)
        auralis, _, _ = make_auralis(tmp_path, spotify=spotify)
        outcome = auralis.song_of_the_moment_suggestion()
        assert outcome.playback == "none" and outcome.track.title == "T1"
        assert spotify.queued == [] and spotify.played == []

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


class TestHistoryAndFeedback:
    def test_real_creations_are_recorded_and_dry_runs_are_not(self, tmp_path):
        store = make_store(tmp_path)
        auralis, _, _ = make_auralis(tmp_path, store=store)
        auralis.playlist_generator("upbeat", dry_run=True)
        auralis.song_of_the_moment_suggestion(dry_run=True)
        assert store.history() == []
        playlist = auralis.playlist_generator(
            "upbeat", depth=Depth.DEEP, source="discord"
        )
        [entry] = store.history()
        assert playlist.id == entry["id"]
        assert entry["prompt"] == "upbeat" and entry["depth"] == "deep"
        assert entry["source"] == "discord" and len(entry["tracks"]) == 8

    def test_a_song_creation_is_recorded_too(self, tmp_path):
        store = make_store(tmp_path)
        auralis, _, _ = make_auralis(tmp_path, store=store)
        song = auralis.song_of_the_moment_suggestion()
        assert store.history()[0]["id"] == song.id

    def test_the_next_creation_cannot_repeat_the_last_one(self, tmp_path):
        store = make_store(tmp_path)
        past_song(store, 1)
        auralis, _, advisor = make_auralis(
            tmp_path, store=store, curator_attempts=(URIS[:8], URIS[1:9])
        )
        playlist = auralis.playlist_generator("upbeat")
        assert advisor.submit_results[0]["ok"] is False
        assert "T1 - Band 1" in advisor.submit_results[0]["violations"][0]
        assert [t.uri for t in playlist.tracks] == URIS[1:9]

    def test_the_scout_pool_also_drops_the_last_creations_songs(self, tmp_path):
        store = make_store(tmp_path)
        past_song(store, 1)
        auralis, _, advisor = make_auralis(
            tmp_path, store=store, curator_attempts=(URIS[1:9],)
        )
        auralis.playlist_generator("upbeat")
        assert "T1 - Band 1" not in advisor.calls[1]["user"]

    def test_after_two_more_creations_a_song_may_come_back(self, tmp_path):
        store = make_store(tmp_path)
        for n in (1, 2, 3):
            past_song(store, n)
        auralis, _, advisor = make_auralis(
            tmp_path, store=store, curator_attempts=(eight_without(2, 3),)
        )
        playlist = auralis.playlist_generator("upbeat")  # contains T1, long ago
        assert advisor.submit_results[0]["ok"] is True
        assert URIS[0] in [t.uri for t in playlist.tracks]

    def test_a_dislike_steers_the_prompts_but_does_not_forbid_the_song(self, tmp_path):
        store = make_store(tmp_path)
        first = past_song(store, 1)
        for n in (2, 3, 4):
            past_song(store, n)
        store.rate_track(first, URIS[0], DISLIKE)
        auralis, _, advisor = make_auralis(
            tmp_path, store=store, curator_attempts=(eight_without(3, 4),)
        )
        playlist = auralis.playlist_generator("upbeat")
        assert URIS[0] in [t.uri for t in playlist.tracks]
        assert advisor.submit_results[0]["ok"] is True  # not a hard rule
        for call in advisor.calls:
            assert "Disliked" in call["user"] and "- T1 - Band 1" in call["user"]

    def test_likes_reach_every_prompt_and_neutral_songs_add_nothing(self, tmp_path):
        store = make_store(tmp_path)
        liked = past_song(store, 5)
        past_song(store, 6)  # never rated: neutral
        store.rate_track(liked, URIS[4], LIKE)
        auralis, _, advisor = make_auralis(
            tmp_path,
            store=store,
            curator_attempts=(eight_without(5, 6),),
            song_attempts=(URIS[10:11],),
        )
        auralis.playlist_generator("upbeat")
        auralis.song_of_the_moment_suggestion()
        assert len(advisor.calls) == 3
        for call in advisor.calls:
            assert "Liked, so lean toward" in call["user"]
            assert "- T5 - Band 5" in call["user"]
            assert "- T6 - Band 6" not in call["user"]

    def test_no_feedback_means_no_feedback_section(self, tmp_path):
        store = make_store(tmp_path)
        auralis, _, advisor = make_auralis(tmp_path, store=store)
        auralis.playlist_generator("upbeat")
        assert all("LISTENER FEEDBACK" not in c["user"] for c in advisor.calls)

    def test_changing_your_mind_changes_the_next_prompt(self, tmp_path):
        store = make_store(tmp_path)
        sid = past_song(store, 5)
        store.rate_track(sid, URIS[4], DISLIKE)
        store.rate_track(sid, URIS[4], LIKE)
        auralis, _, advisor = make_auralis(
            tmp_path, store=store, curator_attempts=(eight_without(5),)
        )
        auralis.playlist_generator("upbeat")
        user = advisor.calls[0]["user"]
        assert "Liked, so lean toward this kind of sound:\n- T5 - Band 5" in user
        assert (
            "Disliked, so steer away from songs like these and avoid these exact songs unless the request names them:\n- none"
            in user
        )


class TestProgress:
    def test_a_playlist_reports_its_stages_in_order(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path)
        stages = []
        auralis.playlist_generator("upbeat", progress=stages.append)
        assert stages == ["taste", "scout", "curate", "finish"]

    def test_a_song_reports_its_stages_in_order(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path)
        stages = []
        auralis.song_of_the_moment_suggestion(progress=stages.append)
        assert stages == ["taste", "pick", "finish"]

    def test_progress_is_optional(self, tmp_path):
        make_auralis(tmp_path)[0].playlist_generator("upbeat")


class TestCommittingAPreview:
    def preview(self, tmp_path, **kwargs):
        store = make_store(tmp_path)
        auralis, spotify, advisor = make_auralis(tmp_path, store=store, **kwargs)
        return (
            auralis,
            spotify,
            advisor,
            store,
            auralis.playlist_generator("upbeat", dry_run=True),
        )

    def test_creates_exactly_the_preview_with_no_new_research(self, tmp_path):
        auralis, spotify, advisor, store, preview = self.preview(tmp_path)
        calls = len(advisor.calls)
        result = auralis.commit_playlist(preview, "upbeat", Depth.DEEP)
        assert len(advisor.calls) == calls  # Claude was not asked again
        assert spotify.created == ["Drive"]
        assert result.dry_run is False and result.playlist_url.endswith("/p1")
        assert [t.uri for t in result.tracks] == [t.uri for t in preview.tracks]
        [entry] = store.history()
        assert entry["id"] == result.id and entry["prompt"] == "upbeat"
        assert entry["depth"] == "deep"

    def test_plays_on_the_chosen_device(self, tmp_path):
        auralis, spotify, _, _, preview = self.preview(tmp_path)
        result = auralis.commit_playlist(preview, "upbeat", device_id="kitchen")
        assert result.playback == "playing"
        assert spotify.played == [("playlist", "spotify:playlist:p1", "kitchen")]

    def test_no_active_device_just_creates_it(self, tmp_path):
        auralis, _, _, _, preview = self.preview(
            tmp_path, spotify=FakeSpotify(has_device=False)
        )
        assert auralis.commit_playlist(preview, "upbeat").playback == "none"

    def test_a_failed_add_rolls_the_playlist_back_and_records_nothing(self, tmp_path):
        auralis, spotify, _, store, preview = self.preview(tmp_path)

        def fail(playlist_id, uris):
            raise RuntimeError("Spotify went away")

        spotify.add_to_playlist = fail
        with pytest.raises(RuntimeError, match="went away"):
            auralis.commit_playlist(preview, "upbeat")
        assert spotify.deleted == ["spotify:playlist:p1"]
        assert store.history() == []

    def test_a_playlist_that_already_exists_cannot_be_committed_again(self, tmp_path):
        store = make_store(tmp_path)
        auralis, spotify, _ = make_auralis(tmp_path, store=store)
        real = auralis.playlist_generator("upbeat")
        with pytest.raises(AuralisError, match="already created"):
            auralis.commit_playlist(real, "upbeat")
        assert spotify.created == ["Drive"]  # only the original

    def test_a_previewed_song_is_played_and_recorded_on_commit(self, tmp_path):
        store = make_store(tmp_path)
        auralis, spotify, advisor = make_auralis(tmp_path, store=store)
        preview = auralis.song_of_the_moment_suggestion(dry_run=True)
        calls = len(advisor.calls)
        result = auralis.commit_song(preview, Depth.QUICK, device_id="kitchen")
        assert len(advisor.calls) == calls
        assert result.dry_run is False and result.playback == "playing"
        assert spotify.played == [("track", URIS[0], "kitchen")]
        assert store.history()[0]["id"] == result.id

    def test_a_chosen_song_cannot_be_committed_again(self, tmp_path):
        auralis, _, _ = make_auralis(tmp_path)
        real = auralis.song_of_the_moment_suggestion()
        with pytest.raises(AuralisError, match="already"):
            auralis.commit_song(real)
