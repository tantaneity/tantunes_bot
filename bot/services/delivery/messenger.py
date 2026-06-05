import asyncio
import logging
from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaAudio

from bot.emoji import DOWNLOAD_EMOJI_ID
from bot.keyboards import track_keyboard
from bot.services.delivery.captions import CaptionRenderer
from bot.services.delivery.media import thumbnail_file
from bot.services.delivery.message import AudioMessage

logger = logging.getLogger(__name__)


class AudioMessenger:
    def __init__(self, bot: Bot, captions: CaptionRenderer) -> None:
        self._bot = bot
        self._captions = captions

    async def edit_inline_audio(self, inline_message_id: str, item: AudioMessage) -> None:
        try:
            await self._bot.edit_message_media(
                media=self._input_media(item),
                inline_message_id=inline_message_id,
                reply_markup=self._track_keyboard(item),
            )
        except TelegramBadRequest:
            pass

    async def send_chat_audio(self, chat_id: int, item: AudioMessage) -> None:
        await self._bot.send_audio(
            chat_id,
            audio=item.file_id,
            title=item.title,
            performer=item.performer,
            thumbnail=thumbnail_file(item.thumbnail_url),
            caption=self._captions.track(item.source, item.performer, item.title),
            parse_mode="HTML",
            reply_markup=self._track_keyboard(item),
        )

    async def edit_progress(
        self, inline_message_id: str, source: str, video_id: str, percent: int
    ) -> None:
        try:
            await self._bot.edit_message_reply_markup(
                inline_message_id=inline_message_id,
                reply_markup=self._progress_keyboard(source, video_id, percent),
            )
        except TelegramBadRequest:
            pass

    def progress_callback(
        self, inline_message_id: str, source: str, video_id: str
    ) -> Callable[[int], None]:
        loop = asyncio.get_running_loop()

        def on_progress(percent: int) -> None:
            future = asyncio.run_coroutine_threadsafe(
                self.edit_progress(inline_message_id, source, video_id, percent), loop
            )
            future.add_done_callback(lambda f: None if f.cancelled() else f.exception())

        return on_progress

    async def show_text(
        self,
        *,
        text: str,
        chat_id: int | None = None,
        message_id: int | None = None,
        inline_message_id: str | None = None,
    ) -> None:
        try:
            if message_id is not None:
                await self._bot.edit_message_text(
                    text, chat_id=chat_id, message_id=message_id, parse_mode="HTML"
                )
            elif inline_message_id is not None:
                await self._bot.edit_message_text(
                    text, inline_message_id=inline_message_id, parse_mode="HTML"
                )
        except TelegramBadRequest:
            pass

    async def delete(self, chat_id: int, message_id: int) -> None:
        try:
            await self._bot.delete_message(chat_id, message_id)
        except TelegramBadRequest:
            pass

    def _track_keyboard(self, item: AudioMessage) -> InlineKeyboardMarkup | None:
        return track_keyboard(self._captions.track_url(item.source, item.video_id, item.url))

    def _input_media(self, item: AudioMessage) -> InputMediaAudio:
        return InputMediaAudio(
            media=item.file_id,
            title=item.title,
            performer=item.performer,
            thumbnail=thumbnail_file(item.thumbnail_url),
            caption=self._captions.track(item.source, item.performer, item.title),
            parse_mode="HTML",
        )

    def _progress_keyboard(self, source: str, video_id: str, percent: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"{percent}%",
                        callback_data=f"dl:{source}:{video_id}",
                        icon_custom_emoji_id=DOWNLOAD_EMOJI_ID,
                    )
                ]
            ]
        )
