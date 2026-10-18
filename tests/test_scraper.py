import requests

from src import spotify_scraper
from src.spotify_scraper import SpotifyScraper


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self.body = body

    def json(self):
        if self.body is None:
            raise ValueError("bad json")
        return self.body


CHART = {
    "entries": [
        {"trackMetadata": {"trackName": "Song", "trackUri": "spotify:track:1"}}
    ],
    "highlights": [{"type": "x", "text": "y"}],
}


def scraper_with(monkeypatch, response=None, error=None):
    seen = {}

    def get(url, headers=None, timeout=None):
        seen["headers"] = headers
        if error:
            raise error
        return response

    monkeypatch.setattr(spotify_scraper.requests, "get", get)
    return SpotifyScraper(lambda: "fresh"), seen


def test_returns_the_trending_chart_using_a_fresh_token(monkeypatch):
    scraper, seen = scraper_with(monkeypatch, FakeResponse(200, CHART))
    assert "Song" in scraper.get_trending_songs("de")
    assert seen["headers"]["authorization"] == "Bearer fresh"


def test_a_plain_token_string_still_works():
    assert SpotifyScraper("abc")._token() == "abc"


def test_every_failure_is_just_no_chart(monkeypatch):
    for kwargs in (
        {"response": FakeResponse(404)},
        {"response": FakeResponse(200, None)},
        {"error": requests.ConnectionError()},
        {"error": requests.Timeout()},
    ):
        scraper, _ = scraper_with(monkeypatch, **kwargs)
        assert scraper.get_trending_songs("de") is None
