import spotipy
from spotipy.oauth2 import SpotifyOAuth
from models.playlist import Playlist
from models.song import Song
from models.device import Device


class SpotifyApiConnector:
    def __init__(self, client_id, client_secret, streamlit_cloud=False):
        """
        Initializes the SpotifyApiConnector with client credentials and sets up the
        redirect URI and scope for Spotify API access.

        Args:
            client_id (str): The client ID for the Spotify application.
            client_secret (str): The client secret for the Spotify application.
        """

        self.redirect_uri = "https://auralis-7hhf8fgymxuwbpzyumhtcq.streamlit.app/"
        self.scope = (
            "user-read-private",
            "user-read-email",
            "playlist-modify-private",
            "playlist-read-private",
            "playlist-modify-public",
            "user-read-currently-playing",
            "user-modify-playback-state",
            "user-read-playback-state",
            "user-read-recently-played",
            "user-top-read",
        )
        self.oaut_manager = SpotifyOAuth(
            client_id,
            client_secret,
            redirect_uri=self.redirect_uri,
            scope=self.scope,
            cache_path=None,
        )
        self.client = None
        # if not streamlit_cloud:
        #     self.client = self.connect()
        # else:
        #     self.client = None

    def get_auth_url(self):
        """
        Generates the authorization URL for the Spotify API.

        Returns:
            str: The authorization URL for the Spotify API.
        """
        return self.oaut_manager.get_authorize_url()

    def get_token_from_code(self, code):
        """
        Exchanges the authorization code for an access token.

        Args:
            code (str): The authorization code received from Spotify.

        Returns:
            str: The access token for the Spotify API.
        """
        return self.oaut_manager.get_access_token(code)

    def get_client(self, token_info):
        self.client = spotipy.Spotify(auth=token_info["access_token"])

    def connect(self):
        """
        Establishes a connection to the Spotify API using the provided client credentials.

        Args:
            client_id (str): The client ID for the Spotify application.
            client_secret (str): The client secret for the Spotify application.

        Returns:
            spotipy.Spotify: An authenticated Spotify client instance.
        """

        return spotipy.Spotify(
            auth_manager=self.oaut_manager,
        )

    def connect_from_streamlit(self, token):
        self.client = spotipy.Spotify(auth=token)

    def get_user_info(self):
        """
        Gets the current user's information from the Spotify API.

        Returns:
            dict: User information from the Spotify API.
        """
        return self.client.me()

    def get_user_playlists(self):
        """
        Gets the current user's playlists from the Spotify API.

        Returns:
            list[Playlist]: A list of Playlist objects representing the current user's playlists.
        """
        playlists = self.client.current_user_playlists()["items"]
        return [Playlist(**playlist) for playlist in playlists]

    def get_songs_from_playlist(self, playlist_id):
        songs = self.client.playlist_tracks(playlist_id)["items"]
        return [Song(**song["track"]) for song in songs]

    def search_for_song(self, query):
        songs = self.client.search(q=query, type="track")["tracks"]["items"]
        return [Song(**song) for song in songs]

    def get_all_user_devices(self):
        devices = self.client.devices()
        return [Device(**device) for device in devices["devices"]]

    def create_playlist(self, playlist_name):
        playlist_name = self.client.user_playlist_create(
            user=self.get_user_info()["id"], name=playlist_name
        )
        return Playlist(**playlist_name)

    def get_playlist(self, playlist_name):
        playlists = self.get_user_playlists(self.client)
        try:
            playlist = [
                playlist for playlist in playlists if playlist.name == playlist_name
            ][0]
        except IndexError:
            self.create_playlist(self.client, playlist_name)
            playlists = self.get_user_playlists(self.client)
            playlist = [
                playlist for playlist in playlists if playlist.name == playlist_name
            ][0]
        return playlist

    def add_songs_to_playlist(self, playlist_id, songs):
        existing_songs = self.get_songs_from_playlist(playlist_id)
        existing_songs = [song.name for song in existing_songs]
        for song in songs:
            if song.name not in existing_songs:
                self.client.playlist_add_items(playlist_id, [song.uri])

    def generate_playlist_from_auralis(self, playlist_name, songs):
        palylist = self.create_playlist(playlist_name)
        songs_in_spotify = [self.search_for_song(song)[0] for song in songs]
        self.add_songs_to_playlist(palylist.id, songs_in_spotify)
        if not self.is_currently_playing():
            self.play_playlist(palylist.uri)

    def recently_played(self):
        recently_played = self.client.current_user_recently_played()["items"]
        return [Song(**song["track"]) for song in recently_played]

    def play_song(self, uri):
        """
        Plays a song on the user's active device.

        Args:
            uri (str): The uri of the song to be played.

        If no device is active, it will play on the user's computer.
        """
        device_id = self.get_device_to_play_on()
        self.client.start_playback(uris=[uri], device_id=device_id)

    def play_playlist(self, uri):
        """
        Plays the specified playlist on the user's active device.

        Args:
            uri (str): The URI of the playlist to be played.

        If no device is currently active, it will attempt to play on the user's computer.
        """

        device_id = self.get_device_to_play_on()
        self.client.start_playback(context_uri=uri, device_id=device_id)

    def get_device_to_play_on(self):
        devices = self.get_all_user_devices()
        device_id = devices[0].id
        for device in devices:
            if device.is_active:
                device_id = device.id
                break
            if device.type.lower() == "computer" or device.type.lower() == "smartphone":
                device_id = device.id
        return device_id

    def users_top_tracks(self):
        songs = self.client.current_user_top_tracks()
        return [Song(**song) for song in songs["items"]]

    def add_songs_to_queue(self, uri, device_id=None):
        return self.client.add_to_queue(uri)

    def is_currently_playing(self):
        state = self.client.currently_playing()
        if not state:
            return False
        return state["is_playing"]
