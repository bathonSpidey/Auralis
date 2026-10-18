from requests.exceptions import ConnectionError

from src import lastfm_api_connector
from src.lastfm_api_connector import LastFmConnector


class FakeResponse:
    def __init__(self, tracks):
        self.tracks = tracks

    def raise_for_status(self):
        pass

    def json(self):
        return {"tracks": {"track": self.tracks}}


def lastfm_track(index):
    return {"name": f"Song {index}", "artist": {"name": f"Artist {index}"}}


class TestLastfmConnector:
    def test_returns_at_most_twenty_top_songs(self, monkeypatch):
        tracks = [lastfm_track(i) for i in range(50)]
        monkeypatch.setattr(
            lastfm_api_connector.requests, "get", lambda *a, **k: FakeResponse(tracks)
        )
        top_songs = LastFmConnector("key").get_top_songs()
        assert len(top_songs) == 20
        assert top_songs[0].name == "Song 0"
        assert top_songs[0].artist_name == "Artist 0"

    def test_network_failure_returns_a_placeholder(self, monkeypatch):
        def fail(*args, **kwargs):
            raise ConnectionError()

        monkeypatch.setattr(lastfm_api_connector.requests, "get", fail)
        [placeholder] = LastFmConnector("key").get_top_songs()
        assert placeholder.name == "Could not be found"
