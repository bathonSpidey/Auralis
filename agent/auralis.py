from openai import OpenAI
import json
from datetime import datetime
from agent.prompt_generator import PromptGenerator
from agent.tool_essentials import ToolRegistry
from typing import List


class Auralis:
    def __init__(
        self,
        spotify_connector,
        openai_api_key,
        lastfm_connector,
        model="gemini-2.0-flash",
    ):
        self.openai_api_key = openai_api_key
        self.model = model
        self.base_url = self.supported_models[self.model]
        self.openai = OpenAI(api_key=self.openai_api_key, base_url=self.base_url)
        self.prompt_generator = PromptGenerator()
        self.spotify_connector = spotify_connector
        self.lastfm_connector = lastfm_connector

    registry = ToolRegistry()
    supported_models = {
        "gemini-2.0-flash": "https://generativelanguage.googleapis.com/v1beta/openai/",
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
        top_songs = self.lastfm_connector.get_top_songs()
        return {
            "time_of_day": time_of_day,
            "season": season,
            "current_trending_songs_in_the_world": [
                item.model_dump() for item in top_songs
            ],
            "my_recently_played_songs": [
                item.model_dump(exclude={"id", "uri"}) for item in recent_songs[:20]
            ],
            "my_top_tracks": [
                item.model_dump(exclude={"id", "uri"}) for item in top_tracks[:13]
            ],
            "my_playlists": [
                item.model_dump(exclude={"id", "uri", "href"}) for item in playlists
            ],
            "my_current_weather": weather.model_dump() if weather else None,
            "my_current_location": location.model_dump(exclude={"lat", "lon"})
            if location
            else None,
        }

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
        tools = self.registry.to_openai_tools()
        context = self.build_context(weather_connector=weather_connector, city=city)
        try:
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=self.prompt_generator.build_playlist_messages(
                    user_prompt, context
                ),
                tools=tools,
                temperature=0.7,
            )
            message = response.choices[0].message
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    return self.call_function(tool_call)
        except Exception as e:
            return {}, e.message
