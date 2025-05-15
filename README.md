# 🎵 Auralis
[![Auralis](https://github.com/bathonSpidey/Auralis/actions/workflows/code-check.yml/badge.svg)](https://github.com/bathonSpidey/Auralis/actions/workflows/code-check.yml) [![Bandit](https://github.com/bathonSpidey/Auralis/actions/workflows/bandit.yml/badge.svg)](https://github.com/bathonSpidey/Auralis/actions/workflows/bandit.yml)

**Auralis** is an **Agentic AI** that generates personalized **songs** and **playlists** based on your mood, prompts, and environment.  
It’s a fun project designed for anyone who wants to **learn, build, and explore Agentic AI** concepts!

---

## 🚀 How It Works

Auralis acts as an intelligent agent with tools to generate music recommendations.  
Currently, it supports **two main features**:

1. **🎶 Song for the Moment**

   - Get a song recommendation from an LLM.
   - If you have an active Spotify device, the song plays automatically!
   - No active device? No worries — the song still appears on the frontend for manual play.

2. **📜 Prompt-Based Playlist Generator**
   - Create a customized playlist based on your own text prompts (e.g., _"chill summer vibes"_ or _"motivational workout beats"_).

---

## 📲 How to Use It

Auralis runs on **Streamlit**, making it simple and interactive!

> **Important:** You’ll need to **bring your own API keys** to get started.

Here's what you need:

- **LLM API Key:**  
  Use keys from providers like OpenAI (ChatGPT), Google Gemini, or even your own locally hosted LLM.

- **Weather API Key (optional):**  
  If you want music recommendations based on your current weather!

---

## 🛠️ Developer Setup

Want to **develop, contribute**, or **customize** Auralis?  
Follow these simple steps:

1. **Clone the Repository**

   ```bash
   git clone <repository>
   ```

2. **Set Up a Virtual Environment**

   ```bash
   python -m venv .venv
   ```

3. **Activate the Environment**

   - On Windows:
     ```bash
     .venv\Scripts\activate
     ```
   - On Mac/Linux:
     ```bash
     source .venv/bin/activate
     ```

4. **Install Requirements**

   ```bash
   pip install -r requirements.txt
   ```

5. **Create a `.env` File**  
   Add your API keys and settings:
   ```env
   SPOTIPY_CLIENT_ID="<your Spotify client ID>"
   SPOTIPY_CLIENT_SECRET="<your Spotify client secret>"
   OPENAI_API_KEY="<your LLM API key>"
   WEATHER="<your weather API key (optional)>"
   COOKIES="<your cookie encryption key>"
   ```

---

## 📚 Supported APIs and Services

| API/Service     | Purpose                                             | Example                                                                |
| :-------------- | :-------------------------------------------------- | :--------------------------------------------------------------------- |
| **Spotify API** | Song playback, search, playlists                    | [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) |
| **OpenAI**      | Generating song recommendations & playlists         | [OpenAI Platform](https://platform.openai.com/)                        |
| **Gemini**      | Generating song recommendations & playlists         | [Google AI Studio](https://aistudio.google.com/prompts/new_chat)       |
| **LM Studio**   | Generating song recommendations & playlists locally | [LM Studio](https://lmstudio.ai/)                                      |
| **Weather API** | Location-based music suggestions                    | [WeatherAPI.com](https://openweathermap.org/api/one-call-3)            |

---

# 🎧 Ready to create your perfect vibe?

Run Auralis, input your mood, and let the magic happen!
