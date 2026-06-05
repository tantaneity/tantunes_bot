import logging

from aiogram import Router
from aiogram.types import ChosenInlineResult
from arq import ArqRedis
from dishka.integrations.aiogram import FromDishka, inject

from bot.services.cache import CacheService
from bot.services.delivery import AudioMessage, AudioMessenger
from bot.services.tracker import TrackingService

router = Router()
logger = logging.getLogger(__name__)


@router.chosen_inline_result()
@inject
async def handle_chosen_result(
    result: ChosenInlineResult,
    cache: FromDishka[CacheService],
    messenger: FromDishka[AudioMessenger],
    tracking: FromDishka[TrackingService],
    arq: FromDishka[ArqRedis],
) -> None:
    parts = result.result_id.split(":", 1)
    if len(parts) != 2:
        return

    source, video_id = parts
    user_id = result.from_user.id
    inline_message_id = result.inline_message_id

    await tracking.record_user(user_id, result.from_user.username)

    file_id = await cache.get_file_id(source, video_id)
    if file_id:
        meta = await cache.get_track_meta(source, video_id) or {}
        await tracking.record_download(
            user_id, source, meta.get("performer", "Unknown"), meta.get("title", "Unknown")
        )
        if inline_message_id:
            item = AudioMessage.from_meta(source, video_id, meta, file_id)
            await messenger.edit_inline_audio(inline_message_id, item)
        return

    if not inline_message_id:
        return

    await arq.enqueue_job(
        "download_track",
        user_id=user_id,
        chat_id=user_id,
        message_id=None,
        inline_message_id=inline_message_id,
        source=source,
        video_id=video_id,
        _job_id=f"track:{source}:{video_id}:{inline_message_id}",
    )
