import spotipy
import random
from spotipy.oauth2 import SpotifyOAuth
from src.models.playlist import Playlist
from src.models.song import Song
from src.models.device import Device


class SpotifyApiConnector():

    def __init__(self, client_id, client_secret):
        self.redirect_uri = 'http://localhost:8888/callback'
        self.scope = "user-read-private", "user-read-email", "playlist-modify-private", "playlist-read-private",\
                "playlist-modify-public", "user-read-currently-playing",\
                "user-modify-playback-state", "user-read-playback-state","user-read-recently-played", "user-top-read"
        self.client = self.connect(client_id, client_secret)
        
    supported_countries = ['US', "IN", "GB", "KR","DE", "FR", "JP", "CA", "AU", "BR" ]

    def connect(self, client_id, client_secret):
        return spotipy.Spotify(auth_manager=SpotifyOAuth(client_id, client_secret, redirect_uri=self.redirect_uri, scope=self.scope))

    def get_user_info(self):
        return self.client.me()

    def get_user_playlists(self):
        playlists = self.client.current_user_playlists()["items"]
        return [Playlist(**playlist) for playlist in playlists]
    
    def get_songs_from_playlist(self, playlist_id):
        songs = self.client.playlist_tracks(playlist_id)["items"]
        return [Song(**song["track"]) for song in songs]
    
    def search_for_song(self, query):
        songs =  self.client.search(q=query, type='track')['tracks']['items']
        return [Song(**song) for song in songs]
    
    def get_all_active_devices(self):
        devices = self.client.devices()
        return [Device(**device) for device in devices["devices"]]
    
    def create_playlist(self, playlist_name):
        self.client.user_playlist_create(user=self.get_user_info()["id"], name=playlist_name)
    
    def get_playlist(self, playlist_name):
        playlists = self.get_user_playlists(self.client)
        try:
            playlist = [playlist for playlist in playlists if playlist.name == playlist_name][0]
        except IndexError:
            self.create_playlist(self.client, playlist_name)
            playlists = self.get_user_playlists(self.client)
            playlist = [playlist for playlist in playlists if playlist.name == playlist_name][0]
        return playlist
    
    def add_songs_to_playlist(self, client, playlist_id, songs):
        existing_songs = self.get_songs_from_playlist(self.client, playlist_id)
        existing_songs = [song.name for song in existing_songs]
        for song in songs:
            if song.name not in existing_songs:
                client.playlist_add_items(playlist_id, [song.uri])
                
    def recently_played(self):
        recently_played = self.client.current_user_recently_played()["items"]
        return [Song(**song["track"]) for song in recently_played]
    
    def play_song(self, uri, device_id=None):
        self.client.start_playback(uris=[uri])
        
    def users_top_tracks(self):
        songs = self.client.current_user_top_tracks()
        return [Song(**song) for song in songs["items"]]
    
    def add_songs_to_queue(self, uri, device_id=None):
        return self.client.add_to_queue(uri, device_id)
    
    def is_currently_playing(self):
        state = self.client.currently_playing()
        return state["is_playing"]