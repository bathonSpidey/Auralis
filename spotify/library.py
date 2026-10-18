"""High-level Spotify operations returning Auralis models.

Written against the Development Mode API (search capped at 10 per page, no
batch artist lookup, playlist contents under /items). This is the layer the
agent and, later, the MCP server sit on.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from models.device import Device
from models.playlist import Playlist
from models.song_key import normalize
from models.song import Song
from spotify.auth import (
    DEFAULT_REDIRECT_URI,
    SpotifyAuth,
    TokenStore,
)
from spotify.client import SpotifyClient, SpotifyError

_SEARCH_PAGE = 10
_PLAYLIST_ADD_BATCH = 100
_DESCRIPTION_LIMIT = 300


class NoDeviceError(RuntimeError):
    pass


@dataclass
class PlaylistBuild:
    playlist: Playlist
    added: List[Song]
    not_found: List[str]


def _to_song(track: Optional[dict]) -> Optional[Song]:
    if not track or track.get("type", "track") != "track" or not track.get("id"):
        return None
    return Song(**track)


def _dedupe(songs: List[Song]) -> List[Song]:
    seen = set()
    unique = []
    for song in songs:
        if song.uri not in seen:
            seen.add(song.uri)
            unique.append(song)
    return unique


class Spotify:
    def __init__(self, client: SpotifyClient):
        self.client = client
        self._genre_cache: Dict[str, List[str]] = {}

    @classmethod
    def from_env(cls) -> "Spotify":
        client_id = os.getenv("SPOTIFY_CLIENT_ID") or os.getenv("SPOTIPY_CLIENT_ID")
        redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI") or DEFAULT_REDIRECT_URI
        auth = SpotifyAuth(client_id, redirect_uri, TokenStore())
        return cls(SpotifyClient(auth))

    # ── listening history ───────────────────────────────────────────────
    def me(self) -> dict:
        return self.client.get("/me")

    def recently_played(self, limit: int = 50) -> List[Song]:
        body = self.client.get("/me/player/recently-played", {"limit": min(limit, 50)})
        songs = [_to_song(item.get("track")) for item in body.get("items", [])]
        return _dedupe([song for song in songs if song])

    def top_tracks(
        self, limit: int = 20, time_range: str = "medium_term"
    ) -> List[Song]:
        items = self.client.get_all(
            "/me/top/tracks", {"time_range": time_range}, max_items=limit
        )
        return [song for song in map(_to_song, items) if song]

    def user_playlists(self, limit: int = 50) -> List[Playlist]:
        items = self.client.get_all("/me/playlists", max_items=limit)
        return [Playlist(**item) for item in items if item]

    def playlist_songs(self, playlist_id: str, limit: int = 200) -> List[Song]:
        """Only works for playlists the user owns or collaborates on."""
        items = self.client.get_all(f"/playlists/{playlist_id}/items", max_items=limit)
        songs = [_to_song(item.get("item") or item.get("track")) for item in items]
        return [song for song in songs if song]

    def artist_genres(self, artist_uris: Sequence[str]) -> Dict[str, List[str]]:
        """One request per artist (no batch endpoint), cached for the process."""
        genres = {}
        for uri in artist_uris:
            if uri not in self._genre_cache:
                try:
                    artist = self.client.get(f"/artists/{uri.split(':')[-1]}")
                except SpotifyError:
                    continue
                self._genre_cache[uri] = artist.get("genres", [])
            genres[uri] = self._genre_cache[uri]
        return genres

    # ── search ──────────────────────────────────────────────────────────
    def search_tracks(self, query: str, limit: int = 10) -> List[Song]:
        items = self.client.get_all(
            "/search",
            {"q": query, "type": "track"},
            page_size=_SEARCH_PAGE,
            max_items=limit,
            pick=lambda body: body.get("tracks", {}),
        )
        return [song for song in map(_to_song, items) if song]

    def find_track(self, title: str, artist: str) -> Optional[Song]:
        """Best match for a title and artist, or None. Prefers no result over a
        different artist's song."""
        for query in (f'track:"{title}" artist:"{artist}"', f"{title} {artist}"):
            matches = [
                song
                for song in self.search_tracks(query)
                if self._artist_matches(song, artist)
            ]
            if matches:
                wanted = normalize(title)
                for song in matches:
                    if normalize(song.name) == wanted:
                        return song
                return matches[0]
        return None

    @staticmethod
    def _artist_matches(song: Song, artist: str) -> bool:
        wanted = normalize(artist)
        for candidate in song.artists:
            name = normalize(candidate.name)
            if name and (name in wanted or wanted in name):
                return True
        return False

    # ── playlists ───────────────────────────────────────────────────────
    def create_playlist(self, name: str, description: str = "") -> Playlist:
        body = self.client.post(
            "/me/playlists",
            json={
                "name": name,
                "description": description[:_DESCRIPTION_LIMIT],
                "public": False,
            },
        )
        return Playlist(**body)

    def delete_playlist(self, playlist_uri: str) -> None:
        """Removes a playlist from the user's library (Spotify's 'delete')."""
        self.client.request("DELETE", "/me/library", params={"uris": playlist_uri})

    def add_to_playlist(self, playlist_id: str, uris: Sequence[str]) -> None:
        for start in range(0, len(uris), _PLAYLIST_ADD_BATCH):
            self.client.post(
                f"/playlists/{playlist_id}/items",
                json={"uris": list(uris[start : start + _PLAYLIST_ADD_BATCH])},
            )

    def build_playlist(
        self, name: str, songs: Sequence[Tuple[str, str]], description: str = ""
    ) -> PlaylistBuild:
        """Resolve (title, artist) pairs and create the playlist. Songs that
        can't be matched are reported, not guessed."""
        found: List[Song] = []
        not_found: List[str] = []
        for title, artist in songs:
            song = self.find_track(title, artist)
            if song is None:
                not_found.append(f"{title} - {artist}")
            else:
                found.append(song)
        found = _dedupe(found)
        if not found:
            raise LookupError("None of the suggested songs were found on Spotify")
        playlist = self.create_playlist(name, description)
        self.add_to_playlist(playlist.id, [song.uri for song in found])
        return PlaylistBuild(playlist, found, not_found)

    # ── playback ────────────────────────────────────────────────────────
    def devices(self) -> List[Device]:
        body = self.client.get("/me/player/devices")
        return [Device(**device) for device in body.get("devices", [])]

    def is_playing(self) -> bool:
        body = self.client.get("/me/player/currently-playing")
        return bool(body and body.get("is_playing"))

    def play_track(self, uri: str) -> None:
        self.client.put(
            "/me/player/play",
            params={"device_id": self._device_id()},
            json={"uris": [uri]},
        )

    def play_playlist(self, uri: str) -> None:
        self.client.put(
            "/me/player/play",
            params={"device_id": self._device_id()},
            json={"context_uri": uri},
        )

    def queue_track(self, uri: str) -> None:
        self.client.post("/me/player/queue", params={"uri": uri})

    def _device_id(self) -> str:
        """Active device, else a computer/phone, else the device named by
        SPOTIFY_DEVICE_NAME. Never an arbitrary speaker: starting music in
        some other room is worse than not playing."""
        devices = self.devices()
        for device in devices:
            if device.is_active:
                return device.id
        preferred = (os.getenv("SPOTIFY_DEVICE_NAME") or "").strip().lower()
        by_name = [d for d in devices if preferred and d.name.lower() == preferred]
        personal = [d for d in devices if d.type.lower() in ("computer", "smartphone")]
        chosen = (by_name or personal or [None])[0]
        if chosen is None:
            raise NoDeviceError(
                "No active Spotify device; open Spotify somewhere or set "
                "SPOTIFY_DEVICE_NAME"
            )
        return chosen.id
