import json

import pytest

from agent.auralis import Auralis
from agent.schemas import PlaylistSuggestion, SongSuggestion
from models.artist import Artist
from models.song import Song


def make_song(name="Track", artist="Artist"):
    return Song(
        id="1",
        uri=f"spotify:track:{name}",
        name=name,
        artists=[Artist(name=artist, uri=f"spotify:artist:{artist}")],
    )


class FakeSpotify:
    def __init__(self, playing=False, matches=None):
        self.playing = playing
        self.matches = [make_song()] if matches is None else matches
        self.played = []
        self.queued = []
        self.playlists = []

    def recently_played(self):
        return [make_song("Recent")]

    def users_top_tracks(self):
        return [make_song("Top")]

    def get_user_playlists(self):
        return []

    def get_artists_genres(self, artist_uris):
        return {uri: ["indie", "pop"] for uri in artist_uris}

    def search_for_song(self, query):
        return self.matches

    def is_currently_playing(self):
        return self.playing

    def play_song(self, uri):
        self.played.append(uri)

    def add_songs_to_queue(self, uri):
        self.queued.append(uri)

    def generate_playlist_from_auralis(self, name, songs):
        self.playlists.append((name, songs))


class FakeAdvisor:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def advise(self, system_prompt, user_prompt, schema):
        self.calls.append((system_prompt, user_prompt, schema))
        return self.answer


SONG_ANSWER = {"song_title": "Opalite", "artist_name": "Taylor Swift", "reason": "r"}
PLAYLIST_ANSWER = {"playlist_name": "Drive", "songs": ["A - B", "C - D"], "reason": "r"}


class TestBuildContext:
    def test_includes_listening_history_and_genres(self):
        auralis = Auralis(FakeSpotify(), FakeAdvisor({}))
        context = auralis.build_context()
        assert context["my_recently_played_songs"][0]["name"] == "Recent"
        assert context["my_top_tracks"][0]["name"] == "Top"
        assert context["my_recent_genre_distribution"] == {"indie": 1, "pop": 1}
        assert context["my_current_weather"] is None

    def test_context_is_json_serialisable(self):
        context = Auralis(FakeSpotify(), FakeAdvisor({})).build_context()
        json.dumps(context)


class TestSongOfTheMoment:
    def test_plays_the_suggestion_when_nothing_is_playing(self):
        spotify = FakeSpotify(playing=False)
        auralis = Auralis(spotify, FakeAdvisor(SONG_ANSWER))
        suggestion = auralis.song_of_the_moment_suggestion()
        assert suggestion == SongSuggestion(**SONG_ANSWER)
        assert spotify.played == ["spotify:track:Track"]
        assert spotify.queued == []

    def test_queues_the_suggestion_when_something_is_playing(self):
        spotify = FakeSpotify(playing=True)
        Auralis(spotify, FakeAdvisor(SONG_ANSWER)).song_of_the_moment_suggestion()
        assert spotify.queued == ["spotify:track:Track"]
        assert spotify.played == []

    def test_already_suggested_reaches_the_prompt(self):
        advisor = FakeAdvisor(SONG_ANSWER)
        Auralis(FakeSpotify(), advisor).song_of_the_moment_suggestion(
            already_suggested=["Old Song - Old Artist"]
        )
        assert "Old Song - Old Artist" in advisor.calls[0][1]

    def test_unknown_song_raises(self):
        auralis = Auralis(FakeSpotify(matches=[]), FakeAdvisor(SONG_ANSWER))
        with pytest.raises(LookupError, match="No Spotify match"):
            auralis.song_of_the_moment_suggestion()

    def test_malformed_answer_raises(self):
        auralis = Auralis(FakeSpotify(), FakeAdvisor({"song_title": "only"}))
        with pytest.raises(ValueError):
            auralis.song_of_the_moment_suggestion()


class TestPlaylistGenerator:
    def test_creates_the_playlist_in_spotify(self):
        spotify = FakeSpotify()
        auralis = Auralis(spotify, FakeAdvisor(PLAYLIST_ANSWER))
        suggestion = auralis.playlist_generator("chill evening")
        assert suggestion == PlaylistSuggestion(**PLAYLIST_ANSWER)
        assert spotify.playlists == [("Drive", ["A - B", "C - D"])]

    def test_prompt_carries_the_request_and_context(self):
        advisor = FakeAdvisor(PLAYLIST_ANSWER)
        Auralis(FakeSpotify(), advisor).playlist_generator("neon city drive")
        _, user_prompt, _ = advisor.calls[0]
        assert "neon city drive" in user_prompt
        assert "my_recently_played_songs" in user_prompt

    def test_stated_duration_sets_a_minimum_song_count(self):
        advisor = FakeAdvisor(PLAYLIST_ANSWER)
        Auralis(FakeSpotify(), advisor).playlist_generator("a 2 hour road trip")
        schema = advisor.calls[0][2]
        assert schema["properties"]["songs"]["minItems"] == 31

    def test_no_minimum_without_a_duration(self):
        advisor = FakeAdvisor(PLAYLIST_ANSWER)
        Auralis(FakeSpotify(), advisor).playlist_generator("rainy mood")
        assert "minItems" not in advisor.calls[0][2]["properties"]["songs"]


class TestSongCountEstimate:
    auralis = Auralis(FakeSpotify(), FakeAdvisor({}))

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
    def test_estimate(self, prompt, expected):
        assert self.auralis._estimate_target_song_count(prompt) == expected
