
import dotenv
import os

from src.SpotifyApiConnector import SpotifyApiConnector

dotenv.load_dotenv()

class TestSpotifyApi():
    
    connector = SpotifyApiConnector()
    client = connector.connect(client_id = os.getenv('SPOTIPY_CLIENT_ID') , client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'))
    playlis_id = '10jvPmRLMzbZlE7MwLSU5M'
    song_uri = 'spotify:track:5zheSFviZNgeZLvZCOxQnE'
    
    def test_connection(self):
        assert self.client != None
        
    def test_get_user_info(self):
        me = self.connector.get_user_info(self.client)
        assert "@" in me["email"]
        
    def test_get_user_playlists(self):
        playlists = self.connector.get_user_playlists(self.client)
        print(playlists)
        assert len(playlists) >= 50
        assert playlists[1].name == "NewHome"
        
    def test_get_songs_from_playlist(self):
        songs = self.connector.get_songs_from_playlist(self.client, self.playlis_id)
        assert len(songs) > 50
        
    def test_search_for_songs(self):
        search = self.connector.search_for_song(query='Imagine Dragons Demons',client=self.client)
        assert "demons" in search[0].name.lower()
        
    def test_get_all_active_devices(self):
        devices = self.connector.get_all_active_devices(self.client)
        assert len(devices) > 2
        
    def test_create_playlist(self):
        self.connector.create_playlist(self.client, 'test playlist')
        playlists = self.connector.get_user_playlists(self.client)
        assert 'test playlist' in [playlist.name for playlist in playlists]
        
    def test_add_songs_to_playlist(self):
        palaylist = self.connector.get_playlist(self.client, 'test playlist')
        songs = ["Imagine Dragon Demons", "Coldplay Yellow", "Lana del Rey Summertime Sadness"]
        songs = [self.connector.search_for_song(query=song, client=self.client)[0] for song in songs]
        self.connector.add_songs_to_playlist(self.client, palaylist.id, songs)
        assert 'test playlist' in [playlist.name for playlist in self.connector.get_user_playlists(self.client)]
        
    def test_recently_played(self):
        recently_played = self.connector.recently_played(self.client)
        print(recently_played)
        assert len(recently_played) > 0
        
        
    
        
    