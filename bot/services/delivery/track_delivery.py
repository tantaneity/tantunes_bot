import logging
import shutil
import tempfile

from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.repositories.stats import DownloadRepository, SearchRepository
from bot.repositories.user import UserRepository
from bot.services.cache import CacheService
from bot.services.delivery.captions import CaptionRenderer
from bot.services.delivery.message import AudioMessage
from bot.services.delivery.messenger import AudioMessenger
from bot.services.delivery.request import TrackDeliveryRequest
from bot.services.delivery.uploader import AudioUploader
from bot.services.download import DownloaderService, DownloadRequest
from bot.services.tracker import TrackingService

logger = logging.getLogger(__name__)


class TrackDeliveryService:
    def __init__(
        self,
        cache: CacheService,
        downloader: DownloaderService,
        uploader: AudioUploader,
        messenger: AudioMessenger,
        captions: CaptionRenderer,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._cache = cache
        self._downloader = downloader
        self._uploader = uploader
        self._messenger = messenger
        self._captions = captions
        self._session_factory = session_factory
        self._upload_channel_id = settings.UPLOAD_CHANNEL_ID

    async def deliver(self, request: TrackDeliveryRequest) -> None:
        tmp_dir = tempfile.mkdtemp(prefix="tantunes_")
        try:
            await self._deliver(request, tmp_dir)
        except TelegramForbiddenError:
            logger.warning("Cannot send to user %s — bot not started", request.chat_id)
            if request.inline_message_id:
                await self._messenger.show_text(
                    inline_message_id=request.inline_message_id,
                    text=self._captions.bot_not_started(),
                )
        except Exception:
            logger.exception("Failed to deliver %s:%s", request.source, request.video_id)
            await self._messenger.show_text(
                chat_id=request.chat_id,
                message_id=request.message_id,
                inline_message_id=request.inline_message_id,
                text=self._captions.download_failed(),
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def _deliver(self, request: TrackDeliveryRequest, tmp_dir: str) -> None:
        meta = await self._cache.get_track_meta(request.source, request.video_id) or {}
        item = AudioMessage.from_meta(request.source, request.video_id, meta)
        if not item.url:
            raise ValueError(f"No URL in metadata for {request.source}:{request.video_id}")

        logger.info(
            "Downloading %s:%s | title=%r | url=%r",
            request.source,
            request.video_id,
            item.title,
            item.url,
        )

        on_progress = None
        if request.inline_message_id:
            on_progress = self._messenger.progress_callback(
                request.inline_message_id, request.source, request.video_id
            )

        path = await self._downloader.download(
            DownloadRequest(
                url=item.url,
                output_dir=tmp_dir,
                title=item.title,
                artist=item.performer,
                isrc=meta.get("isrc", ""),
                expected_duration=int(meta.get("duration") or 0),
                expected_title=item.title,
                expected_artist=item.performer,
                use_deezer=request.source == "spotify",
                on_progress=on_progress,
            )
        )

        target_chat = self._upload_channel_id or request.chat_id
        silent = self._upload_channel_id is not None
        item.file_id = await self._uploader.upload(item, path, target_chat, silent)

        await self._record_download(request.user_id, item)

        if request.inline_message_id:
            await self._messenger.edit_inline_audio(request.inline_message_id, item)
            return

        if target_chat != request.chat_id:
            await self._messenger.send_chat_audio(request.chat_id, item)
        if request.message_id:
            await self._messenger.delete(request.chat_id, request.message_id)

    async def _record_download(self, user_id: int, item: AudioMessage) -> None:
        async with self._session_factory() as session:
            tracking = TrackingService(
                UserRepository(session),
                DownloadRepository(session),
                SearchRepository(session),
            )
            await tracking.record_download(user_id, item.source, item.performer, item.title)
            await session.commit()
