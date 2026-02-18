from pydantic import BaseModel, Field
from typing import List


class TrackMetadata(BaseModel):
    track_name: str = Field(alias="trackName")
    track_uri: str = Field(alias="trackUri")


class ChartEntry(BaseModel):
    # This reaches into the 'trackMetadata' key for each entry
    metadata: TrackMetadata = Field(alias="trackMetadata")


class Highlight(BaseModel):
    # Only type and text as requested
    type: str
    text: str


class ChartData(BaseModel):
    # We wrap the entries and highlights
    entries: List[ChartEntry]
    highlights: List[Highlight]

    def get_top_5_tracks(self):
        """Helper to return just the top 5 track objects"""
        return [entry.metadata for entry in self.entries[:5]]
