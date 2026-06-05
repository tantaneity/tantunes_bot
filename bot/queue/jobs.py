import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.emoji import ERROR
from bot.models.album import AlbumInfo
from bot.models.track import TrackInfo
from bot.repositories.stats import DownloadRepository, SearchRepository
from bot.repositories.user import UserRepository
from bot.services.album import AlbumService
from bot.services.album_delivery import deliver_album
from bot.services.cache import CacheService
from bot.services.sender import deliver_audio
from bot.services.soundcloud_album import SoundCloudAlbumService
from bot.services.tracker import TrackingService

logger = logging.getLogger(__name__)


async def download_track(
    ctx: dict[str, Any],
    *,
    user_id: int,
    chat_id: int,
    message_id: int | None,
    inline_message_id: str | None,
    source: str,
    video_id: str,
) -> None:
    await deliver_audio(
        bot=ctx["bot"],
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        inline_message_id=inline_message_id,
        source=source,
        video_id=video_id,
        cache=ctx["cache"],
        downloader=ctx["downloader"],
        session_factory=ctx["session_factory"],
        upload_channel_id=ctx["upload_channel_id"],
    )


async def download_album(
    ctx: dict[str, Any],
    *,
    token: str,
    index: int,
    chat_id: int,
    picker_message_id: int,
    user_id: int,
) -> None:
    bot: Bot = ctx["bot"]
    cache: CacheService = ctx["cache"]

    raw = await cache.get_albums(token)
    if not raw:
        await _safe_caption(bot, chat_id, picker_message_id, f"{ERROR} results expired, run /album again")
        return

    albums = [AlbumInfo(**item) for item in raw]
    if index >= len(albums):
        return
    album = albums[index]

    try:
        tracks = await _fetch_tracks(album, ctx["album_service"], ctx["soundcloud_album_service"])
    except Exception:
        logger.exception("Album tracklist failed for %s", album.album_id)
        await _safe_caption(bot, chat_id, picker_message_id, f"{ERROR} failed to load tracklist")
        return

    if not tracks:
        await _safe_caption(bot, chat_id, picker_message_id, f"{ERROR} album has no tracks")
        return

    delivered = await deliver_album(
        bot=bot,
        chat_id=chat_id,
        picker_message_id=picker_message_id,
        album=album,
        tracks=tracks,
        cache=cache,
        downloader=ctx["downloader"],
        upload_channel_id=ctx["upload_channel_id"],
    )

    if delivered:
        await _record_download(ctx["session_factory"], user_id, album)


async def _fetch_tracks(
    album: AlbumInfo,
    album_service: AlbumService | None,
    soundcloud_album_service: SoundCloudAlbumService,
) -> list[TrackInfo]:
    if album.source == "soundcloud":
        return await soundcloud_album_service.get_tracks(album.album_id)
    if album_service is None:
        raise RuntimeError("Spotify album service unavailable")
    return await album_service.get_tracks(album.album_id)


async def _record_download(
    session_factory: async_sessionmaker[AsyncSession], user_id: int, album: AlbumInfo
) -> None:
    async with session_factory() as session:
        tracking = TrackingService(
            UserRepository(session),
            DownloadRepository(session),
            SearchRepository(session),
        )
        await tracking.record_download(user_id, album.source, album.artist, album.title)
        await session.commit()


async def _safe_caption(bot: Bot, chat_id: int, message_id: int, text: str) -> None:
    try:
        await bot.edit_message_caption(
            chat_id=chat_id, message_id=message_id, caption=text, parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass
