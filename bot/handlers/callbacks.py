import logging

from aiogram import Router
from aiogram.types import CallbackQuery
from arq import ArqRedis
from dishka.integrations.aiogram import FromDishka, inject

from bot.services.cache import CacheService
from bot.services.delivery import AudioMessage, AudioMessenger, CaptionRenderer
from bot.services.tracker import TrackingService

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(lambda c: c.data and c.data.startswith("dl:"))
@inject
async def handle_download_callback(
    callback: CallbackQuery,
    cache: FromDishka[CacheService],
    messenger: FromDishka[AudioMessenger],
    captions: FromDishka[CaptionRenderer],
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
        item = AudioMessage.from_meta(source, video_id, meta, file_id)
        await tracking.record_download(user_id, source, item.performer, item.title)

        if inline_message_id:
            await messenger.edit_inline_audio(inline_message_id, item)
        else:
            await messenger.send_chat_audio(chat_id, item)
            if message_id:
                await messenger.delete(chat_id, message_id)
        return

    await messenger.show_text(
        text=captions.processing(),
        chat_id=chat_id,
        message_id=message_id,
        inline_message_id=inline_message_id,
    )

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
