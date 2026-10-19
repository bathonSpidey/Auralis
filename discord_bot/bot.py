"""The Auralis Discord bot: slash commands and a daily song, for one person.

It runs inside the web process (one resident Python process on the Pi) and
shares its job queue, so a Discord request waits its turn behind a web one.
Commands are slash-only and the bot asks for no privileged intents, so it
cannot read ordinary messages. Everything is limited to one user in one server.
"""

import asyncio
import contextlib
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import time as clock_time
from typing import Literal, Optional

import discord
from discord import app_commands

from agent.auralis import CURRENT_DEVICE
from discord_bot import format as say
from web.jobs import DONE, FAILED, QueueFull

logger = logging.getLogger(__name__)

SOURCE = "discord"
DIGEST_SOURCE = "digest"
POLL_SECONDS = 3
# A slash command can edit its reply for 15 minutes; stop a little before.
MAX_WAIT_SECONDS = 14 * 60


@dataclass
class Settings:
    token: str
    guild_id: int
    user_id: int
    channel_id: Optional[int] = None
    digest_time: Optional[clock_time] = None

    @classmethod
    def from_env(cls) -> Optional["Settings"]:
        """None unless the bot is fully configured: it fails closed, never
        starting without knowing whose commands to obey."""
        token, guild, user = (
            os.getenv("DISCORD_BOT_TOKEN"),
            os.getenv("DISCORD_GUILD_ID"),
            os.getenv("DISCORD_USER_ID"),
        )
        if not (token and guild and user):
            return None
        channel = os.getenv("DISCORD_CHANNEL_ID")
        return cls(
            token=token,
            guild_id=int(guild),
            user_id=int(user),
            channel_id=int(channel) if channel else None,
            digest_time=parse_time(os.getenv("AURALIS_DIGEST_TIME", "08:30")),
        )


def parse_time(text: str) -> Optional[clock_time]:
    """'08:30' -> 08:30; empty or 'off' turns the daily song off."""
    text = (text or "").strip().lower()
    if text in ("", "off", "no", "false"):
        return None
    hour, minute = text.split(":")
    return clock_time(int(hour), int(minute))


def seconds_until(at: clock_time, now: Optional[datetime] = None) -> float:
    """Seconds to the next occurrence of `at` on the machine's local clock."""
    now = now or datetime.now()
    target = datetime.combine(now.date(), at)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


class RateButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"auralis:rate:(?P<id>\d+):(?P<rating>like|dislike)",
):
    """A like/dislike under a suggestion. The id is in the button itself, so
    it keeps working after a restart."""

    def __init__(self, suggestion_id: int, rating: str):
        like = rating == "like"
        super().__init__(
            discord.ui.Button(
                label="Like" if like else "Less like this",
                emoji="👍" if like else "👎",
                style=discord.ButtonStyle.success
                if like
                else discord.ButtonStyle.secondary,
                custom_id=f"auralis:rate:{suggestion_id}:{rating}",
            )
        )
        self.suggestion_id, self.rating = suggestion_id, rating

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]), match["rating"])

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        if not bot.allowed(interaction):
            await bot.refuse(interaction)
            return
        uris = bot.store.track_uris(self.suggestion_id)
        for uri in uris[:1]:  # a song has exactly one track
            bot.store.rate_track(self.suggestion_id, uri, self.rating)
        said = (
            "Liked. I'll lean toward songs like this."
            if self.rating == "like"
            else "Noted. I'll steer away from songs like this, not forever."
        )
        await interaction.response.send_message(said, ephemeral=True)


def rating_view(suggestion_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(RateButton(suggestion_id, "like"))
    view.add_item(RateButton(suggestion_id, "dislike"))
    return view


class AuralisBot(discord.Client):
    def __init__(self, settings: Settings, queue, store):
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.queue = queue
        self.store = store
        self.tree = app_commands.CommandTree(self)
        self._digest: Optional[asyncio.Task] = None
        self._register()

    # ── lifecycle ───────────────────────────────────────────────────────
    async def setup_hook(self):
        self.add_dynamic_items(RateButton)
        guild = discord.Object(id=self.settings.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        if self.settings.digest_time and self.settings.channel_id:
            self._digest = asyncio.create_task(self._digest_loop())

    async def close(self):
        if self._digest:
            self._digest.cancel()
        await super().close()

    async def on_ready(self):
        logger.info("Discord bot ready as %s", self.user)

    # ── access ──────────────────────────────────────────────────────────
    def allowed(self, interaction: discord.Interaction) -> bool:
        return (
            interaction.user.id == self.settings.user_id
            and interaction.guild_id == self.settings.guild_id
        )

    async def refuse(self, interaction: discord.Interaction):
        logger.warning("Refused Discord interaction from user %s", interaction.user.id)
        await interaction.response.send_message(
            "Auralis only answers its owner.", ephemeral=True
        )

    # ── commands ────────────────────────────────────────────────────────
    def _register(self):
        @self.tree.command(name="song", description="One new song for right now")
        @app_commands.describe(
            web="Look on the web too (slower)", play="Play it on my current device"
        )
        async def song(
            interaction: discord.Interaction, web: bool = False, play: bool = False
        ):
            await self.handle_song(interaction, web, play)

        @self.tree.command(name="playlist", description="Build a playlist")
        @app_commands.describe(
            prompt="The mood, activity or moment",
            depth="How much to research",
            play="Play it on my current device",
        )
        async def playlist(
            interaction: discord.Interaction,
            prompt: app_commands.Range[str, 3, 600],
            depth: Literal["quick", "auto", "deep"] = "auto",
            play: bool = False,
        ):
            await self.handle_playlist(interaction, prompt, depth, play)

        @self.tree.command(name="history", description="What Auralis made recently")
        async def history(
            interaction: discord.Interaction,
            count: app_commands.Range[int, 1, 10] = 5,
        ):
            await self.handle_history(interaction, count)

    async def handle_song(self, interaction, web: bool, play: bool):
        await self._run(
            interaction,
            "Finding your song",
            "song",
            depth="auto" if web else "quick",
            device_id=CURRENT_DEVICE if play else None,
        )

    async def handle_playlist(self, interaction, prompt: str, depth: str, play: bool):
        await self._run(
            interaction,
            f"Building a playlist for “{prompt[:120]}”",
            "playlist",
            prompt=prompt,
            depth=depth,
            device_id=CURRENT_DEVICE if play else None,
        )

    async def handle_history(self, interaction, count: int):
        if not self.allowed(interaction):
            return await self.refuse(interaction)
        items = self.store.history(limit=count)
        await interaction.response.send_message(embed=say.history_embed(items))

    async def _run(self, interaction, what: str, kind: str, **fields):
        if not self.allowed(interaction):
            return await self.refuse(interaction)
        await interaction.response.defer(thinking=True)
        try:
            job = self.queue.submit(kind, source=SOURCE, **fields)
        except QueueFull as e:
            await interaction.edit_original_response(embed=say.failure_embed(str(e)))
            return

        async def show(snapshot):
            await interaction.edit_original_response(
                content=say.working(snapshot, what)
            )

        snapshot = await self._wait(job.id, show)
        await interaction.edit_original_response(
            content=None, **self._result(kind, snapshot)
        )

    # ── results ─────────────────────────────────────────────────────────
    @staticmethod
    def _result(kind: str, snapshot: dict) -> dict:
        """Keyword arguments for sending or editing the finished message."""
        if snapshot["status"] != DONE:
            message = snapshot.get("error") or "The run took too long; try again."
            return {"embed": say.failure_embed(message), "view": None}
        outcome = snapshot["result"]["outcome"]
        if kind == "song":
            view = rating_view(outcome["id"]) if outcome.get("id") else None
            return {"embed": say.song_embed(outcome), "view": view}
        return {"embed": say.playlist_embed(outcome), "view": None}

    async def _wait(self, job_id: str, on_change) -> dict:
        """Poll the job until it ends, reporting each change of stage."""
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        shown = None
        while time.monotonic() < deadline:
            snapshot = self.queue.snapshot(job_id)
            if snapshot is None:  # dropped from the queue
                return {"status": FAILED, "error": "The run was cancelled."}
            if snapshot["status"] in (DONE, FAILED):
                return snapshot
            current = snapshot["stage"] or snapshot["status"]
            if current != shown:
                shown = current
                await on_change(snapshot)
            await asyncio.sleep(POLL_SECONDS)
        return {"status": FAILED, "error": None}

    # ── the daily song ──────────────────────────────────────────────────
    async def _digest_loop(self):
        while True:
            await asyncio.sleep(seconds_until(self.settings.digest_time))
            try:
                await self.post_digest()
            except Exception:  # one bad day must not stop the loop
                logger.exception("Daily song failed")

    async def post_digest(self):
        await self.wait_until_ready()
        channel = self.get_channel(
            self.settings.channel_id
        ) or await self.fetch_channel(self.settings.channel_id)
        try:
            job = self.queue.submit("song", source=DIGEST_SOURCE, depth="quick")
        except QueueFull as e:
            await channel.send(embed=say.failure_embed(f"Today's song: {e}"))
            return

        async def ignore(snapshot):
            return None

        snapshot = await self._wait(job.id, ignore)
        result = self._result("song", snapshot)
        if snapshot["status"] == DONE:
            await channel.send("**Today's song**", **_without_none(result))
        else:
            await channel.send(**_without_none(result))


def _without_none(kwargs: dict) -> dict:
    return {k: v for k, v in kwargs.items() if v is not None}


def lifespan_for(bot: AuralisBot):
    """A FastAPI lifespan that runs the bot beside the web server. A bad token
    or no network is logged; it never takes the web page down."""

    async def serve():
        try:
            await bot.start(bot.settings.token)
        except discord.LoginFailure:
            logger.error("Discord login failed: check DISCORD_BOT_TOKEN")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("The Discord bot stopped")

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(serve())
        try:
            yield
        finally:
            await bot.close()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    return lifespan
