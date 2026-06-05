import asyncio

from bot.services.deezer import DeezerDownloader
from bot.services.download.base import DownloadSource
from bot.services.download.request import DownloadRequest

_DEEZER_TIMEOUT = 60.0


class DeezerDownloadSource(DownloadSource):
    def __init__(self, deezer: DeezerDownloader) -> None:
        self._deezer = deezer

    def can_handle(self, request: DownloadRequest) -> bool:
        return request.use_deezer and bool(request.title or request.artist)

    async def download(self, request: DownloadRequest) -> str:
        return await asyncio.wait_for(
            asyncio.to_thread(
                self._deezer.download,
                request.title or request.expected_title,
                request.artist or request.expected_artist,
                request.output_dir,
                request.isrc,
                request.expected_duration,
                request.on_progress,
            ),
            timeout=_DEEZER_TIMEOUT,
        )
