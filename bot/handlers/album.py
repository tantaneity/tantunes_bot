import asyncio
import contextlib
import dataclasses
import logging
import secrets

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from arq import ArqRedis
from dishka.integrations.aiogram import FromDishka, inject
from rapidfuzz import fuzz

from bot.config import Settings
from bot.emoji import DOWNLOAD_EMOJI_ID, ERROR, PROCESSING
from bot.models.album import AlbumInfo
from bot.services.album import AlbumService
from bot.services.cache import CacheService
from bot.services.delivery import CaptionRenderer
from bot.services.soundcloud_album import SoundCloudAlbumService
from bot.services.tracker import TrackingService

router = Router()
logger = logging.getLogger(__name__)

_SPOTIFY_LIMIT = 8
_SOUNDCLOUD_LIMIT = 5
_GALLERY_LIMIT = 8
_SPOTIFY_TIMEOUT = 10.0
_SOUNDCLOUD_TIMEOUT = 30.0
_MIN_MERGE_SCORE = 55
_TOKEN_BYTES = 4
_EXPIRED_MESSAGE = "results expired, run /album again"


def _is_soundcloud_album_url(text: str) -> bool:
    return (
        text.startswith(("http://", "https://"))
        and "soundcloud.com" in text
        and "/sets/" in text
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
    soundcloud_album_service: FromDishka[SoundCloudAlbumService],
    cache: FromDishka[CacheService],
    captions: FromDishka[CaptionRenderer],
    tracking: FromDishka[TrackingService],
) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer(
            "usage: <code>/album artist - album</code>\n"
            "or paste a SoundCloud album link"
        )
        return

    await tracking.record_user(message.from_user.id, message.from_user.username)

    if _is_soundcloud_album_url(query):
        await _handle_link(message, cache, captions, soundcloud_album_service, query)
        return

    await _handle_text_search(
        message, cache, captions, album_service, soundcloud_album_service, query
    )


async def _present_albums(
    message: Message, cache: CacheService, captions: CaptionRenderer, albums: list[AlbumInfo]
) -> None:
    token = secrets.token_hex(_TOKEN_BYTES)
    await cache.set_albums(token, [dataclasses.asdict(album) for album in albums])
    await message.answer_photo(
        photo=albums[0].cover,
        caption=captions.album(albums[0], 0, len(albums)),
        reply_markup=_picker_keyboard(token, 0, len(albums)),
    )


async def _handle_link(
    message: Message,
    cache: CacheService,
    captions: CaptionRenderer,
    service: SoundCloudAlbumService,
    url: str,
) -> None:
    try:
        album = await service.fetch_album(url)
    except Exception:
        logger.exception("SoundCloud album failed for %r", url)
        album = None

    if not album or not album.cover:
        await message.answer(f"{ERROR} couldn't read that SoundCloud album")
        return
    await _present_albums(message, cache, captions, [album])


async def _handle_text_search(
    message: Message,
    cache: CacheService,
    captions: CaptionRenderer,
    spotify: AlbumService | None,
    soundcloud: SoundCloudAlbumService,
    query: str,
) -> None:
    status = await message.answer(f"{PROCESSING} searching albums…")
    albums = await _resolve_album_search(cache, spotify, soundcloud, query)
    if not albums:
        await status.edit_text(f"{ERROR} nothing found")
        return
    await _present_albums(message, cache, captions, albums)
    await status.delete()


async def _resolve_album_search(
    cache: CacheService,
    spotify: AlbumService | None,
    soundcloud: SoundCloudAlbumService,
    query: str,
) -> list[AlbumInfo]:
    cached = await cache.get_album_search(query)
    if cached is not None:
        return [AlbumInfo(**item) for item in cached]

    albums = await _search_albums(spotify, soundcloud, query)
    if albums:
        await cache.set_album_search(query, [dataclasses.asdict(album) for album in albums])
    return albums


async def _search_albums(
    spotify: AlbumService | None, soundcloud: SoundCloudAlbumService, query: str
) -> list[AlbumInfo]:
    tasks = [_safe_search(soundcloud.search_albums(query, _SOUNDCLOUD_LIMIT), _SOUNDCLOUD_TIMEOUT)]
    if spotify is not None:
        tasks.append(_safe_search(spotify.search_albums(query, _SPOTIFY_LIMIT), _SPOTIFY_TIMEOUT))

    gathered = await asyncio.gather(*tasks)
    albums = [album for group in gathered for album in group if album.cover]
    return _rank(query, albums)[:_GALLERY_LIMIT]


async def _safe_search(coro, timeout: float) -> list[AlbumInfo]:
    try:
        return await asyncio.wait_for(coro, timeout)
    except Exception:
        logger.warning("Album source failed", exc_info=True)
        return []


def _rank(query: str, albums: list[AlbumInfo]) -> list[AlbumInfo]:
    target = query.lower()
    scored = [
        (fuzz.token_sort_ratio(target, f"{album.artist} {album.title}".lower()), album)
        for album in albums
    ]
    relevant = [pair for pair in scored if pair[0] >= _MIN_MERGE_SCORE]
    relevant.sort(key=lambda pair: pair[0], reverse=True)
    return [album for _, album in relevant]


@router.callback_query(lambda c: c.data == "ab:noop")
async def handle_album_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("ab:p:"))
@inject
async def handle_album_page(
    callback: CallbackQuery,
    cache: FromDishka[CacheService],
    captions: FromDishka[CaptionRenderer],
) -> None:
    _, _, token, raw_index = callback.data.split(":")
    albums = await _load_albums(cache, token)
    if not albums:
        await callback.answer(_EXPIRED_MESSAGE, show_alert=True)
        return

    index = int(raw_index) % len(albums)
    album = albums[index]
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=album.cover,
                caption=captions.album(album, index, len(albums)),
                parse_mode="HTML",
            ),
            reply_markup=_picker_keyboard(token, index, len(albums)),
        )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("ab:d:"))
@inject
async def handle_album_download(
    callback: CallbackQuery,
    cache: FromDishka[CacheService],
    s: FromDishka[Settings],
    arq: FromDishka[ArqRedis],
) -> None:
    _, _, token, raw_index = callback.data.split(":")
    albums = await _load_albums(cache, token)
    if not albums:
        await callback.answer(_EXPIRED_MESSAGE, show_alert=True)
        return

    if not s.UPLOAD_CHANNEL_ID:
        await callback.answer("album download needs UPLOAD_CHANNEL_ID configured", show_alert=True)
        return

    index = int(raw_index) % len(albums)
    await callback.answer("queued…")

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)

    await arq.enqueue_job(
        "download_album",
        token=token,
        index=index,
        chat_id=callback.message.chat.id,
        picker_message_id=callback.message.message_id,
        user_id=callback.from_user.id,
        _job_id=f"album:{token}:{index}",
    )
