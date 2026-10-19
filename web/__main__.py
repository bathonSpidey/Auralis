"""Run the Auralis web service.

    python -m web            # the real thing (needs a Spotify login and claude)
    python -m web --demo     # the UI with canned data, no Spotify or Claude calls

Binds to the LAN by default so the Pi serves the page to your devices. There is
no login: it is meant for a trusted home network, like the Bart dashboard.
"""

import argparse
import os

import dotenv
import uvicorn

from web.app import create_app


def build_real():
    from agent.advisor import ClaudeAdvisor
    from agent.auralis import Auralis
    from spotify.library import Spotify
    from src.spotify_scraper import SpotifyScraper
    from store.history import Store

    spotify = Spotify.from_env()
    store = Store()
    advisor = ClaudeAdvisor(config_dir=os.getenv("AURALIS_CLAUDE_CONFIG_DIR"))
    scraper = SpotifyScraper(spotify.client.auth.access_token)
    weather = None
    if os.getenv("WEATHER"):  # optional: without a key, only time and season
        from src.weather_api_connector import WeatherApiConnector

        weather = WeatherApiConnector(os.getenv("WEATHER"), os.getenv("AURALIS_CITY"))
    return (
        Auralis(spotify, advisor, scraper, store=store, weather=weather),
        store,
        spotify,
    )


def attach_background(app, auralis, store, spotify) -> None:
    """Run the Discord bot (when configured) and the DJ inside this process, so
    one Python process serves the page, the bot and the auto-queue."""
    from discord_bot.bot import AuralisBot, Settings, lifespan_for
    from web.dj import Dj

    settings = Settings.from_env()
    bot = None
    if settings:
        bot = AuralisBot(settings, app.state.queue, store, auralis=auralis)
    notify = bot.announce_dj if bot and settings.channel_id else None
    dj = Dj(spotify, app.state.queue, store, notify=notify)
    if bot:
        bot.dj = dj
    app.state.dj = dj
    app.router.lifespan_context = lifespan_for(bot, dj)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Auralis web service")
    parser.add_argument("--demo", action="store_true", help="canned data, no services")
    parser.add_argument("--host", default=os.getenv("AURALIS_HOST", "0.0.0.0"))  # nosec B104
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("AURALIS_PORT", "8090"))
    )
    args = parser.parse_args(argv)

    dotenv.load_dotenv()
    if args.demo:
        from web.demo import build_demo

        auralis, store, spotify = build_demo()
    else:
        auralis, store, spotify = build_real()
    app = create_app(auralis, store, spotify)
    if args.demo:  # shown, but never started: nothing watches Spotify
        from web.dj import Dj

        app.state.dj = Dj(spotify, app.state.queue, store)
    else:
        attach_background(app, auralis, store, spotify)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
