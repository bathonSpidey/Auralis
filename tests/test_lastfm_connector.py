import dotenv
import os
from src.lastfm_api_connector import LastFmConnector


dotenv.load_dotenv()


class TestLastfmConnector:
    def test_get_top_artists(self):
        client = LastFmConnector(os.getenv("LASTFM"))
        top_songs = client.get_top_songs()
        assert len(top_songs) == 15
