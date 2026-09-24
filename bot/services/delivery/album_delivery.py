import asyncio
import contextlib
import dataclasses
import logging
import shutil
import tempfile
import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InputMediaAudio, InputMediaPhoto, InputRichMessage, InputRichMessageMedia
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.models.album import AlbumInfo
from bot.models.track import TrackInfo
from bot.repositories.stats import DownloadRepository, SearchRepository
from bot.repositories.user import UserRepository
from bot.services.album import AlbumService
from bot.services.cache import CacheService
from bot.services.delivery.captions import CaptionRenderer
from bot.services.delivery.message import AudioMessage
from bot.services.delivery.request import AlbumDeliveryRequest
from bot.services.delivery.uploader import AudioUploader
from bot.services.download import DownloaderService, DownloadRequest
from bot.services.soundcloud_album import SoundCloudAlbumService
from bot.services.tracker import TrackingService

logger = logging.getLogger(__name__)

_MAX_CONCURRENCY = 3
_RICH_MEDIA_LIMIT = 50
_COVER_MEDIA_ID = "cover"
_PROGRESS_MIN_INTERVAL = 1.5


class AlbumDeliveryService:
    def __init__(
        self,
        bot: Bot,
        spotify: AlbumService | None,
        soundcloud: SoundCloudAlbumService,
        downloader: DownloaderService,
        uploader: AudioUploader,
        cache: CacheService,
        captions: CaptionRenderer,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._bot = bot
        self._spotify = spotify
        self._soundcloud = soundcloud
        self._downloader = downloader
        self._uploader = uploader
        self._cache = cache
        self._captions = captions
        self._session_factory = session_factory
        self._upload_channel_id = settings.UPLOAD_CHANNEL_ID

    async def run(self, request: AlbumDeliveryRequest) -> None:
        raw = await self._cache.get_albums(request.token)
        if not raw:
            await self._report(request, self._captions.album_error("results expired, run /album again"))
            return

        albums = [AlbumInfo(**item) for item in raw]
        if request.index >= len(albums):
            return
        album = albums[request.index]

        cached = await self._cache.get_album_audio(album.source, album.album_id)
        if cached:
            items = [AudioMessage(**entry) for entry in cached]
            await self._finalize(request, album, items, len(items))
            await self._record_download(request.user_id, album)
            return

        try:
            tracks = await self._fetch_tracks(album)
        except Exception:
            logger.exception("Album tracklist failed for %s", album.album_id)
            await self._report(request, self._captions.album_error("failed to load tracklist"))
            return

        if not tracks:
            await self._report(request, self._captions.album_error("album has no tracks"))
            return

        items = await self._download_all(request, album, tracks)
        if not items:
            await self._report(
                request, self._captions.album_error("couldn't download any track from this album")
            )
            return

        if len(items) == len(tracks):
            await self._cache.set_album_audio(
                album.source, album.album_id, [dataclasses.asdict(item) for item in items]
            )

        await self._finalize(request, album, items, len(tracks))
        await self._record_download(request.user_id, album)

    async def _fetch_tracks(self, album: AlbumInfo) -> list[TrackInfo]:
        if album.source == "soundcloud":
            return await self._soundcloud.get_tracks(album.album_id)
        if self._spotify is None:
            raise RuntimeError("Spotify album service unavailable")
        return await self._spotify.get_tracks(album.album_id)

    async def _download_all(
        self, request: AlbumDeliveryRequest, album: AlbumInfo, tracks: list[TrackInfo]
    ) -> list[AudioMessage]:
        total = len(tracks)
        results: list[AudioMessage | None] = [None] * total
        done = 0
        last_edit = 0.0
        lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

        async def edit_progress(force: bool = False) -> None:
            nonlocal last_edit
            now = time.monotonic()
            if not force and now - last_edit < _PROGRESS_MIN_INTERVAL:
                return
            last_edit = now
            await self._report(request, self._captions.album_progress(album, done, total))

        async def worker(index: int, track: TrackInfo) -> None:
            nonlocal done
            async with semaphore:
                file_id = await self._resolve_track(track)
            async with lock:
                done += 1
                if file_id:
                    results[index] = AudioMessage(
                        source=track.source,
                        video_id=track.video_id,
                        performer=track.performer,
                        title=track.title,
                        file_id=file_id,
                    )
            await edit_progress()

        await edit_progress(force=True)
        await asyncio.gather(*(worker(index, track) for index, track in enumerate(tracks)))

        return [item for item in results if item is not None]

    async def _finalize(
        self,
        request: AlbumDeliveryRequest,
        album: AlbumInfo,
        items: list[AudioMessage],
        total: int,
    ) -> None:
        header = self._captions.album_done(album, len(items), total)
        await self._send_audios(request.chat_id, album, items, header)
        with contextlib.suppress(TelegramBadRequest):
            await self._bot.delete_message(request.chat_id, request.picker_message_id)

    async def _resolve_track(self, track: TrackInfo) -> str | None:
        cached = await self._cache.get_file_id(track.source, track.video_id)
        if cached:
            return cached

        tmp_dir = tempfile.mkdtemp(prefix="tantunes_album_")
        try:
            path = await self._downloader.download(
                DownloadRequest(
                    url=track.url,
                    output_dir=tmp_dir,
                    title=track.title,
                    artist=track.performer,
                    isrc=track.isrc,
                    expected_duration=track.duration,
                    expected_title=track.title,
                    expected_artist=track.performer,
                    use_deezer=track.source == "spotify",
                )
            )
            item = AudioMessage(
                source=track.source,
                video_id=track.video_id,
                performer=track.performer,
                title=track.title,
                url=track.url,
                thumbnail_url=track.thumbnail,
            )
            return await self._uploader.upload(item, path, self._upload_channel_id, silent=True)
        except Exception:
            logger.warning("Album track failed: %s — %s", track.performer, track.title, exc_info=True)
            return None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def _send_audios(
        self, chat_id: int, album: AlbumInfo, items: list[AudioMessage], header: str
    ) -> None:
        tracks_per_message = _RICH_MEDIA_LIMIT - 1
        for start in range(0, len(items), tracks_per_message):
            chunk = items[start : start + tracks_per_message]
            if start > 0:
                await self._send_rich(chat_id, self._rich_album(chunk, start))
                continue
            try:
                await self._send_rich(chat_id, self._rich_album(chunk, start, header, album.cover))
            except TelegramBadRequest:
                logger.warning("Album cover rejected, sending without it: %s", album.cover, exc_info=True)
                await self._send_rich(chat_id, self._rich_album(chunk, start, header))

    async def _send_rich(self, chat_id: int, rich_message: InputRichMessage) -> None:
        await self._bot.send_rich_message(chat_id, rich_message=rich_message)

    def _rich_album(
        self,
        items: list[AudioMessage],
        offset: int,
        header: str | None = None,
        cover: str | None = None,
    ) -> InputRichMessage:
        html_parts: list[str] = []
        media: list[InputRichMessageMedia] = []
        if cover:
            html_parts.append(f'<img src="tg://photo?id={_COVER_MEDIA_ID}"/>')
            media.append(InputRichMessageMedia(id=_COVER_MEDIA_ID, media=InputMediaPhoto(media=cover)))
        if header:
            header_html = header.replace("\n", "<br>")
            html_parts.append(f"<p>{header_html}</p>")

        for index, item in enumerate(items, start=offset):
            media_id = f"t{index}"
            html_parts.append(f'<audio src="tg://audio?id={media_id}"></audio>')
            media.append(
                InputRichMessageMedia(
                    id=media_id,
                    media=InputMediaAudio(
                        media=item.file_id, title=item.title, performer=item.performer
                    ),
                )
            )
        return InputRichMessage(html="".join(html_parts), media=media)

    async def _report(self, request: AlbumDeliveryRequest, caption: str) -> None:
        with contextlib.suppress(TelegramBadRequest):
            await self._bot.edit_message_caption(
                chat_id=request.chat_id,
                message_id=request.picker_message_id,
                caption=caption,
                parse_mode="HTML",
            )

    async def _record_download(self, user_id: int, album: AlbumInfo) -> None:
        async with self._session_factory() as session:
            tracking = TrackingService(
                UserRepository(session),
                DownloadRepository(session),
                SearchRepository(session),
            )
            await tracking.record_download(user_id, album.source, album.artist, album.title)
            await session.commit()
