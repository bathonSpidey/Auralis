import streamlit as st
import dotenv
import os

from agent.auralis import Auralis
from streamlit_cookies_manager import EncryptedCookieManager
from src.spotify_api_connector import SpotifyApiConnector
from src.weather_api_connector import WeatherApiConnector

dotenv.load_dotenv()


class App:
    def __init__(self):
        self.spotify_connector = SpotifyApiConnector(os.getenv("SPOTIFY_CLIENT_ID"), os.getenv("SPOTIFY_CLIENT_SECRET"))
        self.cookies = EncryptedCookieManager(prefix="auralis/", password=os.getenv("COOKIES"))
        if not self.cookies.ready():
             st.warning("Cookie Manager not ready. Check password configuration.")
             st.stop() # Stop if cookies can't be managed
        self.openai_api_key = self.cookies.get("openai_api_key") if self.cookies.ready() else None
        self.title = "Auralis - Your music buddy"
    
    def run(self):
        st.title(self.title)
        weather_connector = None
        if not self.openai_api_key:
            self.openai_api_key = st.text_input("OpenAI API Key", type="password")
            if st.button("Save API Key"):
                self.cookies["openai_api_key"] = self.openai_api_key
                self.cookies.save()
                st.rerun()
        if self.openai_api_key and st.button("Reset API Key"):
             self.cookies["openai_api_key"] = ""
             self.cookies.save()
             self.openai_api_key = None
             st.rerun()
        location_based = st.checkbox("Enable Location-based suggestion")
        if location_based:
            weather_api_key = st.text_input("Weather API Key", type="password")
            weather_connector = WeatherApiConnector(api_key=weather_api_key)
        if self.openai_api_key and st.button("Song of the moment!"):
            auralis = Auralis(self.spotify_connector, self.openai_api_key)
            song, agent_message, message = auralis.song_of_the_moment_suggestion(weather_connector=weather_connector)
            st.write(agent_message)
            st.write(message)
            
if __name__ == "__main__":
    app = App()
    app.run()