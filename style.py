CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Inter:wght@300;400;500;600&display=swap');

/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp {
    background: linear-gradient(-45deg, #0a0a12, #111122, #0f0f1a, #0b0b14);
    background-size: 400% 400%;
    animation: gradientShift 18s ease infinite;!important;
    color: #e4e4ea;
    font-family: 'Inter', -apple-system, sans-serif;
    font-weight: 400;
    line-height: 1.6;
}

@keyframes gradientShift {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

/* Noise texture overlay */
.stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.025'/%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 0;
    opacity: 0.6;
}

body::after {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
        radial-gradient(rgba(29,185,84,0.15) 1px, transparent 1px);
    background-size: 40px 40px;
    animation: floatDots 40s linear infinite;
    pointer-events: none;
    opacity: 0.3;
}

@keyframes floatDots {
    from { transform: translateY(0px); }
    to { transform: translateY(-200px); }
}

/* ── Typography ── */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
    line-height: 1.25 !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header, .stDeployButton { visibility: hidden; }
.block-container {
    padding: 2.5rem 3rem 5rem !important;
    max-width: 920px !important;
}

/* ── Hero Banner ── */
.hero-wrap {
    position: relative;
    padding: 4rem 0 3rem;
    text-align: center;
    overflow: hidden;
}
:root {
    --hero-glow-color: rgba(29,185,84,0.25);
}

.hero-glow {
    position: absolute;
    top: -80px; left: 50%;
    transform: translateX(-50%);
    width: 600px; height: 400px;
    background: radial-gradient(
        ellipse,
        var(--hero-glow-color) 0%,
        transparent 70%
    );
    pointer-events: none;
    filter: blur(60px);
    transition: background 0.8s ease;
}
.hero-eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: 'Inter', sans-serif;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #1DB954;
    background: rgba(29,185,84,0.08);
    border: 1.5px solid rgba(29,185,84,0.25);
    border-radius: 999px;
    padding: 6px 16px;
    margin-bottom: 1.5rem;
}
.hero-title {
    font-size: clamp(3.5rem, 9vw, 6rem) !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 800 !important;
    color: #ffffff !important;
    line-height: 0.95 !important;
    margin: 0 0 0.6rem !important;
    background: linear-gradient(135deg, #ffffff 0%, #d0d0d8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.hero-title span { 
    background: linear-gradient(135deg, #1DB954 0%, #1ed760 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.hero-sub {
    color: #9999aa;
    font-size: 1.1rem;
    font-weight: 400;
    margin: 0;
    letter-spacing: -0.01em;
}

/* ── Welcome Pill ── */
.welcome-pill {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background: rgba(29,185,84,0.08);
    border: 1.5px solid rgba(29,185,84,0.2);
    border-radius: 999px;
    padding: 10px 24px;
    font-size: 0.9rem;
    color: #c8c8d8;
    margin: 1.5rem 0 3rem;
    font-weight: 500;
}
.welcome-pill strong { 
    color: #1DB954; 
    font-weight: 600;
}
.welcome-dot {
    width: 8px; height: 8px;
    background: #1DB954;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(29,185,84,0.6);
    animation: pulse 2.5s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.6; transform: scale(0.85); }
}

/* ── Section Cards ── */
.section-card {
    background: linear-gradient(135deg, rgba(29,185,84,0.04) 0%, rgba(18,18,28,0.6) 100%);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    background: rgba(18, 18, 28, 0.6);
    border: 1px solid rgba(255,255,255,0.08);
    border: 1.5px solid rgba(29,185,84,0.15);
    border-radius: 28px;
    padding: 2.5rem 2.5rem 2rem;
    margin-bottom: 2.5rem;
    position: relative;
    overflow: visible;
    box-shadow: 0 12px 48px rgba(0,0,0,0.15), 0 0 0 1px rgba(255,255,255,0.02) inset;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}
.section-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 16px 56px rgba(0,0,0,0.2), 0 0 0 1px rgba(29,185,84,0.1) inset;
}
.section-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, transparent 0%, rgba(29,185,84,0.6) 50%, transparent 100%);
    border-radius: 28px 28px 0 0;
}
.section-label {
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #1DB954;
    margin-bottom: 0.8rem;
    display: block;
}
.section-title {
    font-family: 'Outfit', sans-serif !important;
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    color: #ffffff !important;
    margin: 0 0 1rem !important;
    line-height: 1.3 !important;
    display: block !important;
    letter-spacing: -0.025em !important;
}
.section-desc {
    color: #9999aa;
    font-size: 0.98rem;
    margin: 0 0 2rem;
    line-height: 1.7;
    max-width: 95%;
    font-weight: 400;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #1DB954 0%, #1ed760 100%) !important;
    color: #000000 !important;
    border: none !important;
    border-radius: 16px !important;
    padding: 0.75em 1.8em !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.98rem !important;
    letter-spacing: -0.01em !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 16px rgba(29,185,84,0.25), 0 0 0 0 rgba(29,185,84,0.4) !important;
    position: relative;
    overflow: hidden;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #1ed760 0%, #22e06b 100%) !important;
    transform: translateY(-3px) scale(1.02) !important;
    box-shadow: 0 12px 32px rgba(29,185,84,0.35), 0 0 0 4px rgba(29,185,84,0.1) !important;
}
.stButton > button:active {
    transform: translateY(-1px) scale(0.98) !important;
}
.stButton > button:disabled {
    background: rgba(255,255,255,0.06) !important;
    color: #555566 !important;
    cursor: not-allowed !important;
    transform: none !important;
    box-shadow: none !important;
}

.stButton > button::after {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(255,255,255,0.3) 0%, transparent 60%);
    transform: rotate(25deg);
    opacity: 0;
    transition: opacity 0.4s ease;
}

.stButton > button:hover::after {
    opacity: 1;
}

/* ── Text Inputs ── */
.stTextInput > div > div > input {
    background: rgba(255,255,255,0.04) !important;
    color: #e8e8ec !important;
    border: 1.5px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
    padding: 0.75em 1.1em !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.95rem !important;
    transition: all 0.2s ease !important;
}
.stTextInput > div > div > input:focus {
    border-color: rgba(29,185,84,0.5) !important;
    box-shadow: 0 0 0 4px rgba(29,185,84,0.08) !important;
    background: rgba(255,255,255,0.06) !important;
}
.stTextInput > label {
    color: #9999aa !important;
    font-size: 0.85rem !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    margin-bottom: 0.5rem !important;
}

/* ── Selectbox ── */
.stSelectbox > div > div {
    background: rgba(255,255,255,0.04) !important;
    border: 1.5px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
    color: #e8e8ec !important;
}
.stSelectbox > label {
    color: #9999aa !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}

/* ── Alerts ── */
.stSuccess {
    background: rgba(29,185,84,0.08) !important;
    border: 1.5px solid rgba(29,185,84,0.25) !important;
    border-radius: 14px !important;
    color: #a8f5c4 !important;
    padding: 1rem 1.2rem !important;
}
.stError {
    background: rgba(255,80,80,0.08) !important;
    border: 1.5px solid rgba(255,80,80,0.25) !important;
    border-radius: 14px !important;
    padding: 1rem 1.2rem !important;
}

/* ── Divider ── */
hr {
    border: none !important;
    border-top: 1px solid rgba(255,255,255,0.06) !important;
    margin: 3rem 0 !important;
}

/* ── Song List ── */
.song-row {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 16px;
    border-radius: 12px;
    transition: all 0.2s ease;
    margin-bottom: 6px;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
}
.song-row:hover { 
    background: rgba(29,185,84,0.06);
    border-color: rgba(29,185,84,0.15);
    transform: translateX(4px);
}
.song-num {
    font-family: 'Outfit', sans-serif;
    font-size: 0.8rem;
    color: #666677;
    min-width: 26px;
    text-align: right;
    font-weight: 600;
}
.song-name {
    font-size: 0.95rem;
    color: #e0e0ea;
    font-weight: 500;
}

/* ── Login screen ── */
.login-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 65vh;
    text-align: center;
    gap: 1.5rem;
}
.login-logo {
    font-family: 'Outfit', sans-serif;
    font-size: 5rem;
    font-weight: 800;
    color: #fff;
    letter-spacing: -0.03em;
    line-height: 1;
    background: linear-gradient(135deg, #ffffff 0%, #d0d0d8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.login-logo span { 
    background: linear-gradient(135deg, #1DB954 0%, #1ed760 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.login-tagline { 
    color: #777788; 
    font-size: 1.05rem; 
    margin: 0;
    font-weight: 400;
}
.spotify-btn {
    display: inline-flex !important;
    align-items: center !important;
    gap: 12px !important;
    background: linear-gradient(135deg, #1DB954 0%, #1ed760 100%) !important;
    color: #000 !important;
    padding: 16px 36px !important;
    border-radius: 999px !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
    text-decoration: none !important;
    letter-spacing: -0.01em !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 8px 28px rgba(29,185,84,0.35) !important;
    margin-top: 1rem !important;
}
.spotify-btn:hover {
    background: linear-gradient(135deg, #1ed760 0%, #22e06b 100%) !important;
    transform: translateY(-3px) scale(1.02) !important;
    box-shadow: 0 12px 36px rgba(29,185,84,0.45) !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d0d16 0%, #12121c 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.05) !important;
    color: #c8c8d4 !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    border-radius: 12px !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,80,80,0.12) !important;
    color: #ff8080 !important;
    box-shadow: none !important;
    transform: translateY(-1px) !important;
}

/* ── Spinner ── */
.stSpinner > div { border-top-color: #1DB954 !important; }

/* ── Checkbox ── */
.stCheckbox > label { 
    color: #9999aa !important; 
    font-size: 0.9rem !important;
    font-weight: 500 !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    color: #9999aa !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    background: rgba(255,255,255,0.03) !important;
    border-radius: 12px !important;
}

/* ── API Key Setup Card ── */
.setup-card {
    background: linear-gradient(135deg, rgba(29,185,84,0.06) 0%, rgba(18,18,28,0.8) 100%);
    border: 1.5px solid rgba(29,185,84,0.2);
    border-radius: 24px;
    padding: 3rem 2.5rem;
    text-align: center;
    max-width: 520px;
    margin: 3rem auto 0;
    box-shadow: 0 12px 48px rgba(0,0,0,0.2);
}
.setup-title {
    font-family: 'Outfit', sans-serif;
    font-size: 1.6rem;
    font-weight: 700;
    color: #fff;
    margin-bottom: 0.5rem;
    letter-spacing: -0.02em;
}
.setup-sub { 
    color: #777788; 
    font-size: 0.95rem; 
    margin-bottom: 2rem;
    line-height: 1.6;
}

/* ── Footer ── */
.app-footer {
    text-align: center;
    color: #444455;
    font-size: 0.8rem;
    padding: 3rem 0 1rem;
    letter-spacing: 0.03em;
    font-weight: 500;
}

/* ── Spacing refinements ── */
.stMarkdown { margin-bottom: 0 !important; }
div[data-testid="column"] { padding: 0 0.5rem !important; }


</style>
"""
