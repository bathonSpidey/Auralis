from src.models.base import BaseItem
from pydantic import field_serializer
from src.models.artist import Artist
from typing import List

class Song(BaseItem):
    uri: str
    artists: List[Artist]
    
    @field_serializer('artists')
    def serialize_first_artist(self, artists):
        if artists:
            return artists[0].name
        return []