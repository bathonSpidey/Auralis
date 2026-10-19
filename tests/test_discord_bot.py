import asyncio
from datetime import datetime
from datetime import time as clock_time
from types import SimpleNamespace

import pytest

from discord_bot import bot as bot_module
from discord_bot import format as say
from discord_bot.bot import AuralisBot, Settings, parse_time, seconds_until
from web.jobs import JobQueue

OWNER, GUILD, CHANNEL = 111, 222, 333

SONG = {
    "id": 7,
    "track": {
        "uri": "spotify:track:abc",
        "title": "Slow Burn",
        "artist": "Someone",
        "album": "Night Album",
        "year": "2021",
    },
    "reason": "Warm and unhurried.",
    "playback": "none",
    "dry_run": False,
}
PLAYLIST = {
    "id": 8,
    "name": "Slow Sunday Pour",
    "reason": "Gentle morning.",
    "research": "",
    "playlist_url": "https://open.spotify.com/playlist/xyz",
    "tracks": [
        {"uri": f"spotify:track:{n}", "title": f"Song {n}", "artist": f"Band {n}"}
        for n in range(1, 10)
    ],
    "playback": "playing",
    "dry_run": False,
}


class FakeInteraction:
    def __init__(self, user=OWNER, guild=GUILD, bot=None):
        self.user = SimpleNamespace(id=user)
        self.guild_id = guild
        self.client = bot
        self.sent, self.edits, self.deferred = [], [], False
        self.response = SimpleNamespace(
            defer=self._defer, send_message=self._send_message
        )

    async def _defer(self, **kwargs):
        self.deferred = True

    async def _send_message(self, content=None, **kwargs):
        self.sent.append({"content": content, **kwargs})

    async def edit_original_response(self, **kwargs):
        self.edits.append(kwargs)


class FakeStore:
    def __init__(self, history=()):
        self._history = list(history)
        self.rated = []

    def history(self, limit=50, offset=0):
        return self._history[:limit]

    def track_uris(self, suggestion_id):
        return ["spotify:track:abc"]

    def rate_track(self, suggestion_id, uri, rating):
        self.rated.append((suggestion_id, uri, rating))


def make_bot(runner, store=None, **settings):
    queue = JobQueue(runner, autostart=False)
    config = Settings(token="t", guild_id=GUILD, user_id=OWNER, **settings)
    return AuralisBot(config, queue, store or FakeStore()), queue


def drive(bot, queue, coro):
    """Run a command while a stand-in worker finishes the queued job."""

    async def main():
        task = asyncio.create_task(coro)
        for _ in range(50):
            await asyncio.sleep(0)
            if queue.run_pending():
                break
        await task

    asyncio.run(main())


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(bot_module, "POLL_SECONDS", 0)


class TestSettings:
    def test_needs_token_guild_and_user(self, monkeypatch):
        for name in ("DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID", "DISCORD_USER_ID"):
            monkeypatch.delenv(name, raising=False)
        assert Settings.from_env() is None
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
        monkeypatch.setenv("DISCORD_GUILD_ID", "1")
        assert Settings.from_env() is None  # still no user id: fail closed

    def test_reads_everything_when_configured(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
        monkeypatch.setenv("DISCORD_GUILD_ID", "1")
        monkeypatch.setenv("DISCORD_USER_ID", "2")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "3")
        monkeypatch.setenv("AURALIS_DIGEST_TIME", "07:45")
        s = Settings.from_env()
        assert (s.guild_id, s.user_id, s.channel_id) == (1, 2, 3)
        assert s.digest_time == clock_time(7, 45)

    def test_the_daily_song_can_be_turned_off(self):
        assert parse_time("off") is None and parse_time("") is None


class TestDigestTiming:
    def test_later_today(self):
        now = datetime(2026, 10, 19, 7, 0)
        assert seconds_until(clock_time(8, 30), now) == 90 * 60

    def test_already_passed_means_tomorrow(self):
        now = datetime(2026, 10, 19, 9, 0)
        assert seconds_until(clock_time(8, 30), now) == 23.5 * 3600


class TestAccess:
    def test_only_the_owner_in_the_server(self):
        bot, _ = make_bot(lambda job, progress: {})
        assert bot.allowed(FakeInteraction())
        assert not bot.allowed(FakeInteraction(user=999))
        assert not bot.allowed(FakeInteraction(guild=999))

    def test_a_stranger_cannot_start_a_run(self):
        bot, queue = make_bot(lambda job, progress: {})
        stranger = FakeInteraction(user=999)
        asyncio.run(bot.handle_song(stranger, False, False))
        assert queue.recent() == []
        assert "only answers its owner" in stranger.sent[0]["content"]

    def test_a_stranger_cannot_read_the_history(self):
        bot, _ = make_bot(lambda job, progress: {})
        stranger = FakeInteraction(user=999)
        asyncio.run(bot.handle_history(stranger, 5))
        assert "embed" not in stranger.sent[0]


class TestCommands:
    def test_song_runs_through_the_shared_queue_and_shows_the_result(self):
        seen = []

        def runner(job, progress):
            seen.append(job)
            progress("pick")
            return {"kind": "song", "outcome": SONG}

        bot, queue = make_bot(runner)
        interaction = FakeInteraction(bot=bot)
        drive(bot, queue, bot.handle_song(interaction, web=False, play=True))
        job = seen[0]
        assert (job.kind, job.source, job.depth) == ("song", "discord", "quick")
        assert job.device_id == "current" and job.preview is False
        final = interaction.edits[-1]
        assert final["embed"].title == "Slow Burn · Someone"
        assert final["view"] is not None  # like / dislike buttons

    def test_web_flag_deepens_the_song_search(self):
        seen = []

        def runner(job, progress):
            seen.append(job)
            return {"kind": "song", "outcome": SONG}

        bot, queue = make_bot(runner)
        drive(bot, queue, bot.handle_song(FakeInteraction(bot=bot), True, False))
        assert seen[0].depth == "auto" and seen[0].device_id is None

    def test_playlist_is_created_for_real_with_the_prompt_and_depth(self):
        seen = []

        def runner(job, progress):
            seen.append(job)
            return {"kind": "playlist", "outcome": PLAYLIST}

        bot, queue = make_bot(runner)
        interaction = FakeInteraction(bot=bot)
        drive(
            bot, queue, bot.handle_playlist(interaction, "rainy focus", "deep", False)
        )
        assert (seen[0].prompt, seen[0].depth) == ("rainy focus", "deep")
        assert seen[0].preview is False
        embed = interaction.edits[-1]["embed"]
        assert embed.title == "Slow Sunday Pour"
        assert "9. Song 9 · Band 9" in embed.fields[0].value

    def test_a_failed_run_says_why(self):
        def runner(job, progress):
            raise RuntimeError("Spotify said no")

        bot, queue = make_bot(runner)
        interaction = FakeInteraction(bot=bot)
        drive(bot, queue, bot.handle_song(interaction, False, False))
        assert interaction.edits[-1]["embed"].description == "Spotify said no"

    def test_progress_is_shown_while_working(self):
        def runner(job, progress):
            progress("scout")
            return {"kind": "song", "outcome": SONG}

        bot, queue = make_bot(runner)
        interaction = FakeInteraction(bot=bot)
        drive(bot, queue, bot.handle_song(interaction, False, False))
        assert interaction.deferred
        assert "Finding your song" in interaction.edits[0]["content"]

    def test_a_full_queue_is_reported_not_raised(self):
        bot, queue = make_bot(lambda job, progress: {})
        for _ in range(queue.max_queued):
            queue.submit("song")
        interaction = FakeInteraction(bot=bot)
        asyncio.run(bot.handle_song(interaction, False, False))
        assert "queue is full" in interaction.edits[-1]["embed"].description

    def test_history_lists_recent_suggestions(self):
        store = FakeStore(
            [
                {
                    "kind": "song",
                    "reason": "Because.",
                    "tracks": [{"title": "A", "artist": "B", "rating": "like"}],
                },
                {"kind": "playlist", "name": "Mix", "tracks": [{}, {}]},
            ]
        )
        bot, _ = make_bot(lambda job, progress: {}, store=store)
        interaction = FakeInteraction(bot=bot)
        asyncio.run(bot.handle_history(interaction, 5))
        fields = interaction.sent[0]["embed"].fields
        assert fields[0].name == "A · B" and fields[0].value.startswith("👍")
        assert fields[1].name == "Mix" and "2 songs" in fields[1].value


class TestRating:
    def test_a_button_press_rates_the_song_for_the_owner_only(self):
        bot, _ = make_bot(lambda job, progress: {})
        button = bot_module.RateButton(7, "dislike")
        owner = FakeInteraction(bot=bot)
        asyncio.run(button.callback(owner))
        assert bot.store.rated == [(7, "spotify:track:abc", "dislike")]
        assert "not forever" in owner.sent[0]["content"]

        stranger = FakeInteraction(user=999, bot=bot)
        asyncio.run(button.callback(stranger))
        assert len(bot.store.rated) == 1

    def test_the_button_id_survives_a_restart(self):
        button = bot_module.RateButton(42, "like")
        assert button.item.custom_id == "auralis:rate:42:like"
        match = bot_module.RateButton.__discord_ui_compiled_template__.fullmatch(
            "auralis:rate:42:like"
        )
        assert match["id"] == "42" and match["rating"] == "like"


class TestFormat:
    def test_spotify_uri_becomes_a_link(self):
        assert (
            say.track_url("spotify:track:abc") == "https://open.spotify.com/track/abc"
        )
        assert say.track_url("nonsense") is None

    def test_a_long_track_list_stays_inside_the_field_limit(self):
        tracks = [
            {"uri": "u", "title": f"A long song title number {n}", "artist": "X" * 30}
            for n in range(60)
        ]
        text = say._numbered(tracks)
        assert len(text) <= 1024 and "more" in text.splitlines()[-1]

    def test_playback_is_told_in_the_footer(self):
        assert say.song_embed(SONG).footer.text == "Not playing; find it in Spotify"
