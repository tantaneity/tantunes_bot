import asyncio
import logging
import os
import re

import imageio_ffmpeg
import yt_dlp
from rapidfuzz import fuzz

from bot.services.download.base import DownloadSource
from bot.services.download.request import DownloadRequest

_FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
_SEARCH_PREFIX_RE = re.compile(r"^(ytmsearch|ytsearch|scsearch)\d*:")
_BROAD_RESULTS = 5
_DURATION_TOLERANCE = 0.15
_PREFERRED_QUALITY = "128"

logger = logging.getLogger(__name__)


def _score_entry(
    entry: dict,
    expected_title: str,
    expected_artist: str,
    expected_duration: int,
) -> float:
    result_title = (entry.get("title") or "").lower()
    title_score = fuzz.token_sort_ratio(expected_title.lower(), result_title) / 100

    uploader = (entry.get("uploader") or entry.get("channel") or "").lower()
    artist_score = fuzz.partial_ratio(expected_artist.lower(), uploader) / 100

    if expected_duration > 0:
        duration = entry.get("duration") or 0
        delta_ratio = abs(duration - expected_duration) / expected_duration
        duration_score = max(0.0, 1.0 - delta_ratio / _DURATION_TOLERANCE)
    else:
        duration_score = 0.5

    return duration_score * 0.55 + title_score * 0.35 + artist_score * 0.10


class YtDlpDownloadSource(DownloadSource):
    def can_handle(self, request: DownloadRequest) -> bool:
        return True

    async def download(self, request: DownloadRequest) -> str:
        return await asyncio.to_thread(self._download_sync, request)

    def _resolve_search_url(self, request: DownloadRequest) -> str:
        url = request.url
        if not _SEARCH_PREFIX_RE.match(url):
            return url

        broad_url = _SEARCH_PREFIX_RE.sub(lambda m: f"{m.group(1)}{_BROAD_RESULTS}:", url)
        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(broad_url, download=False)

        entries = (info or {}).get("entries") or []
        if not entries:
            return url

        if request.expected_title or request.expected_duration:
            scored = [
                (
                    _score_entry(
                        entry,
                        request.expected_title,
                        request.expected_artist,
                        request.expected_duration,
                    ),
                    index,
                    entry,
                )
                for index, entry in enumerate(entries)
            ]
            scored.sort(key=lambda item: item[0], reverse=True)
            best_score, _, best = scored[0]
            logger.debug("Best match for %r: %r (score=%.2f)", url, best.get("title"), best_score)
            return self._entry_url(best, url)

        return self._entry_url(entries[0], url)

    def _entry_url(self, entry: dict, fallback: str) -> str:
        video_id = entry.get("id", "")
        return (
            entry.get("webpage_url")
            or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
            or fallback
        )

    def _download_sync(self, request: DownloadRequest) -> str:
        url = self._resolve_search_url(request)
        output_dir = request.output_dir
        on_progress = request.on_progress
        last_bucket = [-1]

        def _hook(status: dict) -> None:
            if on_progress is None or status.get("status") != "downloading":
                return
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            downloaded = status.get("downloaded_bytes", 0)
            if not total:
                return
            percent = int(downloaded / total * 100)
            bucket = percent // 10
            if bucket != last_bucket[0]:
                last_bucket[0] = bucket
                on_progress(min(percent, 99))

        ydl_opts = {
            "format": "bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio",
            "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": _PREFERRED_QUALITY,
                }
            ],
            "ffmpeg_location": _FFMPEG_PATH,
            "concurrent_fragment_downloads": 4,
            "quiet": True,
            "no_warnings": True,
            "noprogress": on_progress is None,
            "progress_hooks": [_hook] if on_progress is not None else [],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        for filename in os.listdir(output_dir):
            if filename.endswith(".mp3"):
                return os.path.join(output_dir, filename)

        raise FileNotFoundError(f"mp3 not found in {output_dir} after downloading {url}")
