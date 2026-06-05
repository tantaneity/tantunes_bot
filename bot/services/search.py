import asyncio
import dataclasses
import logging
from abc import ABC, abstractmethod

import yt_dlp

from bot.models.track import TrackInfo
from bot.services.cache import CacheService
from bot.utils.text import normalize, parse_artist_title

logger = logging.getLogger(__name__)

_SOURCE_PRIORITY: dict[str, int] = {"spotify": 0, "soundcloud": 1, "youtube": 2}


_SC_NON_TRACK_SLUGS = frozenset(
    ("sets", "stream", "likes", "reposts", "tracks", "albums", "following", "followers")
)


def _is_sc_track_url(url: str) -> bool:
    if not url:
        return False

    path = url.split("soundcloud.com", 1)[-1].strip("/")
    parts = [p for p in path.split("/") if p]

    if len(parts) != 2:
        return False
    slug = parts[1]
    return slug not in _SC_NON_TRACK_SLUGS


def _relevance(track: TrackInfo, query_words: frozenset[str]) -> int:
    text = normalize(f"{track.performer} {track.title}")
    return sum(1 for w in query_words if w in text)


class SearchProvider(ABC):
    @property
    @abstractmethod
    def source(self) -> str: ...

    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[TrackInfo]: ...


class YtDlpProvider(SearchProvider):
    def __init__(self, source: str, prefix: str) -> None:
        self._source = source
        self._prefix = prefix

    @property
    def source(self) -> str:
        return self._source

    def _search_sync(self, query: str, max_results: int) -> list[TrackInfo]:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"{self._prefix}{max_results}:{query}", download=False)

        results: list[TrackInfo] = []
        for entry in info.get("entries") or []:
            if not entry or not entry.get("id"):
                continue

            video_id = str(entry["id"])

            if self._source == "soundcloud":



                wp = entry.get("webpage_url", "")
                if not _is_sc_track_url(wp):
                    logger.debug(
                        "SoundCloud entry %s skipped: bad webpage_url %r", video_id, wp
                    )
                    continue
                url = wp
            else:
                url = (
                    entry.get("webpage_url")
                    or entry.get("url")
                    or (
                        f"https://www.youtube.com/watch?v={video_id}"
                        if self._source == "youtube"
                        else None
                    )
                )
                if not url:
                    continue

            thumbnail = entry.get("thumbnail") or (
                f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
                if self._source == "youtube"
                else ""
            )

            raw_title = entry.get("title") or "Unknown"
            artist_field = entry.get("artist") or entry.get("uploader") or "Unknown"
            track_field = entry.get("track")
            if track_field:
                performer, title = artist_field, track_field
            else:
                performer, title = parse_artist_title(raw_title, artist_field)

            results.append(
                TrackInfo(
                    video_id=video_id,
                    url=url,
                    source=self._source,
                    title=title,
                    performer=performer,
                    duration=int(entry.get("duration") or 0),
                    thumbnail=thumbnail,
                )
            )
        return results

    async def search(self, query: str, max_results: int) -> list[TrackInfo]:
        return await asyncio.to_thread(self._search_sync, query, max_results)


class SearchService:
    def __init__(self, providers: list[SearchProvider], cache: CacheService) -> None:
        self._providers = providers
        self._cache = cache

    async def search(self, query: str, max_results: int = 5) -> list[TrackInfo]:
        cached = await self._cache.get_search_cache(query)
        if cached:
            return [TrackInfo(**t) for t in cached]

        tasks = [p.search(query, max_results) for p in self._providers]
        raw = await asyncio.gather(*tasks, return_exceptions=True)

        merged: list[TrackInfo] = []
        for provider, result in zip(self._providers, raw, strict=False):
            if isinstance(result, Exception):
                logger.warning("Search failed for source=%s: %s", provider.source, result)
                continue
            merged.extend(result)





        seen: dict[tuple[str, str], int] = {}
        deduped: list[TrackInfo] = []
        for track in merged:
            key = (normalize(track.performer), normalize(track.title))
            is_search_url = track.url.startswith(("ytsearch", "scsearch"))
            if key not in seen:
                seen[key] = len(deduped)
                deduped.append(track)
            elif is_search_url:
                pass
            else:
                idx = seen[key]
                existing = deduped[idx]
                if existing.url.startswith(("ytsearch", "scsearch")):
                    deduped[idx] = dataclasses.replace(existing, url=track.url)

        sc_provider = next((p for p in self._providers if p.source == "soundcloud"), None)
        if sc_provider:
            resolve_tasks = []
            resolve_indices = []
            for i, track in enumerate(deduped):
                if track.source == "spotify" and track.url.startswith(("ytmsearch", "ytsearch")):
                    resolve_tasks.append(
                        sc_provider.search(f"{track.performer} {track.title}", max_results=1)
                    )
                    resolve_indices.append(i)

            if resolve_tasks:
                sc_results = await asyncio.gather(*resolve_tasks, return_exceptions=True)
                for i, sc in zip(resolve_indices, sc_results, strict=False):
                    if isinstance(sc, Exception) or not sc:
                        continue
                    candidate = sc[0]
                    if _is_sc_track_url(candidate.url):
                        deduped[i] = dataclasses.replace(deduped[i], url=candidate.url)
                        logger.debug("Resolved spotify:%s → SC %s", deduped[i].video_id, candidate.url)

        query_words = frozenset(normalize(query).split())
        deduped.sort(key=lambda t: (-_relevance(t, query_words), _SOURCE_PRIORITY.get(t.source, 99)))

        results = deduped[:max_results]
        if results:
            await self._cache.set_search_cache(
                query, [dataclasses.asdict(t) for t in results]
            )
        return results
