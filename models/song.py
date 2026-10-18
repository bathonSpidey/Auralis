from models.base import BaseItem
from pydantic import field_serializer
from models.album import Album
from models.artist import Artist
from typing import List, Optional


class Song(BaseItem):
    id: str
    uri: str
    artists: List[Artist]
    album: Optional[Album] = None

    @field_serializer("artists")
    def serialize_first_artist(self, artists):
        if artists:
            return artists[0].name
        return []
