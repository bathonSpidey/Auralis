import asyncio
import json

from auralis_mcp.server import create_server
from auralis_mcp.session import RunRules, RunSession, read_outcome, write_rules
from models.album import Album
from models.artist import Artist
from models.playlist import Playlist
from models.song import Song


def song(n, year="2024-05-01"):
    return Song(
        id=str(n),
        uri=f"spotify:track:{n}",
        name=f"Song {n}",
        artists=[Artist(name=f"Artist {n}", uri=f"spotify:artist:{n}")],
        album=Album(name=f"Album {n}", release_date=year),
    )


class FakeSpotify:
    def __init__(self):
        self.created = []

    def search_tracks(self, query, limit=10):
        return [song(n) for n in range(1, min(limit, 4) + 1)]

    def top_tracks(self, limit=20, time_range="medium_term"):
        return [song(7)]

    def recently_played(self):
        return [song(8)]

    def user_playlists(self):
        return [Playlist(id="p9", href="h", uri="spotify:playlist:p9", name="Mine")]

    def playlist_songs(self, playlist_id, limit=200):
        return [song(9)]

    def artist_genres(self, uris):
        return {uri: ["indie"] for uri in uris}

    def create_playlist(self, name, description=""):
        self.created.append(name)
        return Playlist(id="p1", href="h", uri="spotify:playlist:p1", name=name)

    def add_to_playlist(self, playlist_id, uris):
        pass


def make_server(tmp_path, **rules):
    spotify = FakeSpotify()
    write_rules(tmp_path, RunRules(min_songs=2, max_songs=5, **rules))
    session = RunSession(spotify, tmp_path)
    return create_server(spotify, session), spotify


def call(server, tool, **arguments):
    result = asyncio.run(server.call_tool(tool, arguments))
    structured = result.structured_content
    if structured and set(structured) == {"result"}:
        return structured["result"]  # list results are wrapped
    return json.loads(result.content[0].text)


def test_exposes_the_expected_tools(tmp_path):
    server, _ = make_server(tmp_path)
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == {
        "search_tracks",
        "my_top_tracks",
        "my_recent_tracks",
        "my_playlists",
        "playlist_tracks",
        "artist_info",
        "playlist_rules",
        "submit_playlist",
    }


def test_claude_has_no_tool_that_can_delete_or_edit_playlists(tmp_path):
    server, _ = make_server(tmp_path)
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert not {n for n in names if "delete" in n or "remove" in n or "play_" in n}


def test_search_describes_tracks_with_year(tmp_path):
    server, _ = make_server(tmp_path)
    first = call(server, "search_tracks", query="anything", limit=2)[0]
    assert first == {
        "uri": "spotify:track:1",
        "title": "Song 1",
        "artist": "Artist 1",
        "album": "Album 1",
        "year": "2024",
    }


def test_lookup_results_become_submittable_and_nothing_else_does(tmp_path):
    server, spotify = make_server(tmp_path)
    call(server, "search_tracks", query="q", limit=3)
    bad = call(
        server,
        "submit_playlist",
        name="Mix",
        description="d",
        uris=["spotify:track:1", "spotify:track:77"],
    )
    assert bad["ok"] is False and spotify.created == []
    good = call(
        server,
        "submit_playlist",
        name="Mix",
        description="d",
        uris=["spotify:track:1", "spotify:track:2"],
    )
    assert good["ok"] is True
    assert read_outcome(tmp_path)["name"] == "Mix"


def test_the_listeners_own_tracks_are_verified_too(tmp_path):
    server, _ = make_server(tmp_path)
    call(server, "my_top_tracks")
    call(server, "my_recent_tracks")
    call(server, "playlist_tracks", playlist_id="p9")
    result = call(
        server,
        "submit_playlist",
        name="Mix",
        description="",
        uris=["spotify:track:7", "spotify:track:8", "spotify:track:9"],
    )
    assert result["ok"] is True


def test_rules_are_visible_to_claude(tmp_path):
    server, _ = make_server(tmp_path)
    rules = call(server, "playlist_rules")
    assert rules["min_songs"] == 2 and rules["max_per_artist"] == 2


def test_artist_info(tmp_path):
    server, _ = make_server(tmp_path)
    assert call(server, "artist_info", artist_uri="spotify:artist:1") == {
        "genres": ["indie"]
    }
