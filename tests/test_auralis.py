import dotenv
import pytest
import os

from agent.auralis import Auralis
from src.spotify_api_connector import SpotifyApiConnector
from src.weather_api_connector import WeatherApiConnector

dotenv.load_dotenv()


@pytest.mark.skipif(
    not os.getenv("SPOTIPY_CLIENT_ID"), reason="SPOTIPY_CLIENT_ID not set"
)
@pytest.mark.integration
class TestAuralis:
    spotify_connector = SpotifyApiConnector(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        local=True,
    )
    auralis = Auralis(spotify_connector, os.getenv("OPENAI_API_KEY"))
    weather_connector = WeatherApiConnector(os.getenv("WEATHER"))

    def test_registry(self):
        registry = self.auralis.registry
        assert (
            registry.tools["suggest_song"]["description"]
            == "Suggest and plays a song in spotify"
        )

    def test_action_should_match_existing_tool(self):
        existing_tool_song = {
            "type": "function",
            "function": {
                "name": "suggest_song",
                "description": "Suggest and plays a song in spotify",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "song_title": {"type": "string"},
                        "artist_name": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["song_title", "artist_name", "reason"],
                },
            },
        }
        existing_tool_playlist = {
            "type": "function",
            "function": {
                "name": "generate_playlist",
                "description": "Assembles a playlist in spotify",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "playlist_name": {"type": "string"},
                        "songs": {
                            "type": "array",
                            "items": {
                                "type": "string",
                            },
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["playlist_name", "songs", "reason"],
                },
            },
        }
        tools = self.auralis.registry.to_openai_tools()
        assert tools[0] == existing_tool_song
        assert tools[1] == existing_tool_playlist

    def test_build_context(self):
        context = self.auralis.build_context(self.weather_connector)
        assert len(context["recently_played_songs"]) == 20

    @pytest.mark.slow
    def test_song_of_the_moment_suggestion(self):
        song = self.auralis.song_of_the_moment_suggestion()
        assert song is not None

    @pytest.mark.slow
    def test_generate_playlist(self):
        playlist = self.auralis.playlist_generator(
            "Generate a playlist called Test and add only one song."
        )
        assert playlist is not None
