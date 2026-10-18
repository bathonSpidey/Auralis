from typing import List

from pydantic import BaseModel, Field


class SongSuggestion(BaseModel):
    song_title: str = Field(description="The title of the song.")
    artist_name: str = Field(description="The name of the song's main artist.")
    reason: str = Field(description="Why this song fits right now.")


class PlaylistSuggestion(BaseModel):
    playlist_name: str = Field(description="A short, evocative playlist name.")
    songs: List[str] = Field(
        description="Songs in the form 'Song Title - Artist Name', in play order."
    )
    reason: str = Field(
        description="Why these songs fit the request, including the chosen length."
    )
