# Auralis

[![Code check](https://github.com/bathonSpidey/Auralis/actions/workflows/code-check.yml/badge.svg)](https://github.com/bathonSpidey/Auralis/actions/workflows/code-check.yml)

Auralis builds songs and playlists for you from your own Spotify taste, the time of day, the season and the weather. Claude does the thinking, Spotify supplies the music, and you reach it from a web page on your home network or from Discord.

It is made to run on a small always-on machine (a Raspberry Pi) and to stay out of its way: one idle Python process, and Claude only starts when you ask for something.

## What it does

- **Playlist.** Describe a moment ("a one-hour focus session, instrumental but not boring") and get a playlist in your Spotify. Mention a length and it fits.
- **Song of the moment.** One new song for right now. With Spotify open it goes straight to your queue; a daily song can be posted to Discord.
- **DJ mode.** Off by default. While music is playing, a fresh song that flows after what you are hearing is added to your queue every 30 minutes (10 to 180, your choice), and Discord is told. Pausing for ten minutes ends the session, and a daily cap keeps it from running away. Switch it on from the page or with `/dj`. It can also be started from outside: `POST /api/dj/now` (for Home Assistant) queues one song when the caller decides it is time, and `PUT /api/home` records readings from the home (room temperature, light, who is in) that shape the mood of every pick. Both take an `X-Auralis-Token` header when `AURALIS_TRIGGER_TOKEN` is set.
- **Knows your taste.** It reads your recent plays, top tracks, playlists and liked songs, and prefers discoveries over what you already know.
- **Knows the moment.** Local time of day, season and current weather go into every request.
- **Research depth.** _Quick_ uses your taste only, _Auto_ searches the web when it needs to, _Deep_ researches properly. Pick it per request.
- **Memory.** Everything it makes is kept in a history. Songs from the last two creations never repeat back to back; older ones may come back.
- **Likes and dislikes.** Rate any song. A like leans toward that sound, a dislike steers away from songs like it (never a ban), and unrated songs are neutral. Change or clear a rating any time.
- **Playback picks the device itself.** If Spotify is open on any device, a song joins its queue and never cuts in on what is playing. If Spotify is off, music starts on your default speaker (`AURALIS_DEFAULT_DEVICE`, matched by name, e.g. an Echo in the office); with no default, or when that speaker is offline, it only saves the song or playlist. A playlist never interrupts music that is playing. The daily song and the DJ only ever join a queue and never start music.

## How it works

```
 web page ─┐                              ┌─ Spotify (read: taste, search)
           ├─> job queue ─> Auralis ──────┤
 Discord ──┘   (one at a time)   │         └─ Spotify (write: one gated tool)
                                 ▼
                      claude -p  (headless, no daemon)
                       1. Scout   web search + read-only Spotify tools
                       2. Curator no web, holds the only write tool
```

Claude runs headless (`claude -p`) with an MCP server that exposes Spotify. The two stages are split on purpose: the agent that reads the web cannot write anything, and the agent that writes cannot read the web, which limits what a poisoned web page could do.

The rules are enforced in code, not in the prompt. The only way to create a playlist is a tool that checks every submission: tracks must have been returned by a real Spotify lookup, no duplicates (across releases of the same song), a sane length, a cap per artist, a limit on already-familiar songs, and nothing from the last two creations. A rejected submission comes back with the reasons so Claude can fix it. Creation is all-or-nothing, and a preview (dry run) runs the identical checks without touching Spotify.

## Using it

**Web page.** Open `http://<host>:8090`. _Create_ makes a playlist or a song, with _Show me before creating_ on by default so you can look first and then create exactly what you saw, with no second round of research. _History_ lists everything made. _Likes & dislikes_ is where you change your mind.

**Discord.** Slash commands, answered only for one user in one server:

| Command                                          | What it does                                                 |
| :----------------------------------------------- | :----------------------------------------------------------- |
| `/song [web]`                                    | One new song, queued if Spotify is open, else played on the default speaker. `web` also searches the web. |
| `/playlist <prompt> [depth]`                     | Builds and creates a playlist.                               |
| `/dj [on/off/status] [minutes]`                  | DJ mode: queue a fresh song every so often while you listen. |
| `/history [count]`                               | The most recent suggestions.                                 |

A song comes with a Spotify card (a short preview) and the buttons **Like**, **Less like this**, **Queue it** (when Spotify was closed) and **Another one**. If `DISCORD_CHANNEL_ID` is set, a song is posted there every day at `AURALIS_DIGEST_TIME` (default 08:30, local time; `off` disables it).

## Setup

You need Python 3.10+, a **Spotify Premium** account with a developer app, and the [Claude Code](https://claude.com/claude-code) CLI logged in on the machine that runs Auralis.

```bash
git clone https://github.com/bathonSpidey/Auralis.git
cd Auralis
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

1. **Spotify app.** Create an app at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and add the redirect URI `http://127.0.0.1:8501`. Auralis uses PKCE, so only the client ID is needed.
2. **Configure.** Create a `.env` (or the systemd environment file):

   ```env
   SPOTIFY_CLIENT_ID=<client id>
   AURALIS_DATA_DIR=~/auralis-data      # optional; database and token live here, outside the repo

   WEATHER=<OpenWeather One Call 3.0 key>   # optional
   AURALIS_CITY=<city>                      # optional; default is guessed from your public IP
   AURALIS_DEFAULT_DEVICE=<speaker name>    # optional; where music starts when Spotify is off

   DISCORD_BOT_TOKEN=<bot token>            # optional: all of these four turn the bot on
   DISCORD_GUILD_ID=<server id>
   DISCORD_USER_ID=<the one user allowed to command it>
   DISCORD_CHANNEL_ID=<channel for the daily song>
   AURALIS_DIGEST_TIME=08:30                # or "off"
   ```

3. **Log in to Spotify once**, on a machine with a browser: `python -m spotify.login` (use `--manual` if the browser is on another machine, `--check` to verify). The token is saved in the data directory and can be copied to the server.
4. **Run:** `python -m web` serves the page on port 8090 (and starts the Discord bot if configured). `python -m web --demo` runs the UI with canned data and needs neither Spotify nor Claude.

The page has no login; it is meant for a trusted home network.

### Discord bot

Create an application at the [Discord Developer Portal](https://discord.com/developers/applications), add a bot, and invite it with the `bot` and `applications.commands` scopes plus _Send Messages_ and _Embed Links_. It needs no privileged intents and never reads ordinary messages.

### Running on a Raspberry Pi

`deploy/auralis.service` is a systemd **user** unit: it runs at lower priority, is first in line to be stopped under memory pressure, and logs to the journal. Copy it to `~/.config/systemd/user/`, adjust the paths, then `systemctl --user enable --now auralis`. With `loginctl enable-linger` it survives logouts and reboots. The service holds about 80 MB; `claude` is not a daemon and exists only while a run is in progress. Logs: `systemctl --user status auralis`.

Auralis keeps its data in `AURALIS_DATA_DIR`: the SQLite history (`auralis.db`), the Spotify token, and short-lived run folders. History is pruned automatically (a year, 500 suggestions); ratings are kept.

## Development

```bash
pip install -r requirements-dev.txt
pytest -q -m "not integration"      # no network, no Spotify, no Claude needed
ruff check . && ruff format --check .
python -m scripts.try_playlist --depth quick "rainy focus"   # a real dry run, creates nothing
```

| Path             | What lives there                                                       |
| :--------------- | :--------------------------------------------------------------------- |
| `agent/`         | The Claude advisor, scout/curator prompts, depth plans, run workspace  |
| `auralis_mcp/`   | The MCP server and the rule-enforcing gate                             |
| `spotify/`       | Spotify client (PKCE auth), library, login helper                      |
| `store/`         | SQLite history, ratings and pruning                                    |
| `web/`           | FastAPI app, job queue and the single-page UI                          |
| `discord_bot/`   | Slash commands, daily song, like/dislike buttons                       |
| `src/`           | Weather (OpenWeather), a fail-soft chart scraper, and a Last.fm connector (not used yet) |

## Services

| Service                | Used for                                          |
| :--------------------- | :------------------------------------------------ |
| Spotify Web API        | Your taste, search, playlists and playback        |
| Claude (Claude Code)   | Research, curation and the final choice           |
| OpenWeather One Call   | Weather for the moment (optional)                 |
| Discord                | Commands and the daily song (optional)            |
