import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from agent.advisor import Advisor
from agent.depth import PLANS, Depth
from agent.prompt_generator import PromptGenerator
from agent.schemas import (
    CuratorAnswer,
    PlaylistOutcome,
    ScoutReport,
    SongAnswer,
    SongOutcome,
    TrackInfo,
)
from agent.workspace import run_workspace
from auralis_mcp.config import allowed_tools, mcp_config
from auralis_mcp.server import STAGE_CURATOR, STAGE_SCOUT, STAGE_SONG
from auralis_mcp.session import RunRules, read_outcome, read_verified, write_rules
from models.playlist import Playlist
from models.song import Song
from models.song_key import song_key
from spotify.client import SpotifyError
from spotify.library import NoDeviceError
from store.history import Store

logger = logging.getLogger(__name__)

LIKED_SAMPLE = 20
# Songs from this many latest creations may not come back (back to back only).
RECENT_CREATIONS = 2
CURATOR_BUDGET_USD = 3.0
SONG_BUDGET_USD = 3.0


class AuralisError(RuntimeError):
    pass


Progress = Optional[Callable[[str], None]]


def _report(progress: Progress, stage: str) -> None:
    if progress:
        progress(stage)


@dataclass
class Listening:
    """What the listener has been playing, fetched once per request."""

    recent: List[Song] = field(default_factory=list)
    top_short: List[Song] = field(default_factory=list)
    top_medium: List[Song] = field(default_factory=list)
    top_long: List[Song] = field(default_factory=list)
    liked: List[Song] = field(default_factory=list)  # all of them
    liked_sample: List[Song] = field(default_factory=list)  # for the prompt
    playlists: List[Playlist] = field(default_factory=list)

    def familiar(self) -> List[Song]:
        return (
            self.recent + self.top_short + self.top_medium + self.top_long + self.liked
        )


class Auralis:
    def __init__(
        self,
        spotify,
        advisor: Advisor,
        scrapper=None,
        runs_dir: Optional[Path] = None,
        store: Optional[Store] = None,
    ):
        self.advisor = advisor
        self.prompt_generator = PromptGenerator()
        self.spotify = spotify
        self.scrapper = scrapper
        self.runs_dir = runs_dir
        self.store = store
        self.supported_countries = ["de", "us", "in", "jp"]

    _AVG_SONG_MINUTES = 3.5
    _DEFAULT_SONGS = (8, 30)
    _WORD_NUMBERS = {
        "a": 1,
        "an": 1,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }
    _SPELLED_DURATION_PATTERN = re.compile(
        r"\b("
        + "|".join(_WORD_NUMBERS.keys())
        + r")\b(\s*-?\s*(?:hours?|hrs?|minutes?|mins?)\b)",
        re.I,
    )
    _DURATION_PATTERNS = [
        (re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:hours?|hrs?|h)\b", re.I), 60),
        (re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:minutes?|mins?)\b", re.I), 1),
    ]
    _LONG_SESSION_KEYWORDS = [
        "road trip",
        "roadtrip",
        "long drive",
        "party",
        "all night",
        "marathon",
    ]
    _SHORT_SESSION_KEYWORDS = ["quick", "short", "one song", "single song"]

    # ── public flows ────────────────────────────────────────────────────
    def playlist_generator(
        self,
        user_prompt: str,
        weather_connector=None,
        city=None,
        depth: Depth = Depth.AUTO,
        dry_run: bool = False,
        device_id: Optional[str] = None,
        excluded: Sequence[Tuple[str, str]] = (),
        source: str = "web",
        progress: Progress = None,
    ) -> PlaylistOutcome:
        """Scout (research, no write access) then curator (the one gated write).

        `excluded` are (title, artist) pairs that must not appear, on top of
        the songs of the last few creations. Likes and dislikes only steer the
        prompts; repeats are otherwise allowed.
        """
        plan = PLANS[Depth(depth)]
        _report(progress, "taste")
        listening = self._listen()
        context = self.build_context(weather_connector, city, listening)
        target = self._estimate_target_song_count(user_prompt)
        low, high = self._song_bounds(target)
        rules = RunRules(
            min_songs=low,
            max_songs=high,
            familiar_tracks=self._pairs(listening.familiar()),
            excluded_tracks=self._excluded(excluded),
            dry_run=dry_run,
        )
        feedback = self._feedback()
        pool_size = min(80, max(20, 2 * (target or 15)))

        with run_workspace(self.runs_dir) as run_dir:
            write_rules(run_dir, rules)
            _report(progress, "scout")
            system, user = self.prompt_generator.scout(
                user_prompt,
                context,
                plan.guidance,
                low,
                high,
                pool_size,
                target,
                feedback,
            )
            report = ScoutReport.model_validate(
                self.advisor.advise(
                    system,
                    user,
                    ScoutReport.model_json_schema(),
                    mcp_config=mcp_config(run_dir, STAGE_SCOUT),
                    allowed_tools=(allowed_tools(), *plan.builtin_tools),
                    builtin_tools=plan.builtin_tools,
                    max_budget_usd=plan.budget_usd,
                )
            )
            pool = self._usable_pool(report, read_verified(run_dir), rules)
            if len(pool) < low:
                raise AuralisError(
                    f"The scout found only {len(pool)} usable tracks; need {low}"
                )

            _report(progress, "curate")
            answer, outcome = None, None
            for attempt in (1, 2):
                note = (
                    ""
                    if attempt == 1
                    else "Your previous attempt ended without an accepted "
                    "submit_playlist. Submit a valid playlist now."
                )
                system, user = self.prompt_generator.curator(
                    user_prompt,
                    context,
                    report.interpretation,
                    pool,
                    low,
                    high,
                    rules.max_per_artist,
                    target,
                    note,
                    feedback,
                )
                answer = CuratorAnswer.model_validate(
                    self.advisor.advise(
                        system,
                        user,
                        CuratorAnswer.model_json_schema(),
                        mcp_config=mcp_config(run_dir, STAGE_CURATOR),
                        allowed_tools=(allowed_tools(),),
                        max_budget_usd=CURATOR_BUDGET_USD,
                    )
                )
                outcome = read_outcome(run_dir)
                if outcome:
                    break
            if not outcome:
                raise AuralisError("The curator did not produce an accepted playlist")

        _report(progress, "finish")
        playback = "none"
        if not dry_run and self._start_playlist(outcome["playlist_uri"], device_id):
            playback = "playing"
        result = PlaylistOutcome(
            name=outcome["name"],
            reason=answer.reason,
            research=report.interpretation,
            playlist_url=outcome["playlist_url"],
            tracks=[TrackInfo(**track) for track in outcome["tracks"]],
            playback=playback,
            dry_run=dry_run,
        )
        if self.store and not dry_run:
            result.id = self.store.record_playlist(
                result, user_prompt, Depth(depth).value, source
            )
        return result

    def song_of_the_moment_suggestion(
        self,
        weather_connector=None,
        city=None,
        depth: Depth = Depth.QUICK,
        dry_run: bool = False,
        device_id: Optional[str] = None,
        excluded: Sequence[Tuple[str, str]] = (),
        source: str = "web",
        progress: Progress = None,
    ) -> SongOutcome:
        plan = PLANS[Depth(depth)]
        _report(progress, "taste")
        listening = self._listen()
        context = self.build_context(weather_connector, city, listening)
        rules = RunRules(
            familiar_tracks=self._pairs(listening.familiar()),
            excluded_tracks=self._excluded(excluded),
            dry_run=dry_run,
        )
        feedback = self._feedback()
        with run_workspace(self.runs_dir) as run_dir:
            write_rules(run_dir, rules)
            _report(progress, "pick")
            outcome, answer = None, None
            for attempt in (1, 2):
                note = (
                    ""
                    if attempt == 1
                    else "Your previous attempt ended without an accepted "
                    "submit_song. Choose a song and submit it now."
                )
                system, user = self.prompt_generator.song(
                    context, plan.guidance, note, feedback
                )
                answer = SongAnswer.model_validate(
                    self.advisor.advise(
                        system,
                        user,
                        SongAnswer.model_json_schema(),
                        mcp_config=mcp_config(run_dir, STAGE_SONG),
                        allowed_tools=(allowed_tools(), *plan.builtin_tools),
                        builtin_tools=plan.builtin_tools,
                        max_budget_usd=min(plan.budget_usd, SONG_BUDGET_USD),
                    )
                )
                outcome = read_outcome(run_dir)
                if outcome:
                    break
            if not outcome:
                raise AuralisError("No song was chosen")
        _report(progress, "finish")
        playback = "none" if dry_run else self._play_song(outcome["track"], device_id)
        result = SongOutcome(
            track=TrackInfo(**outcome["track"]),
            reason=answer.reason,
            playback=playback,
            dry_run=dry_run,
        )
        if self.store and not dry_run:
            result.id = self.store.record_song(result, Depth(depth).value, source)
        return result

    def commit_playlist(
        self,
        preview: PlaylistOutcome,
        prompt: str,
        depth: Depth = Depth.AUTO,
        device_id: Optional[str] = None,
        source: str = "web",
    ) -> PlaylistOutcome:
        """Create a previewed playlist exactly as shown: no new research."""
        if not preview.dry_run:
            raise AuralisError("This playlist was already created")
        playlist = self.spotify.create_playlist(preview.name, preview.reason)
        try:
            self.spotify.add_to_playlist(playlist.id, [t.uri for t in preview.tracks])
        except Exception:
            try:
                self.spotify.delete_playlist(playlist.uri)
            except (
                Exception
            ):  # best-effort rollback, original error re-raised  # nosec B110
                pass
            raise
        playing = self._start_playlist(playlist.uri, device_id)
        result = preview.model_copy(
            update={
                "playlist_url": playlist.url,
                "playback": "playing" if playing else "none",
                "dry_run": False,
            }
        )
        if self.store:
            result.id = self.store.record_playlist(
                result, prompt, Depth(depth).value, source
            )
        return result

    def commit_song(
        self,
        preview: SongOutcome,
        depth: Depth = Depth.QUICK,
        device_id: Optional[str] = None,
        source: str = "web",
    ) -> SongOutcome:
        """Play and record a previewed song of the moment."""
        if not preview.dry_run:
            raise AuralisError("This song was already chosen")
        playback = self._play_song(preview.track.model_dump(), device_id)
        result = preview.model_copy(update={"playback": playback, "dry_run": False})
        if self.store:
            result.id = self.store.record_song(result, Depth(depth).value, source)
        return result

    # ── playback ────────────────────────────────────────────────────────
    def _start_playlist(self, uri: str, device_id: Optional[str]) -> bool:
        """Play on the chosen device, else on an active device that is idle.
        Never interrupts what is already playing and never picks a device."""
        try:
            if device_id is None and self.spotify.is_playing():
                return False
            self.spotify.play_playlist(uri, device_id=device_id)
            return True
        except NoDeviceError:
            return False

    def _play_song(self, track: dict, device_id: Optional[str]) -> str:
        try:
            if device_id is None and self.spotify.is_playing():
                self.spotify.queue_track(track["uri"])
                return "queued"
            self.spotify.play_track(track["uri"], device_id=device_id)
            return "playing"
        except NoDeviceError:
            return "none"

    # ── context ─────────────────────────────────────────────────────────
    def _listen(self) -> Listening:
        liked = self._liked_songs()
        return Listening(
            recent=self.spotify.recently_played(),
            top_short=self.spotify.top_tracks(limit=50, time_range="short_term"),
            top_medium=self.spotify.top_tracks(limit=50, time_range="medium_term"),
            top_long=self.spotify.top_tracks(limit=50, time_range="long_term"),
            liked=liked,
            liked_sample=random.sample(
                liked, min(LIKED_SAMPLE, len(liked))
            ),  # variety, not security  # nosec B311
            playlists=self.spotify.user_playlists(),
        )

    def _liked_songs(self) -> List[Song]:
        """Liked songs enrich the profile but are not essential, so a failure
        (e.g. the login predates the user-library-read scope) only warns."""
        try:
            return self.spotify.liked_songs()
        except SpotifyError as e:
            logger.warning(
                "Could not read liked songs (%s); run `python -m spotify.login` "
                "again if the scope is missing",
                e,
            )
            return []

    def build_context(
        self, weather_connector=None, city=None, listening: Optional[Listening] = None
    ):
        listening = listening or self._listen()
        hour = datetime.now().hour
        month = datetime.now().month
        location = (
            weather_connector.encode_location(city) if weather_connector else None
        )
        weather = (
            weather_connector.get_current_location_weather(city)
            if weather_connector
            else None
        )
        if location:
            dt = weather_connector.encode_time(location)
            hour = dt.hour
            month = dt.month
        time_of_day = (
            "morning"
            if hour < 12 and hour >= 4
            else "afternoon"
            if hour < 18 and hour >= 12
            else "evening"
            if hour < 21 and hour >= 18
            else "night"
            if hour < 23 and hour >= 21
            else "late night"
        )
        season = (
            "spring"
            if month in [3, 4, 5]
            else "summer"
            if month in [6, 7, 8]
            else "autumn"
            if month in [9, 10, 11]
            else "winter"
        )
        charts = []
        if self.scrapper:
            for country in self.supported_countries:
                trending = self.scrapper.get_trending_songs(country=country)
                if trending:
                    charts.append(trending)
        exclude = {"id", "uri", "album"}
        return {
            "time_of_day": time_of_day,
            "season": season,
            "my_recently_played_songs": [
                s.model_dump(exclude=exclude) for s in listening.recent[:10]
            ],
            "my_top_tracks_this_month": [
                s.model_dump(exclude=exclude) for s in listening.top_short[:10]
            ],
            "my_top_tracks_overall": [
                s.model_dump(exclude=exclude) for s in listening.top_medium[:10]
            ],
            "my_liked_songs_sample": [
                s.model_dump(exclude=exclude) for s in listening.liked_sample
            ],
            "my_playlists": [
                p.model_dump(exclude={"id", "uri", "href"}) for p in listening.playlists
            ],
            "my_recent_genre_distribution": self._get_recent_genre_distribution(
                listening.recent[:10] + listening.top_medium[:10]
            ),
            "trending_charts": charts,
            "my_current_weather": weather.model_dump() if weather else None,
            "my_current_location": location.model_dump(exclude={"lat", "lon"})
            if location
            else None,
        }

    def _excluded(self, extra: Sequence[Tuple[str, str]]) -> List[List[str]]:
        recent = self.store.recent_songs(RECENT_CREATIONS) if self.store else []
        return [list(pair) for pair in (*extra, *recent)]

    def _feedback(self) -> Optional[dict]:
        return self.store.taste_signals() if self.store else None

    @staticmethod
    def _pairs(songs: Sequence[Song]) -> List[List[str]]:
        return [[s.name, s.artists[0].name] for s in songs if s.artists]

    def _usable_pool(self, report: ScoutReport, verified: dict, rules: RunRules):
        """The scout's candidates minus anything unverified, excluded or repeated."""
        excluded = {song_key(*pair) for pair in rules.excluded_tracks}
        seen, pool = set(), []
        for candidate in report.candidates:
            entry = verified.get(candidate.uri)
            if entry is None:
                continue
            key = song_key(entry["title"], entry["artist"])
            if key in excluded or key in seen:
                continue
            seen.add(key)
            pool.append(
                {
                    "uri": candidate.uri,
                    "title": entry["title"],
                    "artist": entry["artist"],
                    "why": candidate.why,
                }
            )
        return pool

    def _song_bounds(self, target: Optional[int]) -> Tuple[int, int]:
        if not target:
            return self._DEFAULT_SONGS
        return max(5, target - 3), min(100, target + 5)

    def _get_recent_genre_distribution(self, songs):
        artist_uris = {song.artists[0].uri for song in songs if song.artists}
        if not artist_uris:
            return {}
        genre_counts = {}
        for genres in self.spotify.artist_genres(list(artist_uris)).values():
            for genre in genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
        return dict(
            sorted(genre_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        )

    def _normalize_spelled_numbers(self, text: str) -> str:
        def replace(match):
            word = match.group(1).lower()
            number = self._WORD_NUMBERS.get(word)
            return f"{number}{match.group(2)}" if number else match.group(0)

        return self._SPELLED_DURATION_PATTERN.sub(replace, text)

    def _estimate_target_song_count(self, user_prompt: str):
        user_prompt = self._normalize_spelled_numbers(user_prompt)
        total_minutes = 0
        found = False
        for pattern, minutes_per_unit in self._DURATION_PATTERNS:
            for match in pattern.finditer(user_prompt):
                total_minutes += float(match.group(1)) * minutes_per_unit
                found = True
        if found and total_minutes > 0:
            return max(5, round(total_minutes / self._AVG_SONG_MINUTES))
        lowered = user_prompt.lower()
        if any(keyword in lowered for keyword in self._SHORT_SESSION_KEYWORDS):
            return 8
        if any(keyword in lowered for keyword in self._LONG_SESSION_KEYWORDS):
            return 25
        return None
