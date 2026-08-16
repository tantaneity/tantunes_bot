from yt_dlp.extractor import gen_extractor_classes

from bot.services.download.ytdlp_source import _SEARCH_PREFIX_RE
from bot.services.search_urls import SEARCH_PREFIXES, build_youtube_search_url, is_search_url


def _yt_dlp_search_keys() -> set[str]:
    return {
        extractor.SEARCH_KEY
        for extractor in gen_extractor_classes()
        if getattr(extractor, "SEARCH_KEY", None)
    }


def test_should_be_resolvable_by_yt_dlp_when_prefix_is_used():
    assert set(SEARCH_PREFIXES) <= _yt_dlp_search_keys()


def test_should_match_resolver_regex_when_url_is_built():
    assert _SEARCH_PREFIX_RE.match(build_youtube_search_url("Knife Party", "LRAD"))


def test_should_detect_search_url_when_prefix_is_present():
    assert is_search_url(build_youtube_search_url("feeble little horse", "Dog Song 2"))
    assert not is_search_url("https://soundcloud.com/artist/track")


if __name__ == "__main__":
    test_should_be_resolvable_by_yt_dlp_when_prefix_is_used()
    test_should_match_resolver_regex_when_url_is_built()
    test_should_detect_search_url_when_prefix_is_present()
    print("ok")
