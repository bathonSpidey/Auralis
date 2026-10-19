"""SQLite history and feedback, kept in the data directory (outside the repo, so
a deploy never touches it).

- suggestions / suggestion_tracks: what Auralis created, for the history page and
  the back-to-back repeat rule. Real creations only, never dry runs.
- feedback: one like or dislike per song (not per suggestion). No row means
  neutral; clearing a rating deletes the row.

Old history is pruned so the file stays small; ratings are never pruned.
"""

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from agent.schemas import PlaylistOutcome, SongOutcome, TrackInfo
from models.song_key import song_key

RETENTION_DAYS = 365
MAX_SUGGESTIONS = 500
_VACUUM_THRESHOLD_BYTES = 512 * 1024
LIKE, DISLIKE = "like", "dislike"

_SCHEMA_VERSION = 1
_SCHEMA = """
CREATE TABLE suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('playlist', 'song')),
    prompt TEXT,
    depth TEXT NOT NULL,
    source TEXT NOT NULL,
    name TEXT,
    reason TEXT NOT NULL,
    research TEXT,
    playlist_url TEXT
);
CREATE TABLE suggestion_tracks (
    suggestion_id INTEGER NOT NULL REFERENCES suggestions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    song_key TEXT NOT NULL,
    uri TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    year TEXT,
    PRIMARY KEY (suggestion_id, position)
);
CREATE TABLE feedback (
    song_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    uri TEXT,
    rating TEXT NOT NULL CHECK (rating IN ('like', 'dislike')),
    updated_at INTEGER NOT NULL
);
CREATE INDEX suggestions_created ON suggestions (created_at DESC);
"""


def default_db_path() -> Path:
    data_dir = os.getenv("AURALIS_DATA_DIR") or Path.home() / "auralis-data"
    return Path(data_dir) / "auralis.db"


class Store:
    def __init__(
        self,
        path: Optional[Path] = None,
        clock: Callable[[], float] = time.time,
    ):
        self.path = Path(path) if path else default_db_path()
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] < _SCHEMA_VERSION:
                db.executescript(_SCHEMA)
                db.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        self.prune()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("PRAGMA synchronous = NORMAL")
            db.execute("PRAGMA foreign_keys = ON")
            with db:  # commit on success, roll back on error
                yield db
        finally:
            db.close()

    # ── creations ───────────────────────────────────────────────────────
    def record_playlist(
        self, outcome: PlaylistOutcome, prompt: str, depth: str, source: str
    ) -> int:
        return self._record(
            "playlist",
            outcome.tracks,
            prompt=prompt,
            depth=depth,
            source=source,
            name=outcome.name,
            reason=outcome.reason,
            research=outcome.research,
            playlist_url=outcome.playlist_url,
        )

    def record_song(self, outcome: SongOutcome, depth: str, source: str) -> int:
        return self._record(
            "song",
            [outcome.track],
            prompt=None,
            depth=depth,
            source=source,
            name=outcome.track.title,
            reason=outcome.reason,
            research=None,
            playlist_url=None,
        )

    def _record(self, kind: str, tracks: List[TrackInfo], **fields) -> int:
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO suggestions (created_at, kind, prompt, depth, source, "
                "name, reason, research, playlist_url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(self.clock()),
                    kind,
                    fields["prompt"],
                    fields["depth"],
                    fields["source"],
                    fields["name"],
                    fields["reason"],
                    fields["research"],
                    fields["playlist_url"],
                ),
            )
            suggestion_id = cursor.lastrowid
            db.executemany(
                "INSERT INTO suggestion_tracks (suggestion_id, position, song_key, "
                "uri, title, artist, album, year) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        suggestion_id,
                        position,
                        song_key(t.title, t.artist),
                        t.uri,
                        t.title,
                        t.artist,
                        t.album,
                        t.year,
                    )
                    for position, t in enumerate(tracks)
                ],
            )
        self.prune()
        return suggestion_id

    def recent_songs(self, creations: int) -> List[Tuple[str, str]]:
        """(title, artist) of every song in the last `creations` creations."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT DISTINCT title, artist FROM suggestion_tracks WHERE "
                "suggestion_id IN (SELECT id FROM suggestions ORDER BY id DESC LIMIT ?)",
                (creations,),
            ).fetchall()
        return [(row["title"], row["artist"]) for row in rows]

    def history(self, limit: int = 50, offset: int = 0) -> List[dict]:
        """Newest first, each with its tracks and their current rating."""
        with self._connect() as db:
            suggestions = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM suggestions ORDER BY id DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            ]
            for suggestion in suggestions:
                suggestion["tracks"] = [
                    dict(row)
                    for row in db.execute(
                        "SELECT t.position, t.uri, t.title, t.artist, t.album, "
                        "t.year, f.rating FROM suggestion_tracks t "
                        "LEFT JOIN feedback f ON f.song_key = t.song_key "
                        "WHERE t.suggestion_id = ? ORDER BY t.position",
                        (suggestion["id"],),
                    )
                ]
        return suggestions

    def track_uris(self, suggestion_id: int) -> List[str]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT uri FROM suggestion_tracks WHERE suggestion_id = ? "
                "ORDER BY position",
                (suggestion_id,),
            ).fetchall()
        return [row["uri"] for row in rows]

    # ── feedback ────────────────────────────────────────────────────────
    def rate_track(self, suggestion_id: int, uri: str, rating: Optional[str]) -> None:
        """Rate a song shown in the history. `None` makes it neutral again."""
        with self._connect() as db:
            row = db.execute(
                "SELECT title, artist, uri FROM suggestion_tracks "
                "WHERE suggestion_id = ? AND uri = ?",
                (suggestion_id, uri),
            ).fetchone()
            if row is None:
                raise KeyError(f"No track {uri} in suggestion {suggestion_id}")
            self._set_rating(db, row["title"], row["artist"], row["uri"], rating)

    def change_rating(self, key: str, rating: Optional[str]) -> None:
        """Change or clear a rating from the likes/dislikes tab."""
        with self._connect() as db:
            row = db.execute(
                "SELECT title, artist, uri FROM feedback WHERE song_key = ?", (key,)
            ).fetchone()
            if row is None:
                raise KeyError(f"No rated song {key}")
            self._set_rating(db, row["title"], row["artist"], row["uri"], rating)

    def _set_rating(self, db, title, artist, uri, rating: Optional[str]) -> None:
        key = song_key(title, artist)
        if rating is None:
            db.execute("DELETE FROM feedback WHERE song_key = ?", (key,))
            return
        if rating not in (LIKE, DISLIKE):
            raise ValueError(f"rating must be '{LIKE}', '{DISLIKE}' or None")
        db.execute(
            "INSERT INTO feedback (song_key, title, artist, uri, rating, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(song_key) DO UPDATE SET "
            "rating = excluded.rating, updated_at = excluded.updated_at",
            (key, title, artist, uri, rating, int(self.clock())),
        )

    def ratings(self, rating: Optional[str] = None) -> List[dict]:
        """Every rated song, most recently changed first (the likes/dislikes tab)."""
        query = "SELECT song_key, title, artist, uri, rating, updated_at FROM feedback"
        params: tuple = ()
        if rating:
            query += " WHERE rating = ?"
            params = (rating,)
        with self._connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    query + " ORDER BY updated_at DESC, rowid DESC", params
                )
            ]

    def taste_signals(self, limit: int = 30) -> Dict[str, List[Tuple[str, str]]]:
        """Recent likes and dislikes as (title, artist), for the prompts."""
        return {
            kind: [(row["title"], row["artist"]) for row in self.ratings(kind)[:limit]]
            for kind in (LIKE, DISLIKE)
        }

    # ── housekeeping ────────────────────────────────────────────────────
    def prune(self) -> int:
        """Drop old history. Ratings are kept: they are tiny and are the
        listener's actual preferences."""
        cutoff = int(self.clock()) - RETENTION_DAYS * 86400
        with self._connect() as db:
            removed = db.execute(
                "DELETE FROM suggestions WHERE created_at < ? OR id NOT IN "
                "(SELECT id FROM suggestions ORDER BY id DESC LIMIT ?)",
                (cutoff, MAX_SUGGESTIONS),
            ).rowcount
        if removed:
            self._shrink_if_wasteful()
        return removed

    def _shrink_if_wasteful(self) -> None:
        """SQLite reuses freed pages, so the file only needs a VACUUM when a
        lot of space has become reclaimable at once."""
        db = sqlite3.connect(self.path, timeout=10)
        try:
            free_pages = db.execute("PRAGMA freelist_count").fetchone()[0]
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            if free_pages * page_size > _VACUUM_THRESHOLD_BYTES:
                db.execute("VACUUM")
        finally:
            db.close()
