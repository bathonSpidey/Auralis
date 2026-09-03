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
            "- Consider current_trending_songs and viral songs as a source of fresh discovery, but only if they fit the occasion.\n"
            "- Each suggestion should feel meaningfully different from what was suggested before."
        )
        self.playlist_system_prompt = (
            "You are a Spotify playlist manager. The user's PRIMARY REQUEST below is the "
            "non-negotiable instruction. The SECONDARY CONTEXT (recently played, top tracks, "
            "weather, time of day, charts) exists only to personalize and to seed discovery — "
            "it must never override, dilute, or redirect what the user explicitly asked for.\n"
            "Rules:\n"
            "- If the user names a reference song or artist, use it only as a mood/energy anchor. "
            "Do not clone its genre across the whole playlist — a single reference track is not a "
            "genre instruction unless the user explicitly asks for 'more songs like this genre'.\n"
            "- Genre variety is mandatory: span at least 4 distinct genres or sub-genres across the "
            "playlist, unless the user explicitly asks for one specific genre only. Never let the "
            "playlist collapse into one monotonous genre or energy level (e.g. all EDM, all one BPM) "
            "even if the seed songs, recent listening habits, or context lean that way.\n"
            "- Use `my_recent_genre_distribution` (genres the user already listens to a lot) as a "
            "signal of what is NOT fresh — deliberately include genres outside that distribution "
            "unless the user's prompt specifically calls for one of those genres.\n"
            "- Discovery is mandatory: at least 70% of the songs must be tracks the user has not "
            "recently played and are not already in their top tracks. You may include up to 4 songs "
            "the user explicitly referenced or that are clear favorites, but the rest must be genuine "
            "discovery — explore diverse artists, countries, regions, eras, and sub-genres.\n"
            "- Size the playlist to the situation: infer any implied duration or session length from "
            "the prompt (a stated trip/workout time, 'quick', 'long', 'party', etc.). If a suggested "
            "song count is given, treat it as a target and only deviate if the vibe clearly calls for "
            "it. Briefly justify the length you chose in `reason`.\n"
            "- Consider trending_charts and viral_charts as your primary discovery pool when they fit "
            "the occasion.\n"
            "- Avoid Bad Bunny songs unless the user explicitly mentions him or his music style, as he "
            "is a very common suggestion that may not always be the best fit for the user's specific "
            "mood or occasion.\n"
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

    def build_playlist_messages(
        self, user_prompt: str, context: dict, target_song_count: int = None
    ):
        length_hint = (
            f"\n\nSuggested playlist length: aim for about {target_song_count} songs "
            "based on the implied duration/occasion above (deviate only if the vibe "
            "clearly calls for it)."
            if target_song_count
            else ""
        )
        return [
            {"role": "system", "content": self.playlist_system_prompt},
            {
                "role": "user",
                "content": (
                    "PRIMARY REQUEST (follow exactly — this is what the user actually "
                    f"asked for):\n{user_prompt}"
                    f"{length_hint}\n\n"
                    "SECONDARY CONTEXT (for personalization and discovery only — never "
                    "let this override the request above):\n"
                    f"{json.dumps(context) if context else '{}'}"
                ),
            },
        ]
