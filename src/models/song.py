from src.models.base import BaseItem
from src.models.artist import Artist
from typing import List

class Song(BaseItem):
    uri: str
    artists: List[Artist]