from openai import OpenAI
import copy
import json
import re
from datetime import datetime
from agent.prompt_generator import PromptGenerator
from agent.tool_essentials import ToolRegistry
from typing import List


class Auralis:
    def __init__(
        self,
        spotify_connector,
        openai_api_key,
        scrapper=None,
        model="gemini-3.8-flash",
    ):
        self.openai_api_key = openai_api_key
        self.model = model
        self.base_url = self.supported_models[self.model]
        self.openai = OpenAI(api_key=self.openai_api_key, base_url=self.base_url)
        self.prompt_generator = PromptGenerator()
        self.spotify_connector = spotify_connector
        self.scrapper = scrapper
        self.supported_countries = ["de", "us", "in", "jp"]

    registry = ToolRegistry()
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
    supported_models = {
        "gemini-3.8-flash": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3.7-flash": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3.6-flash": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3-flash-preview": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gpt-4.1": "https://api.openai.com/v1/",
        "gpt-4o": "https://api.openai.com/v1/",
        "o4-mini": "https://api.openai.com/v1/",
        "local_lm_studio": "localhost:1234/v1",
    }

    @registry.register(description="Suggest and plays a song in spotify", tags=["song"])
    def suggest_song(self, song_title: str, artist_name: str, reason: str) -> str:
        """Suggests and plays a song in spotify based on the given song title, artist name

        Args:
            song_title (str): The title of the song to be suggested.
            artist_name (str): The name of the artist of the song to be suggested.
            reason (str): The reason why this song should be suggested.

        Returns:
            Song: The suggested song.
        """
        search_query = f"{song_title} {artist_name}"
        song = self.spotify_connector.search_for_song(search_query)[0]
        if self.spotify_connector.is_currently_playing():
            self.spotify_connector.add_songs_to_queue(song.uri)
        else:
            self.spotify_connector.play_song(song.uri)
        return song_title, artist_name, reason

    @registry.register(description="Assembles a playlist in spotify", tags=["playlist"])
    def generate_playlist(
        self, playlist_name: str, songs: List[str], reason: str
    ) -> str:
        """Generates a playlist in spotify with the given songs

        Args:
            playlist_name (str): The name of the playlist to be generated.
            songs (List[str]): The list of songs to be added to the playlist.

        Returns:
            str: The success message.
        """
        self.spotify_connector.generate_playlist_from_auralis(playlist_name, songs)
        return playlist_name, songs, reason

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
        recent_songs = self.spotify_connector.recently_played()
        top_tracks = self.spotify_connector.users_top_tracks()
        playlists = self.spotify_connector.get_user_playlists()
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
        if not artist_uris or not hasattr(self.spotify_connector, "get_artists_genres"):
            return {}
        genre_counts = {}
        for genres in self.spotify_connector.get_artists_genres(
            list(artist_uris)
        ).values():
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

    def song_of_the_moment_suggestion(self, weather_connector=None, city=None):
        context = self.build_context(weather_connector=weather_connector, city=city)
        user_prompt = {"context": context}
        tools = self.registry.to_openai_tools()
        response = self.openai.chat.completions.create(
            model=self.model,
            messages=self.prompt_generator.build_suggest_song_messages(user_prompt),
            tools=tools,
            temperature=0.7,
        )
        message = response.choices[0].message
        if message.tool_calls:
            for tool_call in message.tool_calls:
                return self.call_function(tool_call)
            print("No valid suggestion.")
            return None

    def call_function(self, tool_call):
        tool_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        tool_func = self.registry.tools[tool_name]["function"]
        tool_func = tool_func.__get__(self, self.__class__)
        return tool_func(**arguments)

    def playlist_generator(self, user_prompt, weather_connector=None, city=None):
        tools = copy.deepcopy(self.registry.to_openai_tools())
        context = self.build_context(weather_connector=weather_connector, city=city)
        target_song_count = self._estimate_target_song_count(user_prompt)
        if target_song_count:
            for tool in tools:
                if tool["function"]["name"] == "generate_playlist":
                    tool["function"]["parameters"]["properties"]["songs"][
                        "minItems"
                    ] = max(5, target_song_count - 3)
        try:
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=self.prompt_generator.build_playlist_messages(
                    user_prompt, context, target_song_count
                ),
                tools=tools,
                temperature=0.7,
            )
            message = response.choices[0].message
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    return self.call_function(tool_call)
        except Exception as e:
            return {}, [], str(e)
