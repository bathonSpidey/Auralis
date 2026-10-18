import pytest

from spotify.client import SpotifyClient
from spotify.library import NoDeviceError, Spotify
from tests.spotify_fakes import FakeResponse, FakeSession, StubAuth, track


def make_spotify(routes):
    session = FakeSession(routes)
    client = SpotifyClient(StubAuth(), session=session, sleep=lambda s: None)
    return Spotify(client), session


def ok(body):
    return FakeResponse(200, body)


def search_results(*tracks):
    return ok({"tracks": {"items": list(tracks), "next": None}})


class TestListeningHistory:
    def test_recently_played_dedupes_and_skips_unplayable_items(self):
        items = [
            {"track": track("1", "One")},
            {"track": track("1", "One")},
            {"track": None},
            {"track": {**track("2", "Episode"), "type": "episode"}},
            {"track": track("3", "Three")},
        ]
        spotify, session = make_spotify(
            {("GET", "/me/player/recently-played"): ok({"items": items})}
        )
        assert [s.name for s in spotify.recently_played()] == ["One", "Three"]
        assert session.calls[0]["params"] == {"limit": 50}

    def test_top_tracks(self):
        spotify, session = make_spotify(
            {
                ("GET", "/me/top/tracks"): ok(
                    {"items": [track("1", "One")], "next": None}
                )
            }
        )
        assert [s.name for s in spotify.top_tracks(limit=10)] == ["One"]
        assert session.calls[0]["params"]["time_range"] == "medium_term"

    def test_playlist_songs_reads_the_renamed_item_field(self):
        items = [
            {"item": track("1", "New")},
            {"track": track("2", "Old")},
            {"item": None},
        ]
        spotify, session = make_spotify(
            {("GET", "/playlists/p1/items"): ok({"items": items, "next": None})}
        )
        assert [s.name for s in spotify.playlist_songs("p1")] == ["New", "Old"]

    def test_user_playlists(self):
        playlist = {
            "id": "p1",
            "href": "h",
            "uri": "spotify:playlist:p1",
            "name": "Mine",
        }
        spotify, _ = make_spotify(
            {("GET", "/me/playlists"): ok({"items": [playlist], "next": None})}
        )
        [mine] = spotify.user_playlists()
        assert mine.url == "https://open.spotify.com/playlist/p1"


class TestArtistGenres:
    def test_fetches_each_artist_once_and_caches(self):
        spotify, session = make_spotify(
            {
                ("GET", "/artists/a1"): ok({"genres": ["indie"]}),
                ("GET", "/artists/a2"): ok({"genres": ["pop", "dance"]}),
            }
        )
        uris = ["spotify:artist:a1", "spotify:artist:a2"]
        first = spotify.artist_genres(uris)
        second = spotify.artist_genres(uris)
        assert first == second == {uris[0]: ["indie"], uris[1]: ["pop", "dance"]}
        assert session.paths() == ["/artists/a1", "/artists/a2"]

    def test_one_failing_artist_does_not_lose_the_rest(self):
        spotify, _ = make_spotify({("GET", "/artists/a2"): ok({"genres": ["pop"]})})
        genres = spotify.artist_genres(["spotify:artist:a1", "spotify:artist:a2"])
        assert genres == {"spotify:artist:a2": ["pop"]}


class TestSearch:
    def test_pages_of_ten_to_respect_the_search_cap(self):
        def respond(params, _):
            count = min(params["limit"], 10)
            items = [track(str(params["offset"] + i), "T") for i in range(count)]
            return ok({"tracks": {"items": items, "next": "more"}})

        spotify, session = make_spotify({("GET", "/search"): respond})
        assert len(spotify.search_tracks("q", limit=25)) == 25
        assert [c["params"]["limit"] for c in session.calls] == [10, 10, 5]


class TestFindTrack:
    def test_prefers_the_exact_title_from_the_right_artist(self):
        results = search_results(
            track("1", "Opalite - Live", "Taylor Swift"),
            track("2", "Opalite", "Taylor Swift"),
        )
        spotify, _ = make_spotify({("GET", "/search"): results})
        assert spotify.find_track("Opalite", "Taylor Swift").id == "2"

    def test_artist_names_match_across_accents_and_collaborations(self):
        results = search_results(track("1", "Despacito", "Luis Fonsi"))
        spotify, _ = make_spotify({("GET", "/search"): results})
        assert spotify.find_track("Despacito", "Luis Fonsí feat. Daddy Yankee")

    def test_a_different_artists_song_is_not_a_match(self):
        results = search_results(track("1", "Opalite", "Cover Band"))
        spotify, session = make_spotify({("GET", "/search"): results})
        assert spotify.find_track("Opalite", "Taylor Swift") is None
        assert len(session.calls) == 2  # structured query, then the plain fallback

    def test_falls_back_to_a_plain_query(self):
        answers = [search_results(), search_results(track("1", "Song", "Band"))]
        spotify, session = make_spotify({("GET", "/search"): answers})
        assert spotify.find_track("Song", "Band").id == "1"
        assert session.calls[0]["params"]["q"] == 'track:"Song" artist:"Band"'
        assert session.calls[1]["params"]["q"] == "Song Band"


class TestPlaylists:
    playlist = {"id": "p1", "href": "h", "uri": "spotify:playlist:p1", "name": "Drive"}

    def routes(self, extra=None):
        return {
            ("POST", "/me/playlists"): ok(self.playlist),
            ("POST", "/playlists/p1/items"): ok({"snapshot_id": "s"}),
            **(extra or {}),
        }

    def test_create_playlist_is_private_and_truncates_the_description(self):
        spotify, session = make_spotify(self.routes())
        spotify.create_playlist("Drive", "x" * 500)
        body = session.calls[0]["json"]
        assert body["public"] is False
        assert len(body["description"]) == 300

    def test_adds_in_batches_of_100(self):
        spotify, session = make_spotify(self.routes())
        spotify.add_to_playlist("p1", [f"spotify:track:{i}" for i in range(150)])
        sizes = [len(c["json"]["uris"]) for c in session.calls]
        assert sizes == [100, 50]

    def test_build_playlist_reports_misses_and_dedupes(self):
        catalogue = {"Alpha": track("1", "Alpha", "A"), "Dup": track("2", "Dup", "B")}

        def search(params, _):
            hits = [t for title, t in catalogue.items() if title in params["q"]]
            return search_results(*hits)

        spotify, session = make_spotify(self.routes({("GET", "/search"): search}))
        build = spotify.build_playlist(
            "Drive", [("Alpha", "A"), ("Ghost", "Nobody"), ("Dup", "B"), ("Dup", "B")]
        )
        assert [s.name for s in build.added] == ["Alpha", "Dup"]
        assert build.not_found == ["Ghost - Nobody"]
        assert build.playlist.id == "p1"
        [add] = [c for c in session.calls if c["path"] == "/playlists/p1/items"]
        assert add["json"]["uris"] == ["spotify:track:1", "spotify:track:2"]

    def test_nothing_found_creates_no_playlist(self):
        spotify, session = make_spotify(
            self.routes({("GET", "/search"): search_results()})
        )
        with pytest.raises(LookupError):
            spotify.build_playlist("Drive", [("Ghost", "Nobody")])
        assert "/me/playlists" not in session.paths("POST")


class TestLikedSongs:
    @staticmethod
    def liked_routes(total):
        def respond(params, _):
            start = params["offset"]
            count = max(0, min(params["limit"], total - start))
            items = [
                {"track": track(str(start + i), f"Liked {start + i}")}
                for i in range(count)
            ]
            more = "next" if start + count < total else None
            return ok({"total": total, "items": items, "next": more})

        return {("GET", "/me/tracks"): respond}

    def test_empty_library(self):
        spotify, _ = make_spotify(self.liked_routes(0))
        assert spotify.liked_songs() == []

    def test_reads_every_liked_song_across_pages(self):
        spotify, session = make_spotify(self.liked_routes(213))
        songs = spotify.liked_songs()
        assert len(songs) == 213 and len({s.uri for s in songs}) == 213
        assert len(session.calls) == 5

    def test_a_huge_library_is_capped(self):
        spotify, session = make_spotify(self.liked_routes(5000))
        assert len(spotify.liked_songs(limit=120)) == 120
        assert len(session.calls) == 3

    def test_local_files_and_unplayable_items_are_skipped(self):
        items = [{"track": track("1", "One")}, {"track": None}]
        spotify, _ = make_spotify(
            {("GET", "/me/tracks"): ok({"items": items, "next": None})}
        )
        assert [s.name for s in spotify.liked_songs()] == ["One"]


class TestPlayback:
    @staticmethod
    def device(device_id, kind, active=False):
        return {"id": device_id, "is_active": active, "name": device_id, "type": kind}

    def devices(self, *devices):
        return {("GET", "/me/player/devices"): ok({"devices": list(devices)})}

    def test_uses_the_active_device(self):
        routes = {
            **self.devices(
                self.device("pc", "Computer"), self.device("tv", "TV", True)
            ),
            ("PUT", "/me/player/play"): FakeResponse(204),
        }
        spotify, session = make_spotify(routes)
        spotify.play_track("spotify:track:1")
        play = session.calls[-1]
        assert play["params"] == {"device_id": "tv"}
        assert play["json"] == {"uris": ["spotify:track:1"]}

    def test_a_chosen_device_is_used_without_looking_for_one(self):
        routes = {("PUT", "/me/player/play"): FakeResponse(204)}
        spotify, session = make_spotify(routes)
        spotify.play_playlist("spotify:playlist:p1", device_id="kitchen")
        assert session.paths() == ["/me/player/play"]
        assert session.calls[0]["params"] == {"device_id": "kitchen"}
        assert session.calls[0]["json"] == {"context_uri": "spotify:playlist:p1"}

    def test_nothing_active_and_nothing_chosen_means_no_playback(self):
        spotify, session = make_spotify(
            self.devices(
                self.device("kitchen", "Speaker"),
                self.device("pc", "Computer"),
                self.device("phone", "Smartphone"),
            )
        )
        with pytest.raises(NoDeviceError):
            spotify.play_track("spotify:track:1")
        assert session.paths("PUT") == []

    def test_no_devices_at_all(self):
        spotify, _ = make_spotify(self.devices())
        with pytest.raises(NoDeviceError):
            spotify.play_track("spotify:track:1")

    def test_active_device(self):
        spotify, _ = make_spotify(
            self.devices(self.device("a", "TV"), self.device("b", "Speaker", True))
        )
        assert spotify.active_device().id == "b"

    def test_device_without_volume_is_accepted(self):
        spotify, _ = make_spotify(self.devices(self.device("tv", "TV")))
        assert spotify.devices()[0].volume_percent is None

    def test_is_playing(self):
        spotify, _ = make_spotify(
            {("GET", "/me/player/currently-playing"): ok({"is_playing": True})}
        )
        assert spotify.is_playing() is True

    def test_nothing_playing_returns_204(self):
        spotify, _ = make_spotify(
            {("GET", "/me/player/currently-playing"): FakeResponse(204)}
        )
        assert spotify.is_playing() is False

    def test_queue_track(self):
        spotify, session = make_spotify(
            {("POST", "/me/player/queue"): FakeResponse(204)}
        )
        spotify.queue_track("spotify:track:1")
        assert session.calls[0]["params"] == {"uri": "spotify:track:1"}

    def test_delete_playlist_uses_the_library_endpoint(self):
        spotify, session = make_spotify(
            {("DELETE", "/me/library"): FakeResponse(200, {})}
        )
        spotify.delete_playlist("spotify:playlist:p1")
        assert session.calls[0]["params"] == {"uris": "spotify:playlist:p1"}
