import asyncio
import logging

from aiogram import Bot, Router
from aiogram.types import ChosenInlineResult
from dishka.integrations.aiogram import FromDishka, inject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.services.cache import CacheService
from bot.services.downloader import DownloaderService
from bot.services.sender import deliver_audio, display_track_url, edit_inline_audio, thumbnail_file
from bot.services.tracker import TrackingService

router = Router()
logger = logging.getLogger(__name__)


@router.chosen_inline_result()
@inject
async def handle_chosen_result(
    result: ChosenInlineResult,
    bot: Bot,
    cache: FromDishka[CacheService],
    downloader: FromDishka[DownloaderService],
    tracking: FromDishka[TrackingService],
    session_factory: FromDishka[async_sessionmaker[AsyncSession]],
    s: FromDishka[Settings],
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
        title = meta.get("title", "Unknown")
        performer = meta.get("performer", "Unknown")
        url = meta.get("url", "")
        await tracking.record_download(user_id, source, performer, title)
        if inline_message_id:
            await edit_inline_audio(
                bot,
                inline_message_id=inline_message_id,
                file_id=file_id,
                title=title,
                performer=performer,
                source=source,
                thumbnail=thumbnail_file(meta.get("thumbnail")),
                video_id=video_id,
                url=url,
            )
        return

    if not inline_message_id:
        return

    asyncio.create_task(
        deliver_audio(
            bot=bot,
            user_id=user_id,
            chat_id=user_id,
            message_id=None,
            inline_message_id=inline_message_id,
            source=source,
            video_id=video_id,
            cache=cache,
            downloader=downloader,
            session_factory=session_factory,
            upload_channel_id=s.UPLOAD_CHANNEL_ID,
        ),
        name=f"chosen:{source}:{video_id}",
    )
