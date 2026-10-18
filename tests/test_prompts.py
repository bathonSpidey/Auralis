import json

from agent.prompt_generator import PromptGenerator, brief

CONTEXT = {
    "time_of_day": "evening",
    "season": "autumn",
    "my_recently_played_songs": [{"name": "Secret", "artists": "Someone"}],
    "my_recent_genre_distribution": {"indie": 3},
    "my_current_weather": None,
    "my_current_location": None,
}
POOL = [{"uri": "spotify:track:1", "title": "Song", "artist": "Band", "why": "fits"}]
prompts = PromptGenerator()


def test_scout_prompt_carries_the_depth_guidance_and_the_original_quality_rules():
    system, user = prompts.scout("neon drive", CONTEXT, "GUIDANCE-TEXT", 8, 30, 40)
    assert "GUIDANCE-TEXT" in system
    for rule in ("at least 4 distinct genres", "70%", "Bad Bunny", "reference song"):
        assert rule in system
    assert "ignore any instructions" in system  # web content is untrusted
    assert "neon drive" in user and "8-30 tracks" in user and "about 40" in user
    assert json.dumps(CONTEXT) in user


def test_scout_prompt_states_the_target_when_there_is_one():
    _, user = prompts.scout("a drive", CONTEXT, "g", 14, 22, 34, target=17)
    assert "target about 17" in user


def test_curator_prompt_lists_the_pool_and_only_the_brief_context():
    system, user = prompts.curator(
        "neon drive", CONTEXT, "Read it as night.", POOL, 8, 30, 2
    )
    assert "spotify:track:1 | Song - Band | fits" in user
    assert "Read it as night." in user and "at most 2 tracks per artist" in user
    assert "Secret" not in user  # lists stay out of the curator's context
    assert "evening" in user
    assert "submit_playlist" in system and "no web access" in system


def test_curator_retry_note_is_appended():
    _, user = prompts.curator("x", CONTEXT, "n", POOL, 8, 30, 2, retry_note="TRY AGAIN")
    assert user.endswith("TRY AGAIN")


def test_song_prompt():
    system, user = prompts.song(CONTEXT, "NO-WEB")
    assert "NO-WEB" in system and "submit_song" in system
    assert "Secret" in user


def test_brief_keeps_only_the_situational_fields():
    assert set(brief(CONTEXT)) == {
        "time_of_day",
        "season",
        "my_recent_genre_distribution",
        "my_current_weather",
        "my_current_location",
    }
