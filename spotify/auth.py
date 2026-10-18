"""Spotify authorization (PKCE) with a self-refreshing token file.

Only the client ID is needed, so no client secret ever has to live on the
host that runs the service. Log in once with `python -m spotify.login`; after
that the access token is refreshed from the stored refresh token.
"""

import base64
import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import requests

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = (
    "https://accounts.spotify.com/api/token"  # a URL, not a password  # nosec B105
)
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8501"
SCOPES = (
    "playlist-read-private",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-library-read",
    "user-read-recently-played",
    "user-top-read",
    "user-read-playback-state",
    "user-read-currently-playing",
    "user-modify-playback-state",
)


class SpotifyAuthError(RuntimeError):
    pass


def default_token_path() -> Path:
    data_dir = os.getenv("AURALIS_DATA_DIR") or Path.home() / "auralis-data"
    return Path(data_dir) / "spotify_token.json"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@dataclass(frozen=True)
class Token:
    access_token: str
    refresh_token: str
    expires_at: float
    scope: str = ""


@dataclass(frozen=True)
class LoginSession:
    url: str
    verifier: str
    state: str


class TokenStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_token_path()

    def load(self) -> Optional[Token]:
        try:
            return Token(**json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return None
        except (ValueError, TypeError) as e:
            raise SpotifyAuthError(f"Unreadable token file {self.path}: {e}") from e

    def save(self, token: Token) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(asdict(token), f)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


class SpotifyAuth:
    def __init__(
        self,
        client_id: str,
        redirect_uri: str = DEFAULT_REDIRECT_URI,
        store: Optional[TokenStore] = None,
        post: Callable = requests.post,
        clock: Callable[[], float] = time.time,
        expiry_margin: float = 60,
    ):
        if not client_id:
            raise SpotifyAuthError("SPOTIFY_CLIENT_ID is not set")
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.store = store or TokenStore()
        self.post = post
        self.clock = clock
        self.expiry_margin = expiry_margin
        self._lock = threading.Lock()

    def begin_login(self) -> LoginSession:
        verifier = _b64url(secrets.token_bytes(64))
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        state = secrets.token_urlsafe(16)
        query = urlencode(
            {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": self.redirect_uri,
                "scope": " ".join(SCOPES),
                "state": state,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
            }
        )
        return LoginSession(f"{AUTH_URL}?{query}", verifier, state)

    def complete_login(self, session: LoginSession, response: str) -> Token:
        """`response` is the full URL Spotify redirected to, or a bare code."""
        response = response.strip()
        if "code=" in response or "error=" in response:
            query = parse_qs(urlparse(response).query)
            if "error" in query:
                raise SpotifyAuthError(f"Spotify login failed: {query['error'][0]}")
            if query.get("state", [session.state])[0] != session.state:
                raise SpotifyAuthError("Login state mismatch; start the login again")
            code = query["code"][0]
        else:
            code = response
        token = self._to_token(
            self._token_request(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "code_verifier": session.verifier,
                }
            )
        )
        self.store.save(token)
        return token

    def access_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            # Re-read every time: another process may have refreshed already.
            token = self.store.load()
            if token is None:
                raise SpotifyAuthError("Not logged in. Run: python -m spotify.login")
            if force_refresh or token.expires_at - self.expiry_margin <= self.clock():
                token = self._to_token(
                    self._token_request(
                        {
                            "grant_type": "refresh_token",
                            "refresh_token": token.refresh_token,
                            "client_id": self.client_id,
                        }
                    ),
                    previous=token,
                )
                self.store.save(token)
            return token.access_token

    def _token_request(self, data: dict) -> dict:
        response = self.post(TOKEN_URL, data=data, timeout=15)
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code != 200:
            detail = body.get("error_description") or body.get("error") or ""
            hint = (
                " (login expired or revoked; run: python -m spotify.login)"
                if body.get("error") == "invalid_grant"
                else ""
            )
            raise SpotifyAuthError(
                f"Token request failed ({response.status_code}): {detail}{hint}"
            )
        return body

    def _to_token(self, body: dict, previous: Optional[Token] = None) -> Token:
        refresh_token = body.get("refresh_token") or (
            previous.refresh_token if previous else ""
        )
        return Token(
            access_token=body["access_token"],
            refresh_token=refresh_token,
            expires_at=self.clock() + float(body.get("expires_in", 3600)),
            scope=body.get("scope", previous.scope if previous else ""),
        )
