import pytest
import dotenv
import os
from src.spotify_api_connector import SpotifyApiConnector


dotenv.load_dotenv()


class TestSpotifyApi:
    connector = SpotifyApiConnector(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    )
    playlis_id = "10jvPmRLMzbZlE7MwLSU5M"
    song_uri = "spotify:track:5zheSFviZNgeZLvZCOxQnE"

    def test_get_user_info(self):
        me = self.connector.get_user_info()
        assert "@" in me["email"]

    def test_get_user_playlists(self):
        playlists = self.connector.get_user_playlists()
        assert len(playlists) >= 50
        assert playlists[1].name == "NewHome"

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
        print(top_songs)
        assert len(top_songs) > 0

    def test_is_playing(self):
        is_playing = self.connector.is_currently_playing()
        assert is_playing

    @pytest.mark.slow
    def test_play_song(self):
        self.connector.play_song(self.song_uri)

    @pytest.mark.slow
    def test_add_song_to_queue(self):
        self.connector.add_songs_to_queue(self.song_uri)

    @pytest.mark.slow
    def test_create_playlist(self):
        self.connector.create_playlist("test playlist")
        playlists = self.connector.get_user_playlists()
        assert "test playlist" in [playlist.name for playlist in playlists]

    @pytest.mark.slow
    def test_add_songs_to_playlist(self):
        palaylist = self.connector.get_playlist("test playlist")
        songs = [
            "Imagine Dragon Demons",
            "Coldplay Yellow",
            "Lana del Rey Summertime Sadness",
        ]
        songs = [self.connector.search_for_song(query=song)[0] for song in songs]
        self.connector.add_songs_to_playlist(self.client, palaylist.id, songs)
        assert "test playlist" in [
            playlist.name for playlist in self.connector.get_user_playlists(self.client)
        ]
