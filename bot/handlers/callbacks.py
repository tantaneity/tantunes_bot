import asyncio
import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InputMediaAudio
from dishka.integrations.aiogram import FromDishka, inject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.keyboards import track_keyboard
from bot.services.cache import CacheService
from bot.services.downloader import DownloaderService
from bot.services.sender import (
    audio_caption,
    deliver_audio,
    display_track_url,
    processing_message,
    thumbnail_file,
)
from bot.services.tracker import TrackingService

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(lambda c: c.data and c.data.startswith("dl:"))
@inject
async def handle_download_callback(
    callback: CallbackQuery,
    bot: Bot,
    cache: FromDishka[CacheService],
    downloader: FromDishka[DownloaderService],
    tracking: FromDishka[TrackingService],
    session_factory: FromDishka[async_sessionmaker[AsyncSession]],
    s: FromDishka[Settings],
) -> None:
    _, source, video_id = callback.data.split(":", 2)
    await callback.answer("Processing…")

    user_id = callback.from_user.id
    await tracking.record_user(user_id, callback.from_user.username)

    if callback.message is not None:
        chat_id = callback.message.chat.id
        message_id = callback.message.message_id
        inline_message_id = None
    else:
        chat_id = user_id
        message_id = None
        inline_message_id = callback.inline_message_id

    file_id = await cache.get_file_id(source, video_id)
    if file_id:
        meta = await cache.get_track_meta(source, video_id) or {}
        title = meta.get("title", "Unknown")
        performer = meta.get("performer", "Unknown")
        url = meta.get("url", "")
        thumb = thumbnail_file(meta.get("thumbnail"))
        await tracking.record_download(user_id, source, performer, title)

        caption = audio_caption(source, performer, title)
        reply_markup = track_keyboard(display_track_url(source, video_id, url))

        if inline_message_id:
            try:
                await bot.edit_message_media(
                    media=InputMediaAudio(
                        media=file_id, title=title, performer=performer, thumbnail=thumb,
                        caption=caption, parse_mode="HTML",
                    ),
                    inline_message_id=inline_message_id,
                    reply_markup=reply_markup,
                )
            except TelegramBadRequest:
                pass
        else:
            await bot.send_audio(
                chat_id, audio=file_id, title=title, performer=performer, thumbnail=thumb,
                caption=caption, parse_mode="HTML",
                reply_markup=reply_markup,
            )
            if message_id:
                try:
                    await bot.delete_message(chat_id, message_id)
                except TelegramBadRequest:
                    pass
        return

    proc_text = processing_message(source)
    try:
        if message_id:
            await callback.message.edit_text(proc_text, parse_mode="HTML")
        elif inline_message_id:
            await bot.edit_message_text(
                proc_text,
                inline_message_id=inline_message_id,
                parse_mode="HTML",
            )
    except TelegramBadRequest:
        pass

    asyncio.create_task(
        deliver_audio(
            bot=bot,
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            inline_message_id=inline_message_id,
            source=source,
            video_id=video_id,
            cache=cache,
            downloader=downloader,
            session_factory=session_factory,
            upload_channel_id=s.UPLOAD_CHANNEL_ID,
        ),
        name=f"dl:{source}:{video_id}",
    )
