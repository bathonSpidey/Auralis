"""Thin Spotify Web API client: auth header, 401 refresh, 429/5xx retries,
pagination. Knows nothing about tracks or playlists; see spotify.library."""

import time
from typing import Callable, List, Optional

import requests

from spotify.auth import SpotifyAuth

BASE_URL = "https://api.spotify.com/v1"
_RETRYABLE = (429, 502, 503, 504)


class SpotifyError(RuntimeError):
    def __init__(self, status: int, message: str, reason: str = ""):
        super().__init__(
            f"Spotify {status}: {message}" + (f" [{reason}]" if reason else "")
        )
        self.status = status
        self.message = message
        self.reason = reason


class SpotifyClient:
    def __init__(
        self,
        auth: SpotifyAuth,
        session=None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        max_retry_after: float = 60,
        timeout: float = 15,
    ):
        self.auth = auth
        self.session = session or requests.Session()
        self.sleep = sleep
        self.max_retries = max_retries
        self.max_retry_after = max_retry_after
        self.timeout = timeout

    def request(self, method: str, path: str, params=None, json=None):
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        refreshed = False
        retries = 0
        while True:
            token = self.auth.access_token(force_refresh=refreshed)
            response = self.session.request(
                method,
                url,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout,
            )
            status = response.status_code
            if status == 401 and not refreshed:
                refreshed = True
                continue
            refreshed = False
            if status in _RETRYABLE:
                retries += 1
                delay = self._retry_delay(response, retries)
                if retries > self.max_retries or delay > self.max_retry_after:
                    raise self._error(response)
                self.sleep(delay)
                continue
            if status >= 400:
                raise self._error(response)
            if status == 204 or not response.content:
                return None
            return response.json()

    def get(self, path: str, params=None):
        return self.request("GET", path, params=params)

    def post(self, path: str, params=None, json=None):
        return self.request("POST", path, params=params, json=json)

    def put(self, path: str, params=None, json=None):
        return self.request("PUT", path, params=params, json=json)

    def get_all(
        self,
        path: str,
        params: Optional[dict] = None,
        page_size: int = 50,
        max_items: int = 200,
        pick: Callable[[dict], dict] = lambda body: body,
    ) -> List[dict]:
        """Collect `items` across pages. `pick` extracts the paging object
        from the response (e.g. body["tracks"] for search)."""
        items: List[dict] = []
        while len(items) < max_items:
            page_params = {
                **(params or {}),
                "limit": min(page_size, max_items - len(items)),
                "offset": len(items),
            }
            page = pick(self.get(path, page_params) or {})
            batch = page.get("items") or []
            items.extend(batch)
            if not page.get("next") or not batch:
                break
        return items

    @staticmethod
    def _retry_delay(response, retries: int) -> float:
        if response.status_code == 429:
            try:
                return float(response.headers.get("Retry-After", 1)) + 1
            except ValueError:
                return 2.0
        return float(2**retries)

    @staticmethod
    def _error(response) -> SpotifyError:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        error = body.get("error", {})
        if isinstance(error, str):
            error = {"message": error}
        message = error.get("message") or body.get("message") or response.text[:200]
        reason = error.get("reason") or body.get("reason") or ""
        return SpotifyError(response.status_code, str(message), str(reason))
