"""One-time Spotify login: `python -m spotify.login`.

Default: opens your browser and catches the redirect on the loopback address.
`--manual`: prints the URL; open it on any machine, then paste back the URL it
redirects to (the page will fail to load, that is fine). Use that over SSH.
`--check`: verifies the stored login by fetching your profile.
"""

import argparse
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import dotenv

from spotify.auth import (
    DEFAULT_REDIRECT_URI,
    SpotifyAuth,
    SpotifyAuthError,
    TokenStore,
)
from spotify.library import Spotify

_TIMEOUT_SECONDS = 300


def _catch_redirect(redirect_uri: str) -> str:
    target = urlparse(redirect_uri)
    caught = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            caught["url"] = f"{redirect_uri.rstrip('/')}{self.path}"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"Auralis is connected to Spotify. You can close this tab."
            )
            done.set()

        def log_message(self, *args):
            pass

    server = HTTPServer((target.hostname, target.port or 80), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        if not done.wait(_TIMEOUT_SECONDS):
            raise SpotifyAuthError("Timed out waiting for the Spotify redirect")
    finally:
        server.shutdown()
    return caught["url"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Log Auralis in to Spotify")
    parser.add_argument("--manual", action="store_true", help="paste the redirect URL")
    parser.add_argument("--check", action="store_true", help="verify the stored login")
    args = parser.parse_args(argv)

    dotenv.load_dotenv()
    if args.check:
        profile = Spotify.from_env().me()
        print(f"Logged in as {profile.get('display_name') or profile.get('id')}")
        return 0

    client_id = os.getenv("SPOTIFY_CLIENT_ID") or os.getenv("SPOTIPY_CLIENT_ID")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI") or DEFAULT_REDIRECT_URI
    store = TokenStore()
    auth = SpotifyAuth(client_id, redirect_uri, store)
    session = auth.begin_login()
    print(f"Redirect URI (must be registered in the Spotify dashboard): {redirect_uri}")
    if args.manual:
        print(f"\nOpen this URL and approve access:\n\n{session.url}\n")
        response = input("Paste the full URL you were redirected to: ")
    else:
        print("Opening your browser. If it does not open, visit:\n\n" + session.url)
        webbrowser.open(session.url)
        response = _catch_redirect(redirect_uri)
    auth.complete_login(session, response)
    print(f"Saved Spotify login to {store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
