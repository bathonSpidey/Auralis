"""MCP server exposing Spotify to Claude: read tools plus one gated write.

Started by Claude Code over stdio (see auralis_mcp.config). Everything Claude
learns about tracks passes through here, which is how the gate knows a URI is
real.
"""

import os
from pathlib import Path
from typing import List

import dotenv
from mcp.server import MCPServer

from auralis_mcp.session import RunSession, describe
from spotify.library import Spotify

INSTRUCTIONS = (
    "Spotify tools for building playlists. Every track you may use must come "
    "from a lookup tool; submit_playlist rejects anything else and enforces "
    "the playlist rules, returning violations for you to fix."
)


# Which stage of a run the server is for decides its write capability: the
# scout (the only stage with web access) can write nothing.
STAGE_SCOUT = "scout"
STAGE_CURATOR = "curator"
STAGE_SONG = "song"


def create_server(
    spotify: Spotify, session: RunSession, stage: str = STAGE_SCOUT
) -> MCPServer:
    server = MCPServer("auralis", instructions=INSTRUCTIONS)

    def seen(songs) -> List[dict]:
        session.remember(songs)
        return [describe(song) for song in songs]

    @server.tool()
    def search_tracks(query: str, limit: int = 10) -> List[dict]:
        """Search Spotify for tracks. Supports field filters, e.g.
        `track:"Opalite" artist:"Taylor Swift"`. Returns uri, title, artist,
        album and release year. Use it to verify that a song exists and to get
        the URI you need for submit_playlist."""
        return seen(spotify.search_tracks(query, limit=min(max(limit, 1), 20)))

    @server.tool()
    def my_top_tracks(time_range: str = "medium_term", limit: int = 20) -> List[dict]:
        """The listener's most played tracks. time_range is short_term (about
        4 weeks), medium_term (about 6 months) or long_term (years)."""
        return seen(
            spotify.top_tracks(limit=min(max(limit, 1), 50), time_range=time_range)
        )

    @server.tool()
    def my_recent_tracks() -> List[dict]:
        """The listener's most recently played tracks, newest first."""
        return seen(spotify.recently_played())

    @server.tool()
    def my_playlists() -> List[dict]:
        """The listener's playlists (id, name, url). Their contents show what
        they like; use playlist_tracks to read one."""
        return [
            {"id": p.id, "name": p.name, "url": p.url} for p in spotify.user_playlists()
        ]

    @server.tool()
    def playlist_tracks(playlist_id: str) -> List[dict]:
        """Tracks in one of the listener's own playlists (not other people's)."""
        return seen(spotify.playlist_songs(playlist_id, limit=100))

    @server.tool()
    def artist_info(artist_uri: str) -> dict:
        """Genres Spotify lists for an artist (often empty, so a weak signal).
        artist_uri looks like spotify:artist:..., as found in verified tracks."""
        return {"genres": spotify.artist_genres([artist_uri]).get(artist_uri, [])}

    if stage == STAGE_CURATOR:

        @server.tool()
        def playlist_rules() -> dict:
            """The rules submit_playlist enforces for this run."""
            rules = session.rules
            return {
                "min_songs": rules.min_songs,
                "max_songs": rules.max_songs,
                "max_per_artist": rules.max_per_artist,
                "familiar_tracks_allowed": max(
                    rules.familiar_allowance,
                    int(rules.max_songs * rules.familiar_ratio),
                ),
                "note": (
                    "Songs from my_top_tracks / my_recent_tracks count as familiar. "
                    "Different releases of one song count as the same song."
                ),
            }

        @server.tool()
        def submit_playlist(name: str, description: str, uris: List[str]) -> dict:
            """Create the playlist. This is your final action and works once per
            run. `uris` are Spotify track URIs in play order, all obtained from
            the lookup tools. If a rule is broken, nothing is created and the
            response lists violations; fix them and submit again."""
            return session.submit(name, description, uris)

    if stage == STAGE_SONG:

        @server.tool()
        def submit_song(uri: str, reason: str) -> dict:
            """Choose the song of the moment. This is your final action and
            works once per run. `uri` must come from a lookup tool. If the song
            is not allowed, the response lists why; choose another."""
            return session.submit_song(uri, reason)

    return server


def main() -> None:
    dotenv.load_dotenv()
    run_dir = Path(os.environ["AURALIS_RUN_DIR"])
    spotify = Spotify.from_env()
    stage = os.environ.get("AURALIS_STAGE", STAGE_SCOUT)
    create_server(spotify, RunSession(spotify, run_dir), stage).run()
