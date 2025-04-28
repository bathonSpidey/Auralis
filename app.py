import streamlit as st
import dotenv
import os
import base64

from agent.auralis import Auralis
from st_cookies_manager import EncryptedCookieManager
from src.spotify_api_connector import SpotifyApiConnector
from src.weather_api_connector import WeatherApiConnector

dotenv.load_dotenv()


class App:
    def __init__(self):
        self.spotify_connector = SpotifyApiConnector(
            os.getenv("SPOTIFY_CLIENT_ID"), os.getenv("SPOTIFY_CLIENT_SECRET")
        )
        self.cookies = EncryptedCookieManager(
            prefix="auralis/", password=os.getenv("COOKIES")
        )
        if not self.cookies.ready():
            st.error("🔒 Cookie Manager not ready. Check your configuration.")
            st.stop()
        self.openai_api_key = self.cookies.get("openai_api_key") if self.cookies.ready() else None
        self.model = self.cookies.get("selected_model") if self.cookies.ready() else "gemini-2.0-flash"
        self.title = "Auralis 🎵"

    def apply_custom_css(self):
        st.markdown("""
            <style>
                body {
                    background-color: #191414;
                    color: #FFFFFF;
                }
                .stApp {
                    background-color: #191414;
                }
                h1, h2, h3, h4, h5, h6 {
                    color: #1DB954;
                }
                .stButton>button {
                    background-color: #1DB954;
                    color: white;
                    border-radius: 8px;
                    padding: 0.6em 1.2em;
                    font-weight: 600;
                    transition: 0.3s;
                }
                .stButton>button:hover {
                    background-color: #1ed760;
                    color: #000000;
                }
                .stTextInput>div>div>input {
                    background-color: #282828;
                    color: #FFFFFF;
                    border-radius: 6px;
                }
                .stSelectbox>div>div>div>div {
                    background-color: #282828;
                    color: #FFFFFF;
                    border-radius: 6px;
                }
                footer {visibility: hidden;}

                /* 🔥 Frosted glass panels */
                .glass-card {
                    background: rgba(40, 40, 40, 0.6);
                    border: 1px solid rgba(29, 185, 84, 0.4);
                    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
                    backdrop-filter: blur(10px);
                    -webkit-backdrop-filter: blur(10px);
                    border-radius: 15px;
                    padding: 20px;
                    margin-top: 20px;
                    margin-bottom: 20px;
                }
            </style>
        """, unsafe_allow_html=True)

    def save_user_settings(self, api_key, model):
        self.cookies["openai_api_key"] = api_key
        self.cookies["selected_model"] = model
        self.cookies.save()
        st.success("✅ Settings saved! Ready to roll.")
        st.rerun()

    def reset_user_settings(self):
        self.cookies["openai_api_key"] = ""
        self.cookies["selected_model"] = ""
        self.cookies.save()
        self.openai_api_key = None
        st.success("🔄 Reset complete.")
        st.rerun()

    def run(self):
        self.apply_custom_css()
        file = open("resources/logo1.png", "rb")
        contents = file.read()
        data_url = base64.b64encode(contents).decode("utf-8")
        file.close()

        # Logo section
        st.markdown(
            """
            <div style="text-align:center;">
                <img src="data:image/png;base64,{data_url}" width="180" style="margin-bottom: 10px;">
                <h1 style="margin-bottom: 5px;">Auralis</h1>
                <p style="color: #B3B3B3;"><i>AI-powered Spotify Companion</i></p>
            </div>
            """,
            unsafe_allow_html=True
        )

        weather_connector = None

        if not self.openai_api_key:
            st.error("🚨 No API Key found. Please set it up to continue:")
            self.openai_api_key = st.text_input("Enter your OpenAI API Key", type="password")
            self.model = st.selectbox(
                "Select Model",
                ["gemini-2.0-flash", "gpt-4.1", "gpt-4o", "o4-mini", "local_lm_studio"],
                index=0,
                help="Choose your preferred AI model."
            )
            if st.button("Save & Continue"):
                self.save_user_settings(self.openai_api_key, self.model)
            st.stop()

        # Sidebar
        with st.sidebar:
            st.success(f"🧠 Model: {self.model}")
            if st.button("Reset API Key"):
                self.reset_user_settings()

            location_based = st.checkbox("Enable Location-based Suggestions", value=False)
            if location_based:
                weather_api_key = st.text_input("Enter Weather API Key", type="password", key="weather")
                if weather_api_key:
                    weather_connector = WeatherApiConnector(api_key=weather_api_key)

        # Main App Content
        # --- SONG OF THE MOMENT ---
        with st.container():
            

            st.markdown("""
                <div style="display: flex; align-items: center; gap: 10px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="#1DB954" viewBox="0 0 24 24">
                        <path d="M12 0C5.37 0 0 5.37 0 12s5.37 12 12 12 12-5.37 12-12C24 5.37 18.63 0 12 0zm0 21c-5.52 0-10-4.48-10-10S6.48 1 12 1s10 4.48 10 10-4.48 10-10 10zm-1-16h2v6h-2zm0 8h2v2h-2z"/>
                    </svg>
                    <h2 style="margin: 0; color: #1DB954;">Song of the Moment</h2>
                </div>
            """, unsafe_allow_html=True)

            if st.button("🎵 Get Song of the Moment"):
                with st.spinner("Finding the perfect song for you..."):
                    auralis = Auralis(self.spotify_connector, self.openai_api_key)
                    song, agent_message, message = auralis.song_of_the_moment_suggestion(
                        weather_connector=weather_connector
                    )
                    st.success(agent_message)
                    st.write(message)
                    if song and song.get("preview_url"):
                        st.audio(song["preview_url"], format="audio/mp3")
                        st.markdown(f"**{song['name']}** by *{song['artist']}*")
        st.divider()

        # --- PLAYLIST GENERATOR ---
        st.markdown("""
            ## <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="#1DB954" viewBox="0 0 24 24">
            <path d="M3 3h18v2H3zm0 4h12v2H3zm0 4h18v2H3zm0 4h12v2H3zm0 4h18v2H3z"/>
            </svg> Generate Custom Playlist
            """, unsafe_allow_html=True)
        user_playlist_prompt = st.text_input("📝 Describe the mood or theme...")
        if st.button("🎶 Generate Playlist"):
            with st.spinner("Creating your personalized playlist..."):
                auralis = Auralis(self.spotify_connector, self.openai_api_key)
                playlist, agent_message = auralis.playlist_generator(
                    user_prompt=user_playlist_prompt, weather_connector=weather_connector
                )
                st.success(agent_message)
                st.write(playlist)

        st.divider()
        st.caption("🚀 Built with ❤️ powered by OpenAI, Spotify, and Streamlit")

if __name__ == "__main__":
    app = App()
    app.run()
