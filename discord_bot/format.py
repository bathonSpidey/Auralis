"""What Auralis says in Discord: plain functions from a finished run to an embed."""

from typing import List, Optional

import discord

ACCENT = 0x1DB954
FAILED = 0xE5484D
FIELD_LIMIT = 1000  # Discord caps an embed field at 1024 characters

STAGES = {
    "queued": "Waiting for the run before this one…",
    "taste": "Reading your taste…",
    "scout": "Researching…",
    "pick": "Choosing…",
    "curate": "Curating…",
    "finish": "Finishing up…",
    "create": "Creating…",
}
PLAYBACK = {
    "playing": "Playing now",
    "queued": "Added to your queue",
    "none": "Not playing; find it in Spotify",
}


QUEUE_REPLY = {
    "queued": "Added to your queue.",
    "none": "Spotify isn't open on any device. Start it and press the button again.",
}


def dj_embed(status: dict) -> discord.Embed:
    state = "On" if status["enabled"] else "Off"
    embed = discord.Embed(title=f"DJ mode · {state}", color=ACCENT)
    embed.description = (
        f"While music is playing, a fresh song joins your queue every "
        f"{status['minutes']} minutes."
        if status["enabled"]
        else "Turn it on and a fresh song joins your queue every so often while "
        "music is playing."
    )
    if status["enabled"]:
        if status["listening"] and status["next_at"]:
            embed.add_field(name="Next song", value=f"<t:{int(status['next_at'])}:R>")
        else:
            embed.add_field(name="Next song", value="Starts when music is playing")
    if status["last"]:
        last = status["last"]
        embed.add_field(
            name="Last added",
            value=f"{last['title']} · {last['artist']} (<t:{int(last['at'])}:R>)",
            inline=False,
        )
    embed.set_footer(
        text=f"{status['added_today']} of {status['max_per_day']} songs added today"
    )
    return embed


def track_url(uri: str) -> Optional[str]:
    parts = uri.split(":")
    if len(parts) == 3 and parts[0] == "spotify":
        return f"https://open.spotify.com/{parts[1]}/{parts[2]}"
    return None


def working(snapshot: dict, what: str) -> str:
    stage = STAGES.get(
        snapshot["stage"] or snapshot["status"], STAGES["queued"]
    )  # a queued job has no stage yet
    return f"{what}\n{stage}"


def song_embed(outcome: dict) -> discord.Embed:
    track = outcome["track"]
    embed = discord.Embed(
        title=f"{track['title']} · {track['artist']}",
        url=track_url(track["uri"]),
        description=outcome["reason"],
        color=ACCENT,
    )
    detail = " · ".join(x for x in (track.get("album"), track.get("year")) if x)
    if detail:
        embed.add_field(name="From", value=detail, inline=False)
    embed.set_footer(text=PLAYBACK[outcome["playback"]])
    return embed


def playlist_embed(outcome: dict) -> discord.Embed:
    embed = discord.Embed(
        title=outcome["name"],
        url=outcome.get("playlist_url"),
        description=outcome["reason"],
        color=ACCENT,
    )
    embed.add_field(name="Tracks", value=_numbered(outcome["tracks"]), inline=False)
    embed.set_footer(
        text=f"{len(outcome['tracks'])} songs · {PLAYBACK[outcome['playback']]}"
    )
    return embed


def _numbered(tracks: List[dict]) -> str:
    lines, used = [], 0
    for n, t in enumerate(tracks, 1):
        line = f"{n}. {t['title']} · {t['artist']}"
        if used + len(line) + 1 > FIELD_LIMIT - 30:  # room for the "and more" line
            lines.append(f"…and {len(tracks) - n + 1} more")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def history_embed(items: List[dict]) -> discord.Embed:
    embed = discord.Embed(title="Recent suggestions", color=ACCENT)
    if not items:
        embed.description = "Nothing yet. Try `/song` or `/playlist`."
        return embed
    for item in items:
        tracks = item["tracks"]
        if item["kind"] == "song" and tracks:
            title = f"{tracks[0]['title']} · {tracks[0]['artist']}"
            body = _rating(tracks[0].get("rating")) + (item.get("reason") or "")
        else:
            title = item.get("name") or "Playlist"
            body = f"{len(tracks)} songs"
            if item.get("playlist_url"):
                body += f" · [open]({item['playlist_url']})"
        embed.add_field(name=title[:250], value=body[:FIELD_LIMIT] or "·", inline=False)
    return embed


def _rating(rating: Optional[str]) -> str:
    return {"like": "👍 ", "dislike": "👎 "}.get(rating or "", "")


def failure_embed(message: str) -> discord.Embed:
    return discord.Embed(
        title="That did not work", description=message[:400], color=FAILED
    )
