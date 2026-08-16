import asyncio
import logging

import yt_dlp
from rapidfuzz import fuzz

from bot.models.album import AlbumInfo
from bot.models.track import TrackInfo
from bot.services.search_urls import SOUNDCLOUD_SEARCH_PREFIX
from bot.utils.text import parse_artist_title

logger = logging.getLogger(__name__)

_FLAT_OPTS = {"quiet": True, "no_warnings": True, "extract_flat": True}
_FULL_OPTS = {"quiet": True, "no_warnings": True}

_SCSEARCH_RESULTS = 4
_MAX_UPLOADERS = 3
_MIN_TITLE_SCORE = 60


def _best_thumbnail(item: dict) -> str:
    thumbnails = item.get("thumbnails") or []
    if thumbnails:
        return thumbnails[-1].get("url") or ""
    return item.get("thumbnail") or ""


def _split_query(query: str) -> tuple[str, str]:
    if " - " in query:
        artist, album = query.split(" - ", 1)
        return artist.strip(), album.strip()
    return "", query.strip()


def _candidate_terms(query: str, artist: str) -> list[str]:
    raw = [artist] if artist else []
    tokens = query.split()
    if tokens:
        raw.append(tokens[0])
    if len(tokens) >= 2:
        raw.append(" ".join(tokens[:2]))
    raw.append(query)

    ordered: list[str] = []
    for term in raw:
        term = term.strip()
        if term and term.lower() not in {existing.lower() for existing in ordered}:
            ordered.append(term)
    return ordered


def _entry_artist_title(entry: dict) -> tuple[str, str]:
    track_field = entry.get("track")
    artist_field = entry.get("artist") or entry.get("uploader") or "Unknown"
    if track_field:
        return artist_field, track_field
    return parse_artist_title(entry.get("title") or "Unknown", artist_field)


class SoundCloudAlbumService:
    def _meta_sync(self, url: str) -> AlbumInfo | None:
        with yt_dlp.YoutubeDL(_FLAT_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info or info.get("_type") != "playlist":
            return None

        entries = [e for e in (info.get("entries") or []) if e and e.get("id")]
        if not entries:
            return None

        cover = _best_thumbnail(info)
        if not cover:
            first_url = entries[0].get("webpage_url") or entries[0].get("url")
            if first_url:
                with yt_dlp.YoutubeDL(_FULL_OPTS) as ydl:
                    first = ydl.extract_info(first_url, download=False)
                cover = _best_thumbnail(first or {})

        return AlbumInfo(
            album_id=url,
            title=info.get("title") or "Unknown",
            artist=info.get("uploader") or info.get("uploader_id") or "Unknown",
            cover=cover,
            track_count=len(entries),
            year=str(info.get("release_year") or "")[:4],
            source="soundcloud",
        )

    def _tracks_sync(self, url: str) -> list[TrackInfo]:
        with yt_dlp.YoutubeDL(_FULL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        album_cover = _best_thumbnail(info or {})
        tracks: list[TrackInfo] = []
        for entry in (info.get("entries") or []):
            if not entry or not entry.get("id"):
                continue
            webpage_url = entry.get("webpage_url") or entry.get("url")
            if not webpage_url:
                continue

            performer, title = _entry_artist_title(entry)
            tracks.append(
                TrackInfo(
                    video_id=str(entry["id"]),
                    url=webpage_url,
                    source="soundcloud",
                    title=title,
                    performer=performer,
                    duration=int(entry.get("duration") or 0),
                    thumbnail=_best_thumbnail(entry) or album_cover,
                )
            )
        return tracks

    def _uploader_urls_sync(self, terms: list[str]) -> list[str]:
        ordered: list[str] = []
        for term in terms:
            try:
                with yt_dlp.YoutubeDL(_FLAT_OPTS) as ydl:
                    info = ydl.extract_info(
                        f"{SOUNDCLOUD_SEARCH_PREFIX}{_SCSEARCH_RESULTS}:{term}", download=False
                    )
            except Exception:
                logger.debug("scsearch failed for term %r", term, exc_info=True)
                continue
            for entry in (info.get("entries") or []):
                uploader_url = entry.get("uploader_url")
                if uploader_url and uploader_url not in ordered:
                    ordered.append(uploader_url)
        return ordered[:_MAX_UPLOADERS]

    def _list_albums_sync(self, uploader_url: str) -> list[tuple[str, str]]:
        url = f"{uploader_url.rstrip('/')}/albums"
        try:
            with yt_dlp.YoutubeDL(_FLAT_OPTS) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            logger.debug("Album list failed for %r", url, exc_info=True)
            return []
        albums: list[tuple[str, str]] = []
        for entry in (info.get("entries") or []):
            title = entry.get("title")
            album_url = entry.get("webpage_url") or entry.get("url")
            if title and album_url:
                albums.append((title, album_url))
        return albums

    def _search_sync(self, query: str, limit: int) -> list[AlbumInfo]:
        artist, album = _split_query(query)
        target = (album or query).lower()

        terms = _candidate_terms(query, artist)

        candidates: dict[str, str] = {}
        for uploader_url in self._uploader_urls_sync(terms):
            for title, album_url in self._list_albums_sync(uploader_url):
                candidates.setdefault(album_url, title)

        ranked = sorted(
            (
                (fuzz.token_set_ratio(target, title.lower()), album_url)
                for album_url, title in candidates.items()
            ),
            key=lambda scored: scored[0],
            reverse=True,
        )

        results: list[AlbumInfo] = []
        for score, album_url in ranked:
            if score < _MIN_TITLE_SCORE or len(results) >= limit:
                break
            meta = self._meta_sync(album_url)
            if meta:
                results.append(meta)
        return results

    async def fetch_album(self, url: str) -> AlbumInfo | None:
        return await asyncio.to_thread(self._meta_sync, url)

    async def search_albums(self, query: str, limit: int) -> list[AlbumInfo]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    async def get_tracks(self, url: str) -> list[TrackInfo]:
        return await asyncio.to_thread(self._tracks_sync, url)
