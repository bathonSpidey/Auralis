import json


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self.body = body
        self.headers = headers or {}

    @property
    def content(self):
        return b"" if self.body is None else json.dumps(self.body).encode()

    @property
    def text(self):
        return self.content.decode()

    def json(self):
        if self.body is None:
            raise ValueError("no body")
        return self.body


class FakeSession:
    """Routes (METHOD, path) to a response, a list of responses (consumed in
    order, last one repeats) or a callable(params, json) -> response."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        path = url.replace("https://api.spotify.com/v1", "")
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json": json,
                "headers": headers,
            }
        )
        route = self.routes.get((method, path))
        if route is None:
            return FakeResponse(404, {"error": {"status": 404, "message": "no route"}})
        if callable(route):
            return route(params, json)
        if isinstance(route, list):
            return route.pop(0) if len(route) > 1 else route[0]
        return route

    def paths(self, method=None):
        return [c["path"] for c in self.calls if method in (None, c["method"])]


class StubAuth:
    def __init__(self):
        self.refreshes = 0

    def access_token(self, force_refresh=False):
        if force_refresh:
            self.refreshes += 1
        return "fresh-token" if self.refreshes else "token"


def track(track_id, name, artist="Artist"):
    return {
        "id": track_id,
        "uri": f"spotify:track:{track_id}",
        "type": "track",
        "name": name,
        "artists": [{"name": artist, "uri": f"spotify:artist:{artist}"}],
    }
