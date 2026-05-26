import asyncio
import logging

from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedAudio,
    InputTextMessageContent,
)
from dishka.integrations.aiogram import FromDishka, inject

from bot.emoji import DOWNLOAD_EMOJI_ID, SOURCE_LABEL
from bot.keyboards import track_keyboard
from bot.services.cache import CacheService
from bot.services.sender import build_caption_html, display_track_url, processing_message
from bot.services.search import SearchService
from bot.services.tracker import TrackingService

router = Router()
logger = logging.getLogger(__name__)


def _make_processing_content(source: str | None = None) -> InputTextMessageContent:
    proc_text = processing_message(source)
    return InputTextMessageContent(
        message_text=proc_text,
        parse_mode="HTML",
    )


def _fmt_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


@router.inline_query()
@inject
async def handle_inline_query(
    query: InlineQuery,
    search_service: FromDishka[SearchService],
    cache: FromDishka[CacheService],
    tracking: FromDishka[TrackingService],
) -> None:
    text = query.query.strip()
    if not text:
        await query.answer([], cache_time=1, is_personal=True)
        return

    user_id = query.from_user.id
    await tracking.record_user(user_id, query.from_user.username)
    await tracking.record_search(user_id, text)

    try:
        tracks = await asyncio.wait_for(search_service.search(text), timeout=8.0)
    except asyncio.TimeoutError:
        await query.answer([], cache_time=1, is_personal=True)
        return
    except Exception:
        logger.exception("Search failed for query: %s", text)
        await query.answer([], cache_time=1, is_personal=True)
        return

    results = []
    for track in tracks:
        await cache.set_track_meta(
            track.source,
            track.video_id,
            track.title,
            track.performer,
            track.duration,
            track.url,
            track.thumbnail,
        )

        file_id = await cache.get_file_id(track.source, track.video_id)
        duration_str = _fmt_duration(track.duration)
        src_label = SOURCE_LABEL.get(track.source, track.source.upper())

        if file_id:
            results.append(
                InlineQueryResultCachedAudio(
                    id=f"{track.source}:{track.video_id}",
                    audio_file_id=file_id,
                    caption=build_caption_html(track.source, track.performer, track.title),
                    parse_mode="HTML",
                    reply_markup=track_keyboard(display_track_url(track.source, track.video_id, track.url)),
                )
            )
        else:
            results.append(
                InlineQueryResultArticle(
                    id=f"{track.source}:{track.video_id}",
                    title=f"{track.performer} — {track.title}",
                    description=f"{duration_str} · {src_label}",
                    thumbnail_url=track.thumbnail or None,
                    thumbnail_width=320,
                    thumbnail_height=180,
                    input_message_content=_make_processing_content(track.source),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(
                                text=f"{track.performer} — {track.title}",
                                callback_data=f"dl:{track.source}:{track.video_id}",
                                icon_custom_emoji_id=DOWNLOAD_EMOJI_ID,
                            )
                        ]]
                    ),
                )
            )

    await query.answer(results, cache_time=30, is_personal=True)
