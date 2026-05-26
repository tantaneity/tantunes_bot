import logging
import re
import subprocess
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

import imageio_ffmpeg
from deezer import Deezer, TrackFormats
from deemix import generateDownloadObject
from deemix.downloader import Downloader
from deemix.settings import DEFAULTS

_FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

_DEEMIX_SETTINGS = {
    **DEFAULTS,
    "maxBitrate": str(TrackFormats.MP3_320),
    "fallbackBitrate": True,
    "createAlbumFolder": False,
    "createArtistFolder": False,
    "createSingleFolder": False,
    "createCDFolder": False,
    "tracknameTemplate": "%artist% - %title%",
    "saveArtwork": False,
    "syncedLyrics": False,
    "overwriteFile": "y",
}

logger = logging.getLogger(__name__)


class DeezerDownloader:
    def __init__(self, arl: str) -> None:
        self._arl = arl
        self._dz: Deezer | None = None

    def _client(self) -> Deezer:
        if self._dz is None or not self._dz.logged_in:
            dz = Deezer()
            dz.login_via_arl(self._arl)
            self._dz = dz
        return self._dz

    def _find_deezer_url(self, title: str, artist: str, isrc: str = "") -> str | None:
        dz = self._client()

        if isrc:
            try:
                track = dz.api.get_track_by_ISRC(isrc)
                if track and track.get("id"):
                    return f"https://www.deezer.com/track/{track['id']}"
            except Exception:
                logger.debug("ISRC lookup failed for %s, trying text search", isrc)

        try:
            results = dz.api.search(f"{artist} {title}", limit=1)
            tracks = results.get("data") or []
            if tracks:
                return f"https://www.deezer.com/track/{tracks[0]['id']}"
        except Exception:
            logger.debug("Text search failed for %r %r", artist, title)

        return None

    def _get_audio_duration(self, path: Path) -> float:
        result = subprocess.run(
            [_FFMPEG_PATH, "-i", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
        if not match:
            return 0.0
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)

    def _to_mp3(self, source: Path, output_dir: str) -> str:
        mp3_path = Path(output_dir) / source.with_suffix(".mp3").name
        subprocess.run(
            [_FFMPEG_PATH, "-i", str(source), "-b:a", "320k", "-y", str(mp3_path)],
            check=True,
            capture_output=True,
        )
        source.unlink(missing_ok=True)
        return str(mp3_path)

    def download(
        self,
        title: str,
        artist: str,
        output_dir: str,
        isrc: str = "",
        expected_duration: int = 0,
        on_progress: "Callable[[int], None] | None" = None,
    ) -> str:
        if on_progress:
            on_progress(5)

        deezer_url = self._find_deezer_url(title, artist, isrc)
        if not deezer_url:
            raise LookupError(f"Track not found on Deezer: {artist} — {title}")

        if on_progress:
            on_progress(20)

        dz = self._client()
        settings = deepcopy(_DEEMIX_SETTINGS)
        settings["downloadLocation"] = output_dir

        download_object = generateDownloadObject(dz, deezer_url, TrackFormats.MP3_320)
        Downloader(dz, download_object, settings).start()

        if on_progress:
            on_progress(80)

        out = Path(output_dir)
        audio_file: Path | None = None

        mp3_files = list(out.glob("*.mp3"))
        if mp3_files:
            audio_file = mp3_files[0]
        else:
            flac_files = list(out.glob("*.flac"))
            if flac_files:
                logger.info("Deezer: converting FLAC -> MP3 for %s", flac_files[0].name)
                audio_file = Path(self._to_mp3(flac_files[0], output_dir))

        if audio_file is None:
            raise FileNotFoundError(f"No audio file after Deezer download for {artist} — {title}")

        if expected_duration > 60:
            actual = self._get_audio_duration(audio_file)
            if 0 < actual < 60:
                raise ValueError(
                    f"Deezer returned 30s preview ({actual:.0f}s) instead of "
                    f"full track ({expected_duration}s) for {artist} — {title}"
                )
            logger.info("Deezer: duration OK (%.0fs) for %s", actual, audio_file.name)

        if on_progress:
            on_progress(95)

        return str(audio_file)
