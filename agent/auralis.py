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
        time_of_day = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening" if hour < 22 else "night"
        season = "spring" if month in [3, 4, 5] else "summer" if month in [
            6, 7, 8] else "autumn" if month in [9, 10, 11] else "winter"
        recent_songs = self.spotify_connector.recently_played()
        top_songs = self.spotify_connector.users_top_tracks()
        return {"time_of_day": time_of_day, "season": season, "recently_played_songs": [item.model_dump(exclude={"id", "uri"}) for item in recent_songs[:10]], "my_current_top_songs": [item.model_dump(exclude={"id", "uri"}) for item in top_songs], "my_current_weather": weather_connector.get_weather() if weather_connector else None}

    def song_of_the_moment_suggestion(self):
        context = self.build_context()
        system_prompt = "You are a spotify music reccomdation AI. Given the user context, find a song best based on the user context and play a fitting song in spotify. You do not have to necessarilly use the top songs of the user. You can also suggest a song that is not in the top 10 of the user but fits the context."
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
                {"role": "user", "content": json.dumps(user_prompt)},
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
                    print("Suggested by agent:", args)
                    search_query = f"{args['song_title']} {args['artist_name']}"
                    song = self.spotify_connector.search_for_song(search_query)[0]
                    if self.spotify_connector.is_currently_playing():
                        self.spotify.add_songs_to_queue(song.uri)
                    else:
                        self.spotify_connector.play_song(song.uri)
                    return song
                elif tool_call.function.name == "play_song":
                    if song:
                        self.spotify_connector.play_song(song.uri)
                    return song
        else:
            print("No valid suggestion.")
            return None
