import logging
import subprocess
import tempfile
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

    def _to_mp3(self, source: Path, output_dir: str) -> str:
        mp3_path = Path(output_dir) / source.with_suffix(".mp3").name
        subprocess.run(
            [_FFMPEG_PATH, "-i", str(source), "-b:a", "320k", "-y", str(mp3_path)],
            check=True,
            capture_output=True,
        )
        source.unlink(missing_ok=True)
        return str(mp3_path)

    def download(self, title: str, artist: str, output_dir: str, isrc: str = "") -> str:
        deezer_url = self._find_deezer_url(title, artist, isrc)
        if not deezer_url:
            raise LookupError(f"Track not found on Deezer: {artist} — {title}")

        dz = self._client()
        settings = deepcopy(_DEEMIX_SETTINGS)
        settings["downloadLocation"] = output_dir

        download_object = generateDownloadObject(dz, deezer_url, TrackFormats.MP3_320)
        Downloader(dz, download_object, settings).start()

        out = Path(output_dir)

        mp3_files = list(out.glob("*.mp3"))
        if mp3_files:
            return str(mp3_files[0])

        flac_files = list(out.glob("*.flac"))
        if flac_files:
            logger.info("Deezer: converting FLAC -> MP3 for %s", flac_files[0].name)
            return self._to_mp3(flac_files[0], output_dir)

        raise FileNotFoundError(f"No audio file after Deezer download for {artist} — {title}")
