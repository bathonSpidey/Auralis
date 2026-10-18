from typing import List

from pydantic import BaseModel, Field


class SongSuggestion(BaseModel):
    song_title: str = Field(description="The title of the song.")
    artist_name: str = Field(description="The name of the song's main artist.")
    reason: str = Field(description="Why this song fits right now.")


class PlaylistSong(BaseModel):
    song_title: str = Field(description="The title of the song.")
    artist_name: str = Field(description="The name of the song's main artist.")


class PlaylistSuggestion(BaseModel):
    playlist_name: str = Field(description="A short, evocative playlist name.")
    songs: List[PlaylistSong] = Field(description="The songs, in play order.")
    reason: str = Field(
        description="Why these songs fit the request, including the chosen length."
    )


class PlaylistOutcome(BaseModel):
    suggestion: PlaylistSuggestion
    playlist_url: str
    added: List[str]
    not_found: List[str]
    playing: bool
