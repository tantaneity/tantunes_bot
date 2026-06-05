import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from arq import ArqRedis
from dishka.integrations.aiogram import FromDishka, inject

from bot.services.cache import CacheService
from bot.services.sender import (
    edit_inline_audio,
    processing_message,
    send_chat_audio,
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
    tracking: FromDishka[TrackingService],
    arq: FromDishka[ArqRedis],
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

        if inline_message_id:
            await edit_inline_audio(
                bot,
                inline_message_id=inline_message_id,
                file_id=file_id,
                title=title,
                performer=performer,
                source=source,
                thumbnail=thumb,
                video_id=video_id,
                url=url,
            )
        else:
            await send_chat_audio(
                bot,
                chat_id=chat_id,
                file_id=file_id,
                title=title,
                performer=performer,
                source=source,
                thumbnail=thumb,
                video_id=video_id,
                url=url,
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

    await arq.enqueue_job(
        "download_track",
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        inline_message_id=inline_message_id,
        source=source,
        video_id=video_id,
        _job_id=f"track:{source}:{video_id}:{inline_message_id or f'{chat_id}:{message_id}'}",
    )
