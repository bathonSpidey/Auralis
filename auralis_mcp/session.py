"""Per-run state for the Auralis MCP server, and the gate on playlist creation.

Claude gets exactly one write capability: submit_playlist. The rules live here,
in code, so they hold no matter what the prompt says. A submission that breaks
a rule is rejected with a list of violations Claude can fix within the same
session. State is kept in a run directory so the service (and a second stage
of the same run) can read what happened:

    rules.json     written by the service before the run
    verified.json  every track a lookup tool has returned (the only URIs that
                   may be submitted)
    outcome.json   written once, when a playlist is accepted
"""

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from models.song import Song
from models.song_key import song_key

MAX_NAME_LENGTH = 100


@dataclass
class RunRules:
    min_songs: int = 8
    max_songs: int = 50
    max_per_artist: int = 2
    # Songs the listener already knows, as [title, artist]; at most
    # `familiar_allowance` or `familiar_ratio` of the playlist (whichever is
    # larger) may come from them. Matched by song, not URI, because every
    # release of a song has its own URI.
    familiar_tracks: List[List[str]] = field(default_factory=list)
    familiar_allowance: int = 4
    familiar_ratio: float = 0.3
    # Previously suggested or disliked songs, as [title, artist], must never
    # come back.
    excluded_tracks: List[List[str]] = field(default_factory=list)
    dry_run: bool = False


def _write_json(path: Path, data) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_rules(run_dir: Path, rules: RunRules) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "rules.json", asdict(rules))


def read_outcome(run_dir: Path) -> Optional[dict]:
    return _read_json(Path(run_dir) / "outcome.json", None)


def read_verified(run_dir: Path) -> Dict[str, dict]:
    return _read_json(Path(run_dir) / "verified.json", {})


def describe(song: Song) -> dict:
    album = song.album
    return {
        "uri": song.uri,
        "title": song.name,
        "artist": song.artists[0].name if song.artists else "",
        "album": album.name if album else None,
        "year": album.release_date[:4] if album and album.release_date else None,
    }


class RunSession:
    def __init__(self, spotify, run_dir: Path):
        self.spotify = spotify
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.rules = RunRules(**_read_json(self.run_dir / "rules.json", {}))
        self._excluded = {song_key(*pair) for pair in self.rules.excluded_tracks}
        self._familiar = {song_key(*pair) for pair in self.rules.familiar_tracks}
        self.verified: Dict[str, dict] = read_verified(self.run_dir)

    def remember(self, songs: Sequence[Song]) -> None:
        """Record tracks Spotify has returned; only these may be submitted."""
        changed = False
        for song in songs:
            if song.uri not in self.verified:
                entry = describe(song)
                entry["artist_uri"] = song.artists[0].uri if song.artists else ""
                self.verified[song.uri] = entry
                changed = True
        if changed:
            _write_json(self.run_dir / "verified.json", self.verified)

    def key(self, uri: str) -> str:
        entry = self.verified[uri]
        return song_key(entry["title"], entry["artist"])

    def label(self, uri: str) -> str:
        entry = self.verified.get(uri)
        return f"{entry['title']} - {entry['artist']}" if entry else uri

    def check(self, name: str, uris: Sequence[str]) -> List[str]:
        rules = self.rules
        violations = []
        if not name.strip():
            violations.append("The playlist needs a name.")
        elif len(name) > MAX_NAME_LENGTH:
            violations.append(
                f"The name is too long (max {MAX_NAME_LENGTH} characters)."
            )

        unknown = [u for u in uris if u not in self.verified]
        if unknown:
            violations.append(
                "These URIs were never returned by a Spotify lookup in this run, "
                "so they cannot be used (search for the track first): "
                + ", ".join(unknown)
            )
        by_song: Dict[str, List[str]] = {}
        for uri in dict.fromkeys(u for u in uris if u in self.verified):
            by_song.setdefault(self.key(uri), []).append(uri)
        repeated = [u for u in uris if list(uris).count(u) > 1]
        same_song = [group[0] for group in by_song.values() if len(group) > 1]
        duplicates = list(dict.fromkeys(repeated + same_song))
        if duplicates:
            violations.append(
                "The same song appears more than once (different releases of a "
                "song count as the same): "
                + ", ".join(self.label(u) for u in duplicates)
            )
        if not rules.min_songs <= len(uris) <= rules.max_songs:
            violations.append(
                f"The playlist needs between {rules.min_songs} and {rules.max_songs} "
                f"tracks; you submitted {len(uris)}."
            )

        known = [u for u in dict.fromkeys(uris) if u in self.verified]
        excluded = [u for u in known if self.key(u) in self._excluded]
        if excluded:
            violations.append(
                "Already suggested before or disliked by the listener; replace: "
                + ", ".join(self.label(u) for u in excluded)
            )

        per_artist: Dict[str, List[str]] = {}
        for uri in known:
            per_artist.setdefault(self.verified[uri]["artist"], []).append(uri)
        for artist, tracks in per_artist.items():
            if len(tracks) > rules.max_per_artist:
                violations.append(
                    f"{artist} appears {len(tracks)} times; the maximum is "
                    f"{rules.max_per_artist} per artist."
                )

        familiar = [u for u in known if self.key(u) in self._familiar]
        allowed = max(rules.familiar_allowance, int(len(uris) * rules.familiar_ratio))
        if len(familiar) > allowed:
            violations.append(
                f"{len(familiar)} tracks come from the listener's recent or top "
                f"tracks, but at most {allowed} may; swap some for discoveries: "
                + ", ".join(self.label(u) for u in familiar)
            )
        return violations

    def submit(self, name: str, description: str, uris: Sequence[str]) -> dict:
        if (self.run_dir / "outcome.json").exists():
            return {
                "ok": False,
                "violations": ["A playlist was already created in this run."],
            }
        uris = list(uris)
        violations = self.check(name, uris)
        if violations:
            return {"ok": False, "violations": violations}

        playlist = None
        if not self.rules.dry_run:
            playlist = self.spotify.create_playlist(name, description)
            try:
                self.spotify.add_to_playlist(playlist.id, uris)
            except Exception:
                try:
                    self.spotify.delete_playlist(playlist.uri)
                except (
                    Exception
                ):  # best-effort rollback, original error re-raised  # nosec B110
                    pass
                raise
        _write_json(
            self.run_dir / "outcome.json",
            {
                "kind": "playlist",
                "name": name,
                "description": description,
                "dry_run": self.rules.dry_run,
                "playlist_id": playlist.id if playlist else None,
                "playlist_uri": playlist.uri if playlist else None,
                "playlist_url": playlist.url if playlist else None,
                "tracks": [self.verified[u] for u in uris],
            },
        )
        return {
            "ok": True,
            "message": (
                "Accepted. This is a dry run: the playlist was validated and "
                "recorded, and nothing is created on Spotify. You are done."
                if self.rules.dry_run
                else "Playlist created. You are done."
            ),
            "playlist_url": playlist.url if playlist else None,
            "track_count": len(uris),
        }

    def submit_song(self, uri: str, reason: str) -> dict:
        """The song-of-the-moment pick. Same gate idea as a playlist: the
        track must be verified, not excluded, and not something the listener
        already knows."""
        if (self.run_dir / "outcome.json").exists():
            return {
                "ok": False,
                "violations": ["A song was already chosen in this run."],
            }
        violations = []
        if uri not in self.verified:
            violations.append(
                f"{uri} was never returned by a Spotify lookup in this run "
                "(search for the track first)."
            )
        else:
            key = self.key(uri)
            if key in self._excluded:
                violations.append(
                    f"{self.label(uri)} was already suggested before or is disliked; "
                    "choose a different song."
                )
            if key in self._familiar:
                violations.append(
                    f"{self.label(uri)} is already in the listener's recent, top or "
                    "liked songs; choose a discovery."
                )
        if not reason.strip():
            violations.append("Give a short reason for the choice.")
        if violations:
            return {"ok": False, "violations": violations}
        _write_json(
            self.run_dir / "outcome.json",
            {
                "kind": "song",
                "dry_run": self.rules.dry_run,
                "reason": reason,
                "track": self.verified[uri],
            },
        )
        return {"ok": True, "message": "Song chosen. You are done."}
