from aiogram import Bot
from aiogram.types import FSInputFile

from bot.services.cache import CacheService
from bot.services.delivery.media import thumbnail_file
from bot.services.delivery.message import AudioMessage


class AudioUploader:
    def __init__(self, bot: Bot, cache: CacheService) -> None:
        self._bot = bot
        self._cache = cache

    async def upload(
        self, item: AudioMessage, path: str, target_chat: int, silent: bool
    ) -> str:
        audio = FSInputFile(path, filename=f"{item.performer} - {item.title}.mp3")
        kwargs = {"disable_notification": True} if silent else {}
        uploaded = await self._bot.send_audio(
            target_chat,
            audio=audio,
            title=item.title,
            performer=item.performer,
            thumbnail=thumbnail_file(item.thumbnail_url),
            **kwargs,
        )
        file_id = uploaded.audio.file_id
        await self._cache.set_file_id(item.source, item.video_id, file_id)
        return file_id
