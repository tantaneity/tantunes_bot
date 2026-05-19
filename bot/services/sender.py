import asyncio
import logging
import shutil
import tempfile
from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
    URLInputFile,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.emoji import DOWNLOAD_EMOJI_ID, ERROR, MUSIC, PROCESSING, SOURCE_EMOJI
from bot.keyboards import track_keyboard
from bot.repositories.stats import DownloadRepository, SearchRepository
from bot.repositories.user import UserRepository
from bot.services.cache import CacheService
from bot.services.downloader import DownloaderService
from bot.services.tracker import TrackingService

logger = logging.getLogger(__name__)


def thumbnail_file(url: str | None):
    return URLInputFile(url, filename="thumb.jpg") if url else None


def audio_caption(source: str, performer: str, title: str) -> str:
    src = SOURCE_EMOJI.get(source, source.upper())
    return f'{MUSIC} <b><a href="https://t.me/instantaneity">{performer} — {title}</a></b> · {src}'


def processing_message(source: str | None = None) -> str:
    src = SOURCE_EMOJI.get(source, "") if source else ""
    src_str = f" · {src}" if src else ""
    return f"{PROCESSING} Downloading...{src_str}"


def display_track_url(source: str, video_id: str, download_url: str | None) -> str | None:
    if source == "spotify" and video_id:
        return f"https://open.spotify.com/track/{video_id}"
    if source == "youtube" and video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    if download_url and download_url.startswith(("http://", "https://")):
        return download_url
    return None


def _progress_keyboard(source: str, video_id: str, pct: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=f"{pct}%",
                callback_data=f"dl:{source}:{video_id}",
                icon_custom_emoji_id=DOWNLOAD_EMOJI_ID,
            )
        ]]
    )


def _make_progress_callback(
    bot: Bot,
    loop: asyncio.AbstractEventLoop,
    inline_message_id: str,
    source: str,
    video_id: str,
) -> Callable[[int], None]:
    def on_progress(pct: int) -> None:
        fut = asyncio.run_coroutine_threadsafe(
            bot.edit_message_reply_markup(
                inline_message_id=inline_message_id,
                reply_markup=_progress_keyboard(source, video_id, pct),
            ),
            loop,
        )

        fut.add_done_callback(lambda f: None if f.cancelled() else f.exception())

    return on_progress


async def deliver_audio(
    *,
    bot: Bot,
    user_id: int,
    chat_id: int,
    message_id: int | None,
    inline_message_id: str | None,
    source: str,
    video_id: str,
    cache: CacheService,
    downloader: DownloaderService,
    session_factory: async_sessionmaker[AsyncSession],
    upload_channel_id: int | None,
) -> None:
    tmp_dir = tempfile.mkdtemp(prefix="tantunes_")
    try:
        meta = await cache.get_track_meta(source, video_id) or {}
        title = meta.get("title", "Unknown")
        performer = meta.get("performer", "Unknown")
        url = meta.get("url", "")
        thumb = thumbnail_file(meta.get("thumbnail"))

        if not url:
            raise ValueError(f"No URL in metadata for {source}:{video_id}")

        logger.info("Downloading %s:%s | title=%r | url=%r", source, video_id, title, url)

        on_progress = None
        if inline_message_id:
            loop = asyncio.get_running_loop()
            on_progress = _make_progress_callback(bot, loop, inline_message_id, source, video_id)

        expected_duration = int(meta.get("duration") or 0)
        mp3_path = await downloader.download(
            url, tmp_dir,
            on_progress=on_progress,
            expected_duration=expected_duration,
            expected_title=title,
            expected_artist=performer,
        )

        with open(mp3_path, "rb") as f:
            audio_data = BufferedInputFile(f.read(), filename=f"{performer} - {title}.mp3")

        upload_target = upload_channel_id or chat_id
        upload_kwargs = {"disable_notification": True} if upload_channel_id else {}

        uploaded = await bot.send_audio(
            upload_target,
            audio=audio_data,
            title=title,
            performer=performer,
            thumbnail=thumb,
            **upload_kwargs,
        )
        file_id = uploaded.audio.file_id
        await cache.set_file_id(source, video_id, file_id)

        async with session_factory() as session:
            tracking = TrackingService(
                UserRepository(session),
                DownloadRepository(session),
                SearchRepository(session),
            )
            await tracking.record_download(user_id, source, performer, title)
            await session.commit()

        caption = audio_caption(source, performer, title)
        reply_markup = track_keyboard(display_track_url(source, video_id, url))

        if inline_message_id:
            try:
                await bot.edit_message_media(
                    media=InputMediaAudio(
                        media=file_id,
                        title=title,
                        performer=performer,
                        thumbnail=thumb,
                        caption=caption,
                        parse_mode="HTML",
                    ),
                    inline_message_id=inline_message_id,
                    reply_markup=reply_markup,
                )
            except TelegramBadRequest:
                pass
        else:
            if upload_target != chat_id:
                await bot.send_audio(
                    chat_id,
                    audio=file_id,
                    title=title,
                    performer=performer,
                    thumbnail=thumb,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            if message_id:
                try:
                    await bot.delete_message(chat_id, message_id)
                except TelegramBadRequest:
                    pass

    except TelegramForbiddenError:
        logger.warning("Cannot send to user %s — bot not started", chat_id)
        if inline_message_id:
            try:
                await bot.edit_message_text(
                    f"{ERROR} Start the bot in PM first, then try again.",
                    inline_message_id=inline_message_id,
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                pass
    except Exception:
        logger.exception("Failed to deliver %s:%s", source, video_id)
        try:
            if message_id:
                await bot.edit_message_text(
                    f"{ERROR} Failed to download. Please try again.",
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode="HTML",
                )
            elif inline_message_id:
                await bot.edit_message_text(
                    f"{ERROR} Failed to download. Please try again.",
                    inline_message_id=inline_message_id,
                    parse_mode="HTML",
                )
        except TelegramBadRequest:
            pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
