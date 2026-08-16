YOUTUBE_SEARCH_PREFIX = "ytsearch"
SOUNDCLOUD_SEARCH_PREFIX = "scsearch"
SEARCH_PREFIXES = (YOUTUBE_SEARCH_PREFIX, SOUNDCLOUD_SEARCH_PREFIX)

_SINGLE_RESULT = 1


def build_youtube_search_url(artist: str, title: str) -> str:
    return f"{YOUTUBE_SEARCH_PREFIX}{_SINGLE_RESULT}:{artist} {title}"


def is_search_url(url: str) -> bool:
    return url.startswith(SEARCH_PREFIXES)
