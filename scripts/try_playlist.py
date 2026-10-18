"""Try Auralis from the command line.

    python -m scripts.try_playlist "late-night drive through a neon city"
    python -m scripts.try_playlist --depth deep "80s Japanese city pop and its revival"
    python -m scripts.try_playlist --song

Dry run by default: the full research and every rule check happen, but nothing
is created in Spotify and nothing is played, and it is not added to the history.
Pass --create to make it for real.
"""

import argparse
import logging
import time

import dotenv

from agent.advisor import ClaudeAdvisor
from agent.auralis import Auralis
from agent.depth import Depth
from spotify.library import Spotify
from src.spotify_scraper import SpotifyScraper
from store.history import Store


def build_auralis() -> Auralis:
    spotify = Spotify.from_env()
    scraper = SpotifyScraper(spotify.client.auth.access_token)
    return Auralis(spotify, ClaudeAdvisor(), scraper, store=Store())


def show_tracks(tracks) -> None:
    for number, track in enumerate(tracks, 1):
        year = f" ({track.year})" if track.year else ""
        print(f"  {number:02d}. {track.title} - {track.artist}{year}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Try Auralis")
    parser.add_argument("prompt", nargs="?", help="what the playlist should be")
    parser.add_argument("--song", action="store_true", help="song of the moment")
    parser.add_argument("--depth", choices=[d.value for d in Depth])
    parser.add_argument("--create", action="store_true", help="really create/play")
    args = parser.parse_args(argv)
    if not args.song and not args.prompt:
        parser.error("give a prompt, or use --song")

    dotenv.load_dotenv()
    logging.basicConfig(level=logging.WARNING)
    auralis = build_auralis()
    started = time.time()
    if args.song:
        depth = Depth(args.depth or Depth.QUICK)
        song = auralis.song_of_the_moment_suggestion(
            depth=depth, dry_run=not args.create
        )
        print(f"\nSong of the moment ({depth.value}, {time.time() - started:.0f}s)")
        show_tracks([song.track])
        print(f"\n{song.reason}\nplayback: {song.playback}")
    else:
        depth = Depth(args.depth or Depth.AUTO)
        playlist = auralis.playlist_generator(
            args.prompt, depth=depth, dry_run=not args.create
        )
        print(f"\n{playlist.name} ({depth.value}, {time.time() - started:.0f}s)")
        print(f"research: {playlist.research}\n")
        show_tracks(playlist.tracks)
        print(f"\n{playlist.reason}")
        print(f"url: {playlist.playlist_url}  playback: {playlist.playback}")
    if not args.create:
        print("(dry run: nothing was created or played)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
