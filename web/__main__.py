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


def attach_discord(app, store) -> None:
    """Run the Discord bot inside this process when it is configured, so one
    Python process serves both the page and the bot."""
    from discord_bot.bot import AuralisBot, Settings, lifespan_for

    settings = Settings.from_env()
    if settings is None:
        return
    bot = AuralisBot(settings, app.state.queue, store)
    app.router.lifespan_context = lifespan_for(bot)


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
    if not args.demo:
        attach_discord(app, store)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
