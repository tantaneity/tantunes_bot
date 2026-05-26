import asyncio
import logging
import os
import re
from collections.abc import Callable

import imageio_ffmpeg
import yt_dlp
from rapidfuzz import fuzz

from bot.services.deezer import DeezerDownloader

_FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
_SEARCH_PREFIX_RE = re.compile(r"^(ytmsearch|ytsearch|scsearch)\d*:")
_DEEZER_TIMEOUT = 60.0

logger = logging.getLogger(__name__)


def _score_entry(
    entry: dict,
    expected_title: str,
    expected_artist: str,
    expected_duration: int,
) -> float:
    result_title = (entry.get("title") or "").lower()
    exp_title = expected_title.lower()

    title_score = fuzz.token_sort_ratio(exp_title, result_title) / 100

    uploader = (entry.get("uploader") or entry.get("channel") or "").lower()
    artist_score = fuzz.partial_ratio(expected_artist.lower(), uploader) / 100

    if expected_duration > 0:
        duration = entry.get("duration") or 0
        delta_ratio = abs(duration - expected_duration) / expected_duration
        duration_score = max(0.0, 1.0 - delta_ratio / 0.15)
    else:
        duration_score = 0.5

    return duration_score * 0.55 + title_score * 0.35 + artist_score * 0.10


class DownloaderService:
    def __init__(self, deezer: DeezerDownloader | None = None) -> None:
        self._deezer = deezer

    def _resolve_search_url(
        self,
        url: str,
        expected_duration: int = 0,
        expected_title: str = "",
        expected_artist: str = "",
    ) -> str:
        if not _SEARCH_PREFIX_RE.match(url):
            return url

        broad_url = _SEARCH_PREFIX_RE.sub(lambda m: f"{m.group(1)}5:", url)
        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(broad_url, download=False)

        entries = (info or {}).get("entries") or []
        if not entries:
            return url

        def _entry_url(e: dict) -> str:
            vid = e.get("id", "")
            return (
                e.get("webpage_url")
                or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
                or url
            )

        if expected_title or expected_duration:
            scored = [
                (
                    _score_entry(e, expected_title, expected_artist, expected_duration),
                    i,
                    e,
                )
                for i, e in enumerate(entries)
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, _, best = scored[0]
            logger.debug(
                "Best match for %r: %r (score=%.2f)",
                url, best.get("title"), best_score,
            )
            return _entry_url(best)

        return _entry_url(entries[0])

    def _download_sync(
        self,
        url: str,
        output_dir: str,
        on_progress: Callable[[int], None] | None = None,
        expected_duration: int = 0,
        expected_title: str = "",
        expected_artist: str = "",
    ) -> str:
        url = self._resolve_search_url(url, expected_duration, expected_title, expected_artist)

        last_bucket: list[int] = [-1]

        def _hook(d: dict) -> None:
            if on_progress is None or d.get("status") != "downloading":
                return
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if not total:
                return
            pct = int(downloaded / total * 100)
            bucket = pct // 10
            if bucket != last_bucket[0]:
                last_bucket[0] = bucket
                on_progress(min(pct, 99))

        ydl_opts = {
            "format": "bestaudio[ext=mp3]/bestaudio[ext=m4a]/bestaudio",
            "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
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

    async def download(
        self,
        url: str,
        output_dir: str,
        on_progress: Callable[[int], None] | None = None,
        expected_duration: int = 0,
        expected_title: str = "",
        expected_artist: str = "",
        title: str = "",
        artist: str = "",
        isrc: str = "",
        use_deezer: bool = False,
    ) -> str:
        if use_deezer and self._deezer and (title or artist):
            try:
                mp3_path = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._deezer.download,
                        title or expected_title,
                        artist or expected_artist,
                        output_dir,
                        isrc,
                        expected_duration,
                    ),
                    timeout=_DEEZER_TIMEOUT,
                )
                logger.info("Deezer download succeeded for %r — %r", artist, title)
                return mp3_path
            except asyncio.TimeoutError:
                logger.warning("Deezer timed out after %.0fs for %r — %r", _DEEZER_TIMEOUT, artist, title)
            except Exception:
                logger.warning("Deezer failed for %r — %r, falling back to YouTube", artist, title, exc_info=True)

        return await asyncio.to_thread(
            self._download_sync, url, output_dir,
            on_progress, expected_duration, expected_title, expected_artist,
        )
