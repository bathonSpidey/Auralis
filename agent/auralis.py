from openai import OpenAI
import json
from datetime import datetime


class Auralis:

    def __init__(self, spotify_connector, openai_api_key, model="gemini-2.0-flash"):
        self.openai_api_key = openai_api_key
        self.model = model
        self.base_url = self.supported_models[self.model]
        self.openai = OpenAI(api_key=self.openai_api_key,
                             base_url=self.base_url)
        self.spotify_connector = spotify_connector

    supported_models = {"gemini-2.0-flash": "https://generativelanguage.googleapis.com/v1beta/openai/", "gpt-4.1": "https://api.openai.com/v1/",
                        "gpt-4o": "https://api.openai.com/v1/", "o4-mini": "https://api.openai.com/v1/", "local_lm_studio": "localhost:1234/v1"}

    def build_context(self, weather_connector=None):
        hour = datetime.now().hour
        month = datetime.now().month
        weather = weather_connector.get_current_location_weather() if weather_connector else None
        location = weather_connector.get_location() if weather_connector else None
        time_of_day = "morning" if hour < 12 and hour >= 4 else "afternoon" if hour < 18 and hour >= 12 else "evening" if hour < 21 and hour >= 18 else "night" if hour < 23 and hour >= 21 else "late night"
        season = "spring" if month in [3, 4, 5] else "summer" if month in [
            6, 7, 8] else "autumn" if month in [9, 10, 11] else "winter"
        recent_songs = self.spotify_connector.recently_played()
        top_tracks = self.spotify_connector.users_top_tracks()
        return {"time_of_day": time_of_day, "season": season, "recently_played_songs": [item.model_dump(exclude={"id", "uri"}) for item in recent_songs[:20]], "my_top_tracks": [item.model_dump(exclude={"id", "uri"}) for item in top_tracks[:10]], "my_current_weather": weather.model_dump() if weather else None, "my_current_location": location.model_dump(exclude={"lat", "lon"}) if location else None}

    def song_of_the_moment_suggestion(self, weather_connector=None):
        context = self.build_context(weather_connector=weather_connector)
        system_prompt = "You are a spotify music assistant AI. Given the user context, find a song best based on the user context and play a fitting song in spotify. Check the user recent trend in songs. Do not use any song in the users top tracks but use the information along with the other information in the context to suggest a song. You can include country based songs as well. "
        user_prompt = {
            "context": context
        }
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "suggest_song",
                    "description": "Suggest a song based on user context",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "song_title": {"type": "string", "description": "Title of the suggested song"},
                            "artist_name": {"type": "string", "description": "Artist of the suggested song"},
                            "reason": {"type": "string", "description": "Why this song fits the context"}
                        },
                        "required": ["song_title", "artist_name", "reason"]
                    }
                }
            }
        ]

        response = self.openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",
                    "content": f"Suggest a song based on my context: {json.dumps(user_prompt)}"},
            ],
            tools=tools,
            temperature=0.7
        )
        message = response.choices[0].message
        song = None
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "suggest_song":
                    args = json.loads(tool_call.function.arguments)
                    suggested_text = args
                    search_query = f"{args['song_title']} {args['artist_name']}"
                    song = self.spotify_connector.search_for_song(search_query)[
                        0]
                    if self.spotify_connector.is_currently_playing():
                        self.spotify_connector.add_songs_to_queue(song.uri)
                    else:
                        self.spotify_connector.play_song(song.uri)
                    return song, suggested_text, message.content
            print("No valid suggestion.")
            return None
        
    def build_playlist_context(self, weather_connector=None):
        existing_context = self.build_context(weather_connector=weather_connector)
        playlists = self.spotify_connector.get_user_playlists()
        existing_context["existing_playlists"] = [item.model_dump(exclude={"id", "uri", "href"}) for item in playlists]
        return existing_context

    def playlist_generator(self, user_prompt, weather_connector=None):
        context = None
        system_prompt = "You are a spotify playlist manager. Given the user prompt you generate a playlist for the user. You also generate a fitting name for the playlist. Make sure that the playlist is long enough. Use whatever tools that are present at your disposal. You can also refer to the user context if given to get a bit of idea of the user preferences. Do not use any song or playlist name directly from the user context. Try to include a variety of songs from differnet countrie and regions  if it fits in the provided user context."
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "generate_playlist",
                    "description": "Generate a playlist based on user prompt",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "playlist_name": {"type": "string", "description": "Title of the suggested playlist"},
                            "songs": {"type": "array",
                                      "items": 
                                          {
                                              "type": "string",
                                              "description": "Title of the song with artist name"},
                                      "description": "List of songs in the playlist"},
                            "reason": {"type": "string", "description": "Why this playlist fits the context"}
                        },
                        "required": ["playlist_name", "songs", "reason"]
                    }
                }
            }
        ]
        if weather_connector:
            context = self.build_playlist_context(weather_connector=weather_connector)
        response = self.openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_prompt}. A bit about myself {json.dumps(context) if context else ''}"},
            ],
            tools=tools,
            temperature=0.7
        )
        message = response.choices[0].message
        playlist = None
        if message.tool_calls:
            for tool_call in message.tool_calls:
                if tool_call.function.name == "generate_playlist":
                    args = json.loads(tool_call.function.arguments)
                    playlist = args
                    return playlist, message
