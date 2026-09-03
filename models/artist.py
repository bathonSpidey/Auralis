from models.base import BaseItem
from typing import List


class Artist(BaseItem):
    uri: str
    genres: List[str] = []
