from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ScoutCandidate(BaseModel):
    uri: str = Field(
        description="Spotify track URI, copied exactly from a tool result."
    )
    title: str
    artist: str
    why: str = Field(description="Why it fits the request, in a few words.")


class ScoutReport(BaseModel):
    interpretation: str = Field(
        description="How you read the request and what you looked for."
    )
    candidates: List[ScoutCandidate]


class CuratorAnswer(BaseModel):
    playlist_name: str = Field(description="The name you submitted.")
    reason: str = Field(
        description="2-4 sentences for the listener: how the playlist is shaped "
        "and why this length."
    )


class SongAnswer(BaseModel):
    reason: str = Field(description="1-2 sentences for the listener on why this song.")


class TrackInfo(BaseModel):
    uri: str
    title: str
    artist: str
    album: Optional[str] = None
    year: Optional[str] = None


Playback = Literal["playing", "queued", "none"]


class PlaylistOutcome(BaseModel):
    name: str
    reason: str
    research: str
    playlist_url: Optional[str]
    tracks: List[TrackInfo]
    playback: Playback
    dry_run: bool


class SongOutcome(BaseModel):
    track: TrackInfo
    reason: str
    playback: Playback
    dry_run: bool
