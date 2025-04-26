import dotenv
import os

from agent.auralis import Auralis
from src.SpotifyApiConnector import SpotifyApiConnector
from src.weather_api_connector import WeatherApiConnector

dotenv.load_dotenv()


class TestAuralis:
    
    spotify_connector = SpotifyApiConnector(client_id = os.getenv('SPOTIPY_CLIENT_ID') , client_secret=os.getenv('SPOTIPY_CLIENT_SECRET'))
    auralis = Auralis(spotify_connector, os.getenv('OPENAI_API_KEY'))
    
    def test_build_context(self):
        weather_connector = WeatherApiConnector(os.getenv('WEATHER'))
        context = self.auralis.build_context(weather_connector)
        assert len(context["recent_songs"]) == 10
        
    def test_song_of_the_moment_suggestion(self):
        song = self.auralis.song_of_the_moment_suggestion()
        assert song != None