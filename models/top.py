from pydantic import BaseModel


class Top(BaseModel):
    name: str
    artist_name: str
