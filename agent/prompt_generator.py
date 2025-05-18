import json


class PromptGenerator:
    def __init__(self):
        self.one_song_system_prompt = "You are a Spotify song recommender. Given the user prompt, select a single song that best matches the mood, genre, and overall vibe described. Focus on interpreting the user's preferences from their prompt and context, but do not directly copy songs from the user recently_played_songs and top_tracks. If absolutely necessary for better personalization, you may select one song from the user's known favorites, but only if it strongly fits the situation. Choose songs creatively, considering a variety of artists from different countries and regions where appropriate. Look into the current_trending_songs_in_the_world this might help user discover new music, but make sure that they fit the occasion"
        self.playlist_system_prompt = "You are a Spotify playlist manager. Given the user's prompt, generate a playlist with a fitting name.Focus primarily on the mood, genre preferences, and overall vibe inferred from the user prompt and context — but do not directly copy songs from the user recently_played_songs and top_tracks. If absolutely necessary to enhance personalization, you may include up to 4 songs from either the user's favorites or recently played, but only if they are a strong fit. Ensure the playlist duration is sufficient for a satisfying listening experience. Incorporate a variety of songs from different countries and regions  where appropriate to keep the playlist fresh and diverse. Do not include too many sogs from the same artist."

    def build_suggest_song_messages(self, user_prompt):
        return [
            {"role": "system", "content": self.one_song_system_prompt},
            {
                "role": "user",
                "content": f"Suggest a song based on my context: {json.dumps(user_prompt)}",
            },
        ]

    def build_playlist_messages(self, user_prompt, context):
        return [
            {"role": "system", "content": self.playlist_system_prompt},
            {
                "role": "user",
                "content": f"{user_prompt}. A bit about myself {json.dumps(context) if context else ''}",
            },
        ]
