import pytest
import dotenv
import os
import sys
from src.spotify_api_connector import SpotifyApiConnector


dotenv.load_dotenv()


@pytest.mark.skipif(sys.platform == "unix", reason="windows only")
@pytest.mark.skipif(
    not os.getenv("SPOTIPY_CLIENT_ID"), reason="SPOTIPY_CLIENT_ID not set"
)
@pytest.mark.integration
class TestSpotifyApi:
    connector = SpotifyApiConnector(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        local=True,
    )
    playlis_id = "10jvPmRLMzbZlE7MwLSU5M"
    song_uri = "spotify:track:5zheSFviZNgeZLvZCOxQnE"

    def test_get_user_info(self):
        me = self.connector.get_user_info()
        assert "@" in me["email"]

    def test_get_auth_url(self):
        auth_url = self.connector.get_auth_url()
        assert "code" in auth_url

    def test_get_user_playlists(self):
        playlists = self.connector.get_user_playlists()
        assert len(playlists) >= 50

    def test_get_songs_from_playlist(self):
        songs = self.connector.get_songs_from_playlist(self.playlis_id)
        assert len(songs) > 25

    def test_search_for_songs(self):
        search = self.connector.search_for_song(query="Imagine Dragons Demons")
        assert "demons" in search[0].name.lower()

    def test_get_all_active_devices(self):
        devices = self.connector.get_all_user_devices()
        assert len(devices) > 2

    def test_recently_played(self):
        recently_played = self.connector.recently_played()
        assert len(recently_played) > 0

    def test_get_top_tracks(self):
        top_songs = self.connector.users_top_tracks()
        assert len(top_songs) > 0

    def test_is_playing(self):
        is_playing = self.connector.is_currently_playing()
        assert is_playing or not is_playing
