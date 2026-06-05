import re

_PUNCTUATION = re.compile(r"[^\w\s]")
_TITLE_SEPARATOR = " - "


def normalize(text: str) -> str:
    return _PUNCTUATION.sub("", text.lower()).strip()


def parse_artist_title(raw_title: str, fallback_artist: str) -> tuple[str, str]:
    if _TITLE_SEPARATOR in raw_title:
        artist, title = raw_title.split(_TITLE_SEPARATOR, 1)
        return artist.strip(), title.strip()
    return fallback_artist or "Unknown", raw_title
