import asyncio
import logging

import yt_dlp

from bot.models.album import AlbumInfo
from bot.models.track import TrackInfo
from bot.services.search import _parse_title

logger = logging.getLogger(__name__)

_FLAT_OPTS = {"quiet": True, "no_warnings": True, "extract_flat": True}
_FULL_OPTS = {"quiet": True, "no_warnings": True}


def _best_thumbnail(item: dict) -> str:
    thumbnails = item.get("thumbnails") or []
    if thumbnails:
        return thumbnails[-1].get("url") or ""
    return item.get("thumbnail") or ""


def _entry_artist_title(entry: dict) -> tuple[str, str]:
    track_field = entry.get("track")
    artist_field = entry.get("artist") or entry.get("uploader") or "Unknown"
    if track_field:
        return artist_field, track_field
    return _parse_title(entry.get("title") or "Unknown", artist_field)


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

    async def fetch_album(self, url: str) -> AlbumInfo | None:
        return await asyncio.to_thread(self._meta_sync, url)

    async def get_tracks(self, url: str) -> list[TrackInfo]:
        return await asyncio.to_thread(self._tracks_sync, url)
