import streamlit as st
import dotenv
import os

from agent.auralis import Auralis
from st_cookies_manager import EncryptedCookieManager
from src.spotify_api_connector import SpotifyApiConnector
from src.weather_api_connector import WeatherApiConnector

dotenv.load_dotenv()


class App:
    def __init__(self):
        self.title = "Auralis 🎵"
        st.set_page_config(page_title=self.title, page_icon="🎧")
        self.apply_custom_css()

        self.cookies = EncryptedCookieManager(
            prefix="auralis/", password=os.getenv("COOKIES")
        )
        if not self.cookies.ready():
            st.error(
                "🔒 Cookie Manager not ready. Check your configuration. Enable cookies for this website"
            )
            st.stop()
        self.spotify_connector = SpotifyApiConnector(
            os.getenv("SPOTIFY_CLIENT_ID"), os.getenv("SPOTIFY_CLIENT_SECRET")
        )
        self.openai_api_key = (
            self.cookies.get("openai_api_key") if self.cookies.ready() else None
        )
        self.model = (
            self.cookies.get("selected_model")
            if self.cookies.ready()
            else "gemini-2.0-flash"
        )
        self.token_info = (
            self.cookies.get("token_info") if self.cookies.ready() else None
        )
        if not self.token_info:
            self.user = "Please sign in!"
        else:
            self.spotify_connector.get_client(self.token_info)
            self.user = self.spotify_connector.get_user_info()["display_name"]
        self.introduction()

        self.weather_connector = None
        self.city = None
        self.user = "unknown"
        self.handle_spotify_login()

    def introduction(self):
        st.markdown(
            f"""
                <div style="display: flex; flex-direction: column; align-items: center; margin-bottom: 30px; margin-right: 30px;">
                    <div style="display: flex; align-items: left; gap: 10px;">
                        <img src="https://github.com/bathonSpidey/Auralis/blob/e3948377dca6996d5f16ea46dd128e1dc05a76ac/resources/logo1.png?raw=true" 
                            alt="Auralis Logo" style="width:80px; height:auto;">
                        <h1 style="margin: 0; color: #1DB954;">Auralis</h1>
                    </div>
                    <p style="color: #B3B3B3; margin: 10px 0 0 0; font-size: 18px; text-align: center;">
                        <i>Your Personal Music Agent — Smarter. Sharper. Tuned to You.</i>
                        <p style="margin-top: 15px; font-size: 20px; color: white; background: linear-gradient(90deg, #1DB954 0%, #1ED760 100%); padding: 8px 20px; border-radius: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);">
            🎧 Welcome back, <strong>{self.user}</strong> </p>
                    </p>
                </div>
                """,
            unsafe_allow_html=True,
        )
        st.markdown("""---""")

    def handle_spotify_login(self):
        if "spotify_token" not in st.session_state:
            query_parms = st.query_params
            if "code" not in query_parms:
                auth_url = self.spotify_connector.get_auth_url()
                st.markdown(
                    f"""
                <div style="text-align: center; margin-top: 2rem;">
                    <a href="{auth_url}" target="_self" style="
                        background-color: #1DB954;
                        color: white;
                        padding: 0.75rem 1.5rem;
                        border-radius: 30px;
                        font-weight: bold;
                        text-decoration: none;
                        font-size: 1.1rem;
                        display: inline-block;
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
                        transition: background-color 0.3s ease;
                    " onmouseover="this.style.backgroundColor='#17a74a'" onmouseout="this.style.backgroundColor='#1DB954'">
                        🎵 Connect with Spotify
                    </a>
                </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.stop()
            else:
                code = query_parms["code"][0]
                token_info = self.spotify_connector.get_token_from_code(code)
                if token_info:
                    st.session_state["spotify_token"] = token_info["access_token"]
                    self.spotify_connector.get_client(token_info)
                    st.success("Successfully authenticated! Reload the app.")
                    st.rerun()
        else:
            token_info = st.session_state["spotify_token"]
            self.spotify_connector.get_client(token_info)
        self.user = self.spotify_connector.get_user_info()["display_name"]
        st.rerun()

    def apply_custom_css(self):
        st.markdown(
            """
                    <style>
                    body, .stApp {
                background: linear-gradient(135deg, #121212 0%, #1c1c1c 100%);
                background-attachment: fixed;
                color: #EAEAEA;
                font-family: 'Poppins', sans-serif;
            }

            /* Headings with subtle Spotify accent */
            h1, h2, h3, h4, h5, h6 {
                color: #1DB954;
                font-family: 'Poppins', sans-serif;
                font-weight: 600;
            }

            /* Buttons - more balanced green and hover */
            .stButton>button {
                background-color: #1DB954;
                color: #FFFFFF;
                border-radius: 10px;
                padding: 0.6em 1.2em;
                font-weight: 500;
                transition: all 0.3s ease;
                border: none;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            }

            .stButton>button:hover {
                background-color: #25e06b;
                color: #000000;
                transform: translateY(-1px);
                box-shadow: 0 6px 14px rgba(0, 0, 0, 0.25);
            }

            /* Inputs and select boxes - softened glass look */
            .stTextInput>div>div>input,
            .stSelectbox>div>div>div>div {
                background-color: rgba(255, 255, 255, 0.07);
                color: #FFFFFF;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                padding: 0.5em;
                font-size: 14px;
            }

            /* Glassmorphism container */
            .glass-card {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                box-shadow: 0 8px 32px 0 rgba(0,0,0,0.35);
                backdrop-filter: blur(12px);
                border-radius: 16px;
                padding: 24px;
                margin: 20px 0;
            }

            /* Hide Streamlit footer */
            footer {visibility: hidden;}
                    </style>
        """,
            unsafe_allow_html=True,
        )

    def save_user_settings(self, api_key, model):
        self.cookies["openai_api_key"] = api_key
        self.cookies["selected_model"] = model

        self.cookies.save()
        st.success("✅ Settings saved! Ready to roll.")
        st.rerun()

    def save_spotify_token(self, token_info):
        self.cookies["token_info"] = token_info
        self.cookies.save()
        st.success("✅ Token saved! Ready to roll.")
        st.rerun()

    def reset_user_settings(self):
        self.cookies["openai_api_key"] = ""
        self.cookies["selected_model"] = ""
        self.cookies["token_info"] = ""
        self.cookies.save()
        self.openai_api_key = None
        st.success("🔄 Reset complete.")
        st.rerun()

    def run(self):
        if not self.openai_api_key:
            st.error("🚨 No API Key found. Please set it up to continue:")
            self.openai_api_key = st.text_input(
                "Enter your OpenAI API Key", type="password"
            )
            self.model = st.selectbox(
                "Select Model",
                ["gemini-2.0-flash", "gpt-4.1", "gpt-4o", "o4-mini", "local_lm_studio"],
                index=0,
                help="Choose your preferred AI model.",
            )
            if st.button("Save & Continue"):
                self.save_user_settings(self.openai_api_key, self.model)
            st.stop()

        # Sidebar
        with st.sidebar:
            self.settings()

        # Main App Content
        # --- SONG OF THE MOMENT ---
        with st.container():
            message = ""
            st.markdown(
                """
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; justify-content: center; gap: 10px;">
                        <svg height="64px" width="64px" version="1.1" id="Layer_1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 511.994 511.994" xml:space="preserve" fill="#000000"><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"></g><g id="SVGRepo_iconCarrier"> <circle style="fill:#1DB954;" cx="255.997" cy="255.997" r="255.997"></circle> <path style="opacity:0.1;enable-background:new ;" d="M23.403,279.403c0-141.384,114.615-255.999,255.999-255.999 c64.737,0,123.85,24.041,168.931,63.666C401.417,33.696,332.648,0,255.999,0C114.615,0,0,114.615,0,255.999 c0,76.648,33.696,145.418,87.07,192.334C47.444,403.254,23.403,344.14,23.403,279.403z"></path> <path style="fill:#FFFFFF;" d="M255.999,447.641c-105.671,0-191.64-85.97-191.64-191.641s85.97-191.64,191.64-191.64 s191.64,85.97,191.64,191.64S361.671,447.641,255.999,447.641z"></path> <path style="opacity:0.1;enable-background:new ;" d="M87.762,279.403c0-105.671,85.97-191.64,191.64-191.64 c46.891,0,89.893,16.938,123.235,45.003c-35.182-41.797-87.857-68.407-146.638-68.407c-105.671,0-191.64,85.97-191.64,191.64 c0,58.781,26.61,111.456,68.407,146.638C104.701,369.296,87.762,326.294,87.762,279.403z"></path> <g> <path style="fill:#000000;" d="M255.999,64.359c-2.942,0-5.866,0.077-8.776,0.209v51.096c0,4.847,3.928,8.776,8.776,8.776 c4.848,0,8.776-3.929,8.776-8.776V64.569C261.867,64.436,258.942,64.359,255.999,64.359z"></path> <path style="fill:#000000;" d="M385.097,114.491l-36.072,36.07c-3.427,3.427-3.427,8.985,0,12.411 c1.714,1.714,3.96,2.571,6.207,2.571c2.246,0,4.492-0.857,6.207-2.571l36.07-36.07C393.562,122.579,389.42,118.438,385.097,114.491 z"></path> <path style="fill:#000000;" d="M447.431,247.223h-51.095c-4.848,0-8.776,3.929-8.776,8.776s3.928,8.776,8.776,8.776h51.095 c0.132-2.91,0.209-5.834,0.209-8.776C447.641,253.058,447.564,250.133,447.431,247.223z"></path> <path style="fill:#000000;" d="M397.509,385.097l-36.07-36.07c-3.429-3.427-8.985-3.427-12.412,0s-3.427,8.985,0,12.411 l36.072,36.07C389.42,393.562,393.562,389.42,397.509,385.097z"></path> <path style="fill:#000000;" d="M255.999,387.56c-4.848,0-8.776,3.929-8.776,8.776v51.096c2.91,0.132,5.834,0.209,8.776,0.209 c2.942,0,5.866-0.077,8.776-0.209v-51.096C264.776,391.488,260.847,387.56,255.999,387.56z"></path> <path style="fill:#000000;" d="M150.562,349.026l-36.07,36.07c3.947,4.323,8.089,8.465,12.412,12.412l36.072-36.07 c3.427-3.427,3.427-8.985,0-12.411C159.547,345.599,153.991,345.599,150.562,349.026z"></path> <path style="fill:#000000;" d="M115.664,247.223H64.569c-0.132,2.91-0.209,5.834-0.209,8.776c0,2.942,0.077,5.866,0.209,8.776 h51.095c4.848,0,8.776-3.929,8.776-8.776S120.511,247.223,115.664,247.223z"></path> <path style="fill:#000000;" d="M114.491,126.902l36.07,36.07c1.714,1.713,3.961,2.571,6.207,2.571c2.246,0,4.492-0.857,6.207-2.571 c3.427-3.427,3.427-8.985,0-12.411l-36.072-36.07C122.579,118.438,118.438,122.579,114.491,126.902z"></path> <path style="fill:#000000;" d="M303.437,320.988c-4.492,0-8.985-1.714-12.411-5.142L243.59,268.41 c-3.292-3.292-5.142-7.756-5.142-12.411v-88.358c0-9.694,7.859-17.552,17.552-17.552c9.694,0,17.552,7.859,17.552,17.552v81.087 l42.296,42.296c6.855,6.854,6.855,17.968,0,24.823C312.42,319.275,307.928,320.988,303.437,320.988z"></path> </g> </g></svg>
                        <h2 style="margin: 0; color: #1DB954;">Song of the Moment</h2>
                    </div>
                </div>
            """,
                unsafe_allow_html=True,
            )

            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                st.empty()
            with col2:
                st.markdown(
                    "🎵 Victory, struggle, hope — whatever your story, the right music is just one click away. Find it now..."
                )
                if st.button("Find my vibe", use_container_width=True):
                    with st.spinner("Finding the perfect song for you..."):
                        auralis = Auralis(self.spotify_connector, self.openai_api_key)
                        song, agent_message, message = (
                            auralis.song_of_the_moment_suggestion(
                                weather_connector=self.weather_connector, city=self.city
                            )
                        )
                        st.success(
                            f"Your background track is: {agent_message['song_title']} by {agent_message['artist_name']}"
                        )
            st.write(message)
            with col3:
                st.empty()
        st.divider()

        # --- PLAYLIST GENERATOR ---
        st.markdown(
            """
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; justify-content: center; gap: 10px;">
                        <svg fill="#1DB954" height="64px" width="64px" version="1.1" id="Capa_1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 512 512" xml:space="preserve"><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g id="SVGRepo_tracerCarrier" stroke-linecap="round" stroke-linejoin="round"></g><g id="SVGRepo_iconCarrier"> <g> <polygon points="176,368 137.6,432 374.4,432 336,368 "></polygon> <path d="M480,80H32C14.328,80,0,94.326,0,112v288c0,17.672,14.328,32,32,32h68.561l57.322-96h196.234l57.322,96H480 c17.674,0,32-14.328,32-32V112C512,94.326,497.674,80,480,80z M96,272c-17.672,0-32-14.328-32-32c0-17.674,14.328-32,32-32 c17.674,0,32,14.326,32,32C128,257.672,113.674,272,96,272z M336,272H176v-64h160V272z M416,272c-17.672,0-32-14.328-32-32 c0-17.674,14.328-32,32-32c17.674,0,32,14.326,32,32C448,257.672,433.674,272,416,272z"></path> </g> </g></svg>
                        <h2 style="margin: 0; color: #1DB954;">Generate Playlist For Your Occasion</h2>
                    </div>
                </div>
            """,
            unsafe_allow_html=True,
        )
        playlist = None
        agent_message = None

        user_playlist_prompt = st.text_input(
            "📝 What's your vibe today? 🎶\n"
            "Describe a mood, moment, or even a wild fantasy! 🚀\n"
            "Examples: 'Study session with coffee ☕', 'Epic road trip across mountains 🛣️', 'Chill beats on a rainy night 🌧️' — or invent your own!"
        )
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            st.empty()
        with col2:
            if user_playlist_prompt and st.button(
                "🎧 Generate your Playlist", use_container_width=True
            ):
                with st.spinner("Creating your personalized playlist..."):
                    auralis = Auralis(self.spotify_connector, self.openai_api_key)
                    playlist, agent_message = auralis.playlist_generator(
                        user_prompt=user_playlist_prompt,
                        weather_connector=self.weather_connector,
                        city=self.city,
                    )
        with col3:
            st.empty()
        if playlist is not {} and playlist is not None:
            st.success(agent_message)
            st.markdown(
                "Note: This playlist might start playing directly in the device that you last played so please check your app. "
            )
            st.markdown(f"### 🎵 Playlist: {playlist['playlist_name']}")
            st.markdown("---")
            for idx, song in enumerate(playlist["songs"], start=1):
                st.markdown(f"**{idx}. {song}**")
        elif playlist is {}:
            st.error(agent_message)

        st.divider()
        st.caption("🚀 Built with ❤️ powered by Curiosity, Spotify, and Streamlit")

    def settings(self):
        st.success(f"🧠 Model: {self.model}")
        if st.button("Reset API Key"):
            self.reset_user_settings()

        location_based = st.checkbox("Enable Location-based Options", value=False)
        with st.expander("Enable Location-based Suggestions"):
            st.markdown(
                "You have to have a valid weather api key to use these feature. You can contact the developer for one or bring your own keys"
            )
        if location_based:
            self.city = st.text_input("Enter city you are at", key="city")
            weather_api_key = st.text_input(
                "Enter Weather API Key", type="password", key="weather"
            )
            with st.expander("Need help getting a Weather API key?"):
                st.markdown(
                    "You can sign up at [weatherapi.com](https://www.weatherapi.com/) and find your key in the dashboard."
                )

            if weather_api_key:
                self.weather_connector = WeatherApiConnector(api_key=weather_api_key)


if __name__ == "__main__":
    app = App()
    app.run()
