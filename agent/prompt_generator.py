import json
from typing import List


class PromptGenerator:
    def __init__(self):
        self.one_song_system_prompt = (
            "You are a Spotify song recommender. Given the user's context, suggest a single song "
            "that best matches the mood, genre, and overall vibe. "
            "Rules:\n"
            "- NEVER suggest a song that appears in the 'already_suggested' list — this is a hard rule.\n"
            "- Do NOT directly copy or suggest songs from the user's recently_played_songs or currently_playing\n"
            "- Read the pattern of what he/she has been listening to, but suggest something that is a meaningful departure from that pattern, to help them discover new music.\n"
            "- You may include at  one song from their known favorites, only if it strongly fits.\n"
            "- Explore diverse artists from different countries and regions to help the user discover new music.\n"
            "- Consider current_trending_songs_in_the_world as a source of fresh discovery, but only if they fit the occasion.\n"
            "- Each suggestion should feel meaningfully different from what was suggested before."
        )
        self.playlist_system_prompt = (
            "You are a Spotify playlist manager. Given the user's prompt, generate a playlist with a fitting name. "
            "Rules:\n"
            "- Focus on the mood, genre, and vibe inferred from the user prompt and context.\n"
            "- You may include up to 4 songs from the user's favorites or recently played, only if they are a strong fit.\n"
            "- Ensure the playlist is long enough for a satisfying listening session and also occasions where the user wants to explore something new.\n"
            "- Incorporate variety — different countries, regions, eras, and sub-genres.\n"
        )

    def build_suggest_song_messages(
        self, user_prompt: dict, already_suggested: List[str] = None
    ):
        already_suggested = already_suggested or []

        # Build a hard exclusion block so the model cannot ignore it
        if already_suggested:
            exclusion_block = (
                "\n\n⛔ ALREADY SUGGESTED — DO NOT REPEAT ANY OF THESE:\n"
                + "\n".join(f"  - {s}" for s in already_suggested)
                + "\nYou MUST pick something completely different."
            )
        else:
            exclusion_block = ""

        return [
            {"role": "system", "content": self.one_song_system_prompt},
            {
                "role": "user",
                "content": (
                    f"Suggest a song based on my context: {json.dumps(user_prompt)}"
                    f"{exclusion_block}"
                ),
            },
        ]

    def build_playlist_messages(self, user_prompt: str, context: dict):
        return [
            {"role": "system", "content": self.playlist_system_prompt},
            {
                "role": "user",
                "content": (
                    f"{user_prompt}. "
                    f"A bit about myself: {json.dumps(context) if context else ''}"
                ),
            },
        ]
