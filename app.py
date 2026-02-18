import streamlit as st
import dotenv
import os

from agent.auralis import Auralis
from st_cookies_manager import EncryptedCookieManager
from src.spotify_api_connector import SpotifyApiConnector
from src.spotify_scraper import SpotifyScraper
from src.weather_api_connector import WeatherApiConnector

dotenv.load_dotenv()

# ─────────────────────────────────────────────
#  GLOBAL CSS — applied once at module level
# ─────────────────────────────────────────────
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp {
    background: #0a0a0f !important;
    color: #e8e8ec;
    font-family: 'DM Sans', sans-serif;
    font-weight: 400;
}

/* Noise texture overlay */
.stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.035'/%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 0;
    opacity: 0.5;
}

/* ── Typography ── */
h1, h2, h3, h4 {
    font-family: 'Syne', sans-serif !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header, .stDeployButton { visibility: hidden; }
.block-container {
    padding: 2rem 2.5rem 4rem !important;
    max-width: 900px !important;
}

/* ── Hero Banner ── */
.hero-wrap {
    position: relative;
    padding: 3.5rem 0 2.5rem;
    text-align: center;
    overflow: hidden;
}
.hero-glow {
    position: absolute;
    top: -60px; left: 50%;
    transform: translateX(-50%);
    width: 520px; height: 320px;
    background: radial-gradient(ellipse, rgba(29,185,84,0.18) 0%, transparent 70%);
    pointer-events: none;
}
.hero-eyebrow {
    display: inline-block;
    font-family: 'DM Sans', sans-serif;
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #1DB954;
    border: 1px solid rgba(29,185,84,0.35);
    border-radius: 999px;
    padding: 4px 14px;
    margin-bottom: 1rem;
}
.hero-title {
    font-size: clamp(3rem, 8vw, 5.5rem) !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 800 !important;
    color: #ffffff !important;
    line-height: 1.0 !important;
    margin: 0 0 0.4rem !important;
}
.hero-title span { color: #1DB954; }
.hero-sub {
    color: #888899;
    font-size: 1.05rem;
    font-weight: 300;
    margin: 0;
    letter-spacing: 0.01em;
}

/* ── Welcome Pill ── */
.welcome-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(29,185,84,0.08);
    border: 1px solid rgba(29,185,84,0.25);
    border-radius: 999px;
    padding: 8px 20px;
    font-size: 0.9rem;
    color: #ccccd8;
    margin: 1rem 0 2rem;
}
.welcome-pill strong { color: #1DB954; }
.welcome-dot {
    width: 8px; height: 8px;
    background: #1DB954;
    border-radius: 50%;
    box-shadow: 0 0 6px #1DB954;
    animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.5; transform: scale(0.7); }
}

/* ── Section Cards ── */
.section-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px;
    padding: 2rem 2rem 1.6rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
.section-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(29,185,84,0.4), transparent);
}
.section-label {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.68rem;
    font-weight: 500;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: #1DB954;
    margin-bottom: 0.3rem;
}
.section-title {
    font-family: 'Syne', sans-serif !important;
    font-size: 1.55rem !important;
    font-weight: 700 !important;
    color: #ffffff !important;
    margin: 0 0 0.4rem !important;
}
.section-desc {
    color: #77778a;
    font-size: 0.9rem;
    margin: 0 0 1.4rem;
    line-height: 1.6;
}

/* ── Buttons ── */
.stButton > button {
    background: #1DB954 !important;
    color: #000000 !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.65em 1.4em !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.02em !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 0 0 0 rgba(29,185,84,0.4) !important;
}
.stButton > button:hover {
    background: #22d45f !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(29,185,84,0.3) !important;
}
.stButton > button:active {
    transform: translateY(0px) !important;
}

/* ── Text Inputs ── */
.stTextInput > div > div > input {
    background: rgba(255,255,255,0.05) !important;
    color: #e8e8ec !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
    padding: 0.7em 1em !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.92rem !important;
    transition: border-color 0.2s;
}
.stTextInput > div > div > input:focus {
    border-color: rgba(29,185,84,0.5) !important;
    box-shadow: 0 0 0 3px rgba(29,185,84,0.1) !important;
}
.stTextInput > label {
    color: #888899 !important;
    font-size: 0.82rem !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Selectbox ── */
.stSelectbox > div > div {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
    color: #e8e8ec !important;
}

/* ── Alerts ── */
.stSuccess {
    background: rgba(29,185,84,0.08) !important;
    border: 1px solid rgba(29,185,84,0.25) !important;
    border-radius: 12px !important;
    color: #a8f5c4 !important;
}
.stError {
    background: rgba(255,80,80,0.08) !important;
    border: 1px solid rgba(255,80,80,0.25) !important;
    border-radius: 12px !important;
}

/* ── Divider ── */
hr {
    border: none !important;
    border-top: 1px solid rgba(255,255,255,0.07) !important;
    margin: 2rem 0 !important;
}

/* ── Song List ── */
.song-row {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 10px 14px;
    border-radius: 10px;
    transition: background 0.15s;
    margin-bottom: 4px;
}
.song-row:hover { background: rgba(255,255,255,0.04); }
.song-num {
    font-family: 'Syne', sans-serif;
    font-size: 0.75rem;
    color: #555566;
    min-width: 22px;
    text-align: right;
}
.song-name {
    font-size: 0.92rem;
    color: #dddde8;
    font-weight: 500;
}

/* ── Login screen ── */
.login-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 60vh;
    text-align: center;
    gap: 1.2rem;
}
.login-logo {
    font-family: 'Syne', sans-serif;
    font-size: 4rem;
    font-weight: 800;
    color: #fff;
    letter-spacing: -0.04em;
    line-height: 1;
}
.login-logo span { color: #1DB954; }
.login-tagline { color: #666677; font-size: 1rem; margin: 0; }
.spotify-btn {
    display: inline-flex !important;
    align-items: center !important;
    gap: 10px !important;
    background: #1DB954 !important;
    color: #000 !important;
    padding: 14px 32px !important;
    border-radius: 999px !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    text-decoration: none !important;
    letter-spacing: 0.01em !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 20px rgba(29,185,84,0.35) !important;
    margin-top: 0.5rem !important;
}
.spotify-btn:hover {
    background: #22d45f !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 28px rgba(29,185,84,0.45) !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: #0d0d14 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.06) !important;
    color: #c8c8d4 !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,80,80,0.12) !important;
    color: #ff8080 !important;
    box-shadow: none !important;
}

/* ── Spinner ── */
.stSpinner > div { border-top-color: #1DB954 !important; }

/* ── Checkbox ── */
.stCheckbox > label { color: #888899 !important; font-size: 0.88rem !important; }

/* ── Expander ── */
.streamlit-expanderHeader {
    color: #888899 !important;
    font-size: 0.85rem !important;
}

/* ── API Key Setup Card ── */
.setup-card {
    background: rgba(29,185,84,0.04);
    border: 1px solid rgba(29,185,84,0.15);
    border-radius: 20px;
    padding: 2.5rem;
    text-align: center;
    max-width: 480px;
    margin: 3rem auto 0;
}
.setup-title {
    font-family: 'Syne', sans-serif;
    font-size: 1.4rem;
    font-weight: 700;
    color: #fff;
    margin-bottom: 0.3rem;
}
.setup-sub { color: #666677; font-size: 0.88rem; margin-bottom: 1.5rem; }

/* ── Footer ── */
.app-footer {
    text-align: center;
    color: #333344;
    font-size: 0.78rem;
    padding: 2rem 0 0.5rem;
    letter-spacing: 0.04em;
}
</style>
"""


class App:
    def __init__(self):
        st.set_page_config(
            page_title="Auralis — Your Music Agent",
            page_icon="🎵",
            layout="centered",
            initial_sidebar_state="collapsed",
        )
        # Inject CSS immediately after page config
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
        self.model = self.cookies.get("selected_model") or "gemini-2.5-flash"
        self.token_info = self.cookies.get("token_info") or None
        self.weather_connector = None
        self.city = None
        self.user = "Guest"

        # ── Auth gate ──
        self._handle_spotify_login()

        if self.spotify_connector.client is not None:
            self.user = self.spotify_connector.get_user_info()["display_name"]

    # ─────────────────────────────────────────────
    #  AUTH
    # ─────────────────────────────────────────────
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
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>
                    </svg>
                    Connect with Spotify
                </a>
                <p style="color:#333344; font-size:0.78rem; margin-top:0.5rem;">
                    Secure OAuth 2.0 — we never store your credentials
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ─────────────────────────────────────────────
    #  HERO
    # ─────────────────────────────────────────────
    def _render_hero(self):
        st.markdown(
            f"""
            <div class="hero-wrap">
                <div class="hero-glow"></div>
                <div class="hero-eyebrow">✦ AI Music Agent</div>
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

    # ─────────────────────────────────────────────
    #  SIDEBAR SETTINGS
    # ─────────────────────────────────────────────
    def _render_sidebar(self):
        with st.sidebar:
            st.markdown(
                "<p style='font-family:Syne,sans-serif; font-weight:700; font-size:1.1rem;"
                " color:#fff; margin-bottom:0.2rem;'>⚙️ Settings</p>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<p style='color:#555566; font-size:0.8rem; margin-top:0;'>Model: <span style='color:#1DB954'>{self.model}</span></p>",
                unsafe_allow_html=True,
            )
            st.divider()

            # Location
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

    # ─────────────────────────────────────────────
    #  API KEY SETUP (first-run gate)
    # ─────────────────────────────────────────────
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
                [
                    "gemini-2.5-flash",
                    "gemini-3-flash-preview",
                    "gpt-4.1",
                    "gpt-4o",
                    "o4-mini",
                    "local_lm_studio",
                ],
                label_visibility="collapsed",
            )
            if st.button("Save & Continue →", use_container_width=True):
                self._save_user_settings(api_key, model)
        st.stop()

    # ─────────────────────────────────────────────
    #  SONG OF THE MOMENT
    # ─────────────────────────────────────────────
    def _render_vibe_section(self):
        st.markdown(
            """
            <div class="section-card">
                <div class="section-label">✦ Instant Pick</div>
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
                with st.spinner("Tuning in…"):
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

    # ─────────────────────────────────────────────
    #  PLAYLIST GENERATOR
    # ─────────────────────────────────────────────
    def _render_playlist_section(self):
        st.markdown(
            """
            <div class="section-card">
                <div class="section-label">✦ Playlist Generator</div>
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
        reason = ""

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
                        self.lastfm_connector,
                    )
                    playlist_name, songs, reason = auralis.playlist_generator(
                        user_prompt=prompt,
                        weather_connector=self.weather_connector,
                        city=self.city,
                    )
                except Exception as e:
                    st.error(
                        "Couldn't generate playlist. The AI service may be temporarily unavailable."
                    )
                    with st.expander("Error details"):
                        st.code(str(e))

        if playlist_name:
            st.success(f"✅ **{playlist_name}** created in Spotify!")
            st.caption(reason)
            st.caption(
                "💡 The playlist may start playing on your last active Spotify device."
            )
            st.markdown("---")
            # Song list
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

    # ─────────────────────────────────────────────
    #  COOKIE HELPERS
    # ─────────────────────────────────────────────
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

    def _render_internal_chart_call(self):
        st.markdown(
            """
            <div class="section-card">
                <div class="section-label">✦ Debug Mode</div>
                <div class="section-title">Internal Chart Data</div>
                <p class="section-desc">Fetch data from the internal regional-de-weekly endpoint using your current session token.</p>
            </div>
        """,
            unsafe_allow_html=True,
        )

        if st.button("📡 Fetch Chart Data", use_container_width=True):
            token = st.session_state.get("spotify_token")
            if not token:
                st.error("No active token found. Please connect to Spotify first.")
                return
            scrapper = SpotifyScraper(token)
            with st.spinner("Accessing partner API..."):
                try:
                    chart_data = scrapper.get_viral_songs(country="jp")
                    st.json(chart_data)

                except Exception as e:
                    st.error(f"Request failed: {str(e)}")

    # ─────────────────────────────────────────────
    #  MAIN RUN
    # ─────────────────────────────────────────────
    def run(self):
        if not self.openai_api_key:
            self._render_hero()
            self._render_api_key_setup()
            return

        self._render_sidebar()
        self._render_hero()
        self._render_vibe_section()
        st.markdown("<div style='margin: 2rem 0;'></div>", unsafe_allow_html=True)
        self._render_playlist_section()
        # self._render_internal_chart_call()

        st.markdown(
            "<div class='app-footer'>Built with ❤️ · Powered by Spotify, Last.fm & AI</div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    app = App()
    app.run()
