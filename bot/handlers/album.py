import asyncio
import dataclasses
import logging
import secrets
from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from dishka.integrations.aiogram import FromDishka, inject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.emoji import DOWNLOAD_EMOJI_ID, ERROR, MUSIC
from bot.models.album import AlbumInfo
from bot.repositories.stats import DownloadRepository, SearchRepository
from bot.repositories.user import UserRepository
from bot.services.album import AlbumService
from bot.services.album_delivery import deliver_album
from bot.services.cache import CacheService
from bot.services.downloader import DownloaderService
from bot.services.tracker import TrackingService

router = Router()
logger = logging.getLogger(__name__)

_SEARCH_LIMIT = 8
_TOKEN_BYTES = 4
_EXPIRED_MESSAGE = "results expired, run /album again"


def _album_caption(album: AlbumInfo, index: int, total: int) -> str:
    counter = f" · {index + 1}/{total}" if total > 1 else ""
    return (
        f"{MUSIC} <b>{escape(album.artist)} — {escape(album.title)}</b>\n"
        f"{album.year} · {album.track_count} tracks{counter}"
    )


def _picker_keyboard(token: str, index: int, total: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="download",
                callback_data=f"ab:d:{token}:{index}",
                icon_custom_emoji_id=DOWNLOAD_EMOJI_ID,
            )
        ]
    ]
    if total > 1:
        prev_index = (index - 1) % total
        next_index = (index + 1) % total
        rows.append(
            [
                InlineKeyboardButton(text="‹", callback_data=f"ab:p:{token}:{prev_index}"),
                InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="ab:noop"),
                InlineKeyboardButton(text="›", callback_data=f"ab:p:{token}:{next_index}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _load_albums(cache: CacheService, token: str) -> list[AlbumInfo] | None:
    raw = await cache.get_albums(token)
    if not raw:
        return None
    return [AlbumInfo(**item) for item in raw]


@router.message(Command("album"))
@inject
async def handle_album(
    message: Message,
    command: CommandObject,
    album_service: FromDishka[AlbumService | None],
    cache: FromDishka[CacheService],
    tracking: FromDishka[TrackingService],
) -> None:
    if album_service is None:
        await message.answer(f"{ERROR} album search needs Spotify configured")
        return

    query = (command.args or "").strip()
    if not query:
        await message.answer("usage: <code>/album artist - album</code>")
        return

    await tracking.record_user(message.from_user.id, message.from_user.username)

    try:
        albums = await album_service.search_albums(query, _SEARCH_LIMIT)
    except Exception:
        logger.exception("Album search failed for %r", query)
        await message.answer(f"{ERROR} search failed, try again")
        return

    albums = [album for album in albums if album.cover]
    if not albums:
        await message.answer(f"{ERROR} nothing found")
        return

    token = secrets.token_hex(_TOKEN_BYTES)
    await cache.set_albums(token, [dataclasses.asdict(album) for album in albums])

    await message.answer_photo(
        photo=albums[0].cover,
        caption=_album_caption(albums[0], 0, len(albums)),
        reply_markup=_picker_keyboard(token, 0, len(albums)),
    )


@router.callback_query(lambda c: c.data == "ab:noop")
async def handle_album_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("ab:p:"))
@inject
async def handle_album_page(
    callback: CallbackQuery,
    cache: FromDishka[CacheService],
) -> None:
    _, _, token, raw_index = callback.data.split(":")
    albums = await _load_albums(cache, token)
    if not albums:
        await callback.answer(_EXPIRED_MESSAGE, show_alert=True)
        return

    index = int(raw_index) % len(albums)
    album = albums[index]
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=album.cover,
                caption=_album_caption(album, index, len(albums)),
                parse_mode="HTML",
            ),
            reply_markup=_picker_keyboard(token, index, len(albums)),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("ab:d:"))
@inject
async def handle_album_download(
    callback: CallbackQuery,
    bot: Bot,
    cache: FromDishka[CacheService],
    downloader: FromDishka[DownloaderService],
    album_service: FromDishka[AlbumService | None],
    session_factory: FromDishka[async_sessionmaker[AsyncSession]],
    s: FromDishka[Settings],
) -> None:
    _, _, token, raw_index = callback.data.split(":")
    albums = await _load_albums(cache, token)
    if not albums or album_service is None:
        await callback.answer(_EXPIRED_MESSAGE, show_alert=True)
        return

    if not s.UPLOAD_CHANNEL_ID:
        await callback.answer("album download needs UPLOAD_CHANNEL_ID configured", show_alert=True)
        return

    index = int(raw_index) % len(albums)
    album = albums[index]
    await callback.answer("downloading…")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass

    asyncio.create_task(
        _run_album_download(
            bot=bot,
            chat_id=callback.message.chat.id,
            picker_message_id=callback.message.message_id,
            album=album,
            album_service=album_service,
            cache=cache,
            downloader=downloader,
            session_factory=session_factory,
            user_id=callback.from_user.id,
            upload_channel_id=s.UPLOAD_CHANNEL_ID,
        ),
        name=f"album:{album.album_id}",
    )


async def _run_album_download(
    *,
    bot: Bot,
    chat_id: int,
    picker_message_id: int,
    album: AlbumInfo,
    album_service: AlbumService,
    cache: CacheService,
    downloader: DownloaderService,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    upload_channel_id: int,
) -> None:
    try:
        tracks = await album_service.get_tracks(album.album_id)
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
        downloader=downloader,
        upload_channel_id=upload_channel_id,
    )

    if delivered:
        async with session_factory() as session:
            tracking = TrackingService(
                UserRepository(session),
                DownloadRepository(session),
                SearchRepository(session),
            )
            await tracking.record_download(user_id, "spotify", album.artist, album.title)
            await session.commit()


async def _safe_caption(bot: Bot, chat_id: int, message_id: int, text: str) -> None:
    try:
        await bot.edit_message_caption(
            chat_id=chat_id, message_id=message_id, caption=text, parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass
