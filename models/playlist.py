from models.base import BaseItem


class Playlist(BaseItem):
    id: str
    href: str
    uri: str

    @property
    def url(self) -> str:
        return f"https://open.spotify.com/playlist/{self.id}"
