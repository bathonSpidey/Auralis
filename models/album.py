from typing import Optional

from models.base import BaseItem


class Album(BaseItem):
    release_date: Optional[str] = None
