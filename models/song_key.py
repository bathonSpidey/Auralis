"""Identify "the same song" across Spotify releases (album, single, remaster).

A track URI is per release, so rules like "never suggest this song again" must
compare songs by title and artist instead.
"""

import re
import unicodedata

_BRACKETED = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_DASH_SUFFIX = re.compile(
    r"\s+-\s+.*\b(remaster(ed)?|version|single|mono|stereo|deluxe|bonus|edit|radio|"
    r"explicit|clean|anniversary|live|\d{4})\b.*$",
    re.I,
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def song_key(title: str, artist: str) -> str:
    title = _DASH_SUFFIX.sub("", _BRACKETED.sub(" ", title))
    return f"{normalize(title)}|{normalize(artist)}"
