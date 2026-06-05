import logging

from bot.services.download.base import DownloadSource
from bot.services.download.request import DownloadRequest

logger = logging.getLogger(__name__)


class DownloaderService:
    def __init__(
        self,
        ytdlp_source: DownloadSource,
        deezer_source: DownloadSource | None = None,
    ) -> None:
        self._ytdlp = ytdlp_source
        self._deezer = deezer_source

    async def download(self, request: DownloadRequest) -> str:
        if self._deezer is not None and self._deezer.can_handle(request):
            try:
                path = await self._deezer.download(request)
                logger.info("Deezer download succeeded for %r — %r", request.artist, request.title)
                return path
            except TimeoutError:
                logger.warning("Deezer timed out for %r — %r", request.artist, request.title)
            except Exception:
                logger.warning(
                    "Deezer failed for %r — %r, falling back to yt-dlp",
                    request.artist,
                    request.title,
                    exc_info=True,
                )

        return await self._ytdlp.download(request)
