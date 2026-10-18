import re
from datetime import datetime
from typing import List, Optional

from agent.advisor import Advisor
from agent.prompt_generator import PromptGenerator
from agent.schemas import PlaylistOutcome, PlaylistSuggestion, SongSuggestion
from spotify.library import NoDeviceError


class Auralis:
    def __init__(self, spotify, advisor: Advisor, scrapper=None):
        self.advisor = advisor
        self.prompt_generator = PromptGenerator()
        self.spotify = spotify
        self.scrapper = scrapper
        self.supported_countries = ["de", "us", "in", "jp"]

    _AVG_SONG_MINUTES = 3.5
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

    def _play_or_queue(self, suggestion: SongSuggestion) -> None:
        song = self.spotify.find_track(suggestion.song_title, suggestion.artist_name)
        if song is None:
            raise LookupError(
                f"No Spotify match for '{suggestion.song_title}' by "
                f"{suggestion.artist_name}"
            )
        if self.spotify.is_playing():
            self.spotify.queue_track(song.uri)
        else:
            self.spotify.play_track(song.uri)

    def build_context(self, weather_connector=None, city=None):
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
        recent_songs = self.spotify.recently_played()
        top_tracks = self.spotify.top_tracks()
        playlists = self.spotify.user_playlists()
        all_charts = []
        viral_charts = []
        if self.scrapper:
            for country in self.supported_countries:
                all_charts.append(self.scrapper.get_trending_songs(country=country))
                viral_charts.append(self.scrapper.get_viral_songs(country=country))
        genre_distribution = self._get_recent_genre_distribution(
            recent_songs[:10] + top_tracks[:10]
        )
        return {
            "time_of_day": time_of_day,
            "season": season,
            "my_recently_played_songs": [
                item.model_dump(exclude={"id", "uri"}) for item in recent_songs[:10]
            ],
            "my_top_tracks": [
                item.model_dump(exclude={"id", "uri"}) for item in top_tracks[:10]
            ],
            "my_playlists": [
                item.model_dump(exclude={"id", "uri", "href"}) for item in playlists
            ],
            "my_recent_genre_distribution": genre_distribution,
            "trending_charts": all_charts,
            "viral_charts": viral_charts,
            "my_current_weather": weather.model_dump() if weather else None,
            "my_current_location": location.model_dump(exclude={"lat", "lon"})
            if location
            else None,
        }

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

    def song_of_the_moment_suggestion(
        self,
        weather_connector=None,
        city=None,
        already_suggested: Optional[List[str]] = None,
    ) -> SongSuggestion:
        context = self.build_context(weather_connector=weather_connector, city=city)
        system_prompt, user_prompt = self.prompt_generator.build_suggest_song_prompt(
            {"context": context}, already_suggested
        )
        suggestion = SongSuggestion.model_validate(
            self.advisor.advise(
                system_prompt, user_prompt, SongSuggestion.model_json_schema()
            )
        )
        self._play_or_queue(suggestion)
        return suggestion

    def playlist_generator(
        self, user_prompt, weather_connector=None, city=None
    ) -> PlaylistOutcome:
        context = self.build_context(weather_connector=weather_connector, city=city)
        target_song_count = self._estimate_target_song_count(user_prompt)
        schema = PlaylistSuggestion.model_json_schema()
        if target_song_count:
            schema["properties"]["songs"]["minItems"] = max(5, target_song_count - 3)
        system_prompt, prompt = self.prompt_generator.build_playlist_prompt(
            user_prompt, context, target_song_count
        )
        suggestion = PlaylistSuggestion.model_validate(
            self.advisor.advise(system_prompt, prompt, schema)
        )
        build = self.spotify.build_playlist(
            suggestion.playlist_name,
            [(song.song_title, song.artist_name) for song in suggestion.songs],
            description=suggestion.reason,
        )
        playing = self._start_playlist_if_idle(build.playlist.uri)
        return PlaylistOutcome(
            suggestion=suggestion,
            playlist_url=build.playlist.url,
            added=[f"{song.name} - {song.artists[0].name}" for song in build.added],
            not_found=build.not_found,
            playing=playing,
        )

    def _start_playlist_if_idle(self, playlist_uri: str) -> bool:
        try:
            if self.spotify.is_playing():
                return False
            self.spotify.play_playlist(playlist_uri)
            return True
        except NoDeviceError:
            return False
