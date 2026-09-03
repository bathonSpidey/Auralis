import streamlit as st
import dotenv
import os

from agent.auralis import Auralis
from st_cookies_manager import EncryptedCookieManager
from src.spotify_api_connector import SpotifyApiConnector
from src.spotify_scraper import SpotifyScraper
from src.weather_api_connector import WeatherApiConnector
from style import CUSTOM_CSS
import datetime

dotenv.load_dotenv()

# ─────────────────────────────────────────────
#  GLOBAL CSS — Professional, Cohesive Theme
# ─────────────────────────────────────────────


class App:
    def __init__(self):
        st.set_page_config(
            page_title="Auralis — Your Music Agent",
            page_icon="🎵",
            layout="centered",
            initial_sidebar_state="collapsed",
        )
        st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

        st.cache_data.clear()
        st.cache_resource.clear()

        self.title = "Auralis"

        local_auth = os.getenv("LOCAL", "").lower() == "true"
        self.spotify_connector = SpotifyApiConnector(
            os.getenv("SPOTIFY_CLIENT_ID"),
            os.getenv("SPOTIFY_CLIENT_SECRET"),
            local_auth,
        )

        self.cookies = EncryptedCookieManager(
            prefix="auralis/", password=os.getenv("COOKIES")
        )
        if not self.cookies.ready():
            st.error(
                "🔒 Cookie Manager not ready. Please enable cookies for this site."
            )
            st.stop()

        self.openai_api_key = self.cookies.get("openai_api_key") or None
        self.model = self.cookies.get("selected_model") or next(
            iter(Auralis.supported_models)
        )
        self.weather_connector = None
        self.city = None
        self.user = "Guest"

        self._handle_spotify_login()

        if self.spotify_connector.client is not None:
            self.user = self.spotify_connector.get_user_info()["display_name"]

    def _handle_spotify_login(self):
        if "spotify_token" not in st.session_state:
            qp = st.query_params
            if "code" not in qp:
                self._render_login_screen()
                st.stop()
            else:
                token_info = self.spotify_connector.get_token_from_code(qp["code"])
                if token_info:
                    st.session_state["spotify_token"] = token_info["access_token"]
                    self.spotify_connector.get_client(token_info)
                    st.query_params.clear()
                    st.rerun()
        else:
            self.spotify_connector.get_client(st.session_state["spotify_token"])

    def _render_login_screen(self):
        auth_url = self.spotify_connector.get_auth_url()
        st.markdown(
            f"""
            <div class="login-wrap">
                <div>
                    <div class="login-logo">Aur<span>a</span>lis</div>
                    <p class="login-tagline">Your Personal Music Agent — Smarter. Tuned to You.</p>
                </div>
                <a href="{auth_url}" target="_self" class="spotify-btn">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>
                    </svg>
                    Connect with Spotify
                </a>
                <p style="color:#555566; font-size:0.8rem; margin-top:0.8rem; font-weight:400;">
                    Secure OAuth 2.0 · We never store your credentials
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def _render_hero(self):
        st.markdown(
            f"""
            <div class="hero-wrap">
                <div class="hero-glow"></div>
                <div class="hero-eyebrow">✦ AI MUSIC AGENT</div>
                <h1 class="hero-title">Aur<span>a</span>lis</h1>
                <p class="hero-sub">Music that moves with you — powered by AI.</p>
            </div>
            <div style="display:flex; justify-content:center;">
                <div class="welcome-pill">
                    <div class="welcome-dot"></div>
                    Listening as&nbsp;<strong>{self.user}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def _render_sidebar(self):
        with st.sidebar:
            st.markdown(
                "<p style='font-family:Outfit,sans-serif; font-weight:700; font-size:1.15rem;"
                " color:#fff; margin-bottom:0.3rem;'>⚙️ Settings</p>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<p style='color:#666677; font-size:0.82rem; margin-top:0;'>Model: <span style='color:#1DB954; font-weight:600;'>{self.model}</span></p>",
                unsafe_allow_html=True,
            )
            st.divider()

            location_on = st.checkbox("📍 Enable Location Suggestions", value=False)
            if location_on:
                self.city = st.text_input("City", placeholder="e.g. London", key="city")
                weather_key = st.text_input(
                    "Weather API Key",
                    type="password",
                    key="weather",
                    help="Get a free key at weatherapi.com",
                )
                if weather_key:
                    self.weather_connector = WeatherApiConnector(api_key=weather_key)
                with st.expander("How to get a Weather API key"):
                    st.markdown(
                        "Sign up at [weatherapi.com](https://www.weatherapi.com/) "
                        "and copy your key from the dashboard."
                    )

            st.divider()
            if st.button("🗑 Reset API Key", use_container_width=True):
                self._reset_user_settings()

    def _render_api_key_setup(self):
        st.markdown(
            """
            <div class="setup-card">
                <div class="setup-title">One last step 🔑</div>
                <p class="setup-sub">Enter your AI API key to unlock playlist generation and song recommendations.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            api_key = st.text_input(
                "AI API Key",
                type="password",
                label_visibility="collapsed",
                placeholder="Paste your API key here…",
            )
            model = st.selectbox(
                "Model",
                list(Auralis.supported_models.keys()),
                label_visibility="collapsed",
            )
            if st.button("Save & Continue →", use_container_width=True):
                self._save_user_settings(api_key, model)
        st.stop()

    def _render_vibe_section(self):
        st.markdown(
            """
            <div class="section-card">
                <div class="section-label">✦ INSTANT PICK</div>
                <div class="section-title">Song of the Moment</div>
                <p class="section-desc">
                    Let AI read your taste, the weather, and the time of day to find
                    the one track that fits right now.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            if st.button("✦ Find My Vibe", use_container_width=True):
                with st.spinner(
                    "Analyzing your taste profile 🎧\nReading weather ☁️\nUnderstanding your vibe 🧠"
                ):
                    try:
                        auralis = Auralis(
                            self.spotify_connector,
                            self.openai_api_key,
                            SpotifyScraper(st.session_state.get("spotify_token")),
                        )
                        song_name, artist_name, reason = (
                            auralis.song_of_the_moment_suggestion(
                                weather_connector=self.weather_connector,
                                city=self.city,
                            )
                        )
                        st.success(f"🎵 **{song_name}** — {artist_name}\n\n_{reason}_")
                        st.caption("Added to your Spotify queue.")
                    except Exception as e:
                        st.error(
                            "Couldn't find a song right now. Check your Spotify connection."
                        )
                        with st.expander("Error details"):
                            st.code(str(e))

    def _render_playlist_section(self):
        st.markdown(
            """
            <div class="section-card">
                <div class="section-label">✦ PLAYLIST GENERATOR</div>
                <div class="section-title">Build a Playlist for Any Moment</div>
                <p class="section-desc">
                    Describe a mood, activity, or fantasy — and get a full Spotify playlist
                    tailored to it in seconds.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        prompt = st.text_input(
            "What's your vibe?",
            placeholder="e.g. Late-night drive through a neon city 🌆",
            label_visibility="collapsed",
        )

        col_l, col_c, col_r = st.columns([1, 2, 1])
        playlist_name = None
        songs = []

        with col_c:
            generate = st.button(
                "🎧 Generate Playlist",
                use_container_width=True,
                disabled=not bool(prompt),
            )

        if generate and prompt:
            with st.spinner("Crafting your playlist…"):
                try:
                    auralis = Auralis(
                        self.spotify_connector,
                        self.openai_api_key,
                        SpotifyScraper(st.session_state.get("spotify_token")),
                    )
                    playlist_name, songs, reason = auralis.playlist_generator(
                        user_prompt=prompt,
                        weather_connector=self.weather_connector,
                        city=self.city,
                    )
                    if playlist_name:
                        st.success(f"✅ **{playlist_name}** created in Spotify!")
                        st.caption(reason)
                        st.caption(
                            "💡 The playlist may start playing on your last active Spotify device."
                        )
                        st.markdown("---")
                        tracks_html = "".join(
                            f'<div class="song-row">'
                            f'<span class="song-num">{i:02d}</span>'
                            f'<span class="song-name">{song}</span>'
                            f"</div>"
                            for i, song in enumerate(songs, 1)
                        )
                        st.markdown(
                            f'<div style="margin-top:0.5rem;">{tracks_html}</div>',
                            unsafe_allow_html=True,
                        )
                except Exception as e:
                    st.error(
                        "Couldn't generate playlist. The AI service may be temporarily unavailable."
                    )
                    with st.expander("Error details"):
                        st.code(str(e))

    def _save_user_settings(self, api_key, model):
        self.cookies["openai_api_key"] = api_key
        self.cookies["selected_model"] = model
        self.cookies.save()
        st.success("✅ Settings saved!")
        st.rerun()

    def _reset_user_settings(self):
        for key in ("openai_api_key", "selected_model", "token_info"):
            self.cookies[key] = ""
        self.cookies.save()
        self.openai_api_key = None
        st.rerun()

    def run(self):
        hour = datetime.datetime.now().hour

        if 6 <= hour < 18:
            glow_color = "rgba(29,185,84,0.25)"
        else:
            glow_color = "rgba(120,100,255,0.25)"

        st.markdown(
            f"""
            <style>
            :root {{
                --hero-glow-color: {glow_color};
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
        if not self.openai_api_key:
            self._render_hero()
            self._render_api_key_setup()
            return
        self._render_sidebar()
        self._render_hero()
        self._render_vibe_section()
        st.markdown("<div style='margin: 2.5rem 0;'></div>", unsafe_allow_html=True)
        self._render_playlist_section()

        st.markdown(
            "<div class='app-footer'>Built with ❤️ · Powered by Spotify & AI</div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    app = App()
    app.run()
