import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dishka.integrations.aiogram import setup_dishka

from bot.config import settings
from bot.core.container import create_container
from bot.core.db import init_db
from bot.emoji import DOWNLOAD_EMOJI_ID, MUSIC_EMOJI_ID, SOURCE_EMOJI_IDS
from bot.handlers import admin, callbacks, chosen, commands, inline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_emoji_logger = logging.getLogger("bot.emoji")


async def _validate_emoji_ids(bot: Bot) -> None:
    all_ids = [MUSIC_EMOJI_ID, DOWNLOAD_EMOJI_ID, *SOURCE_EMOJI_IDS.values()]
    try:
        stickers = await bot.get_custom_emoji_stickers(all_ids)
        valid = {s.custom_emoji_id for s in stickers}
        for emoji_id in all_ids:
            if emoji_id in valid:
                sticker = next(s for s in stickers if s.custom_emoji_id == emoji_id)
                _emoji_logger.info("✓ emoji %s → %s", emoji_id, sticker.emoji)
            else:
                _emoji_logger.warning("✗ INVALID emoji id: %s", emoji_id)
    except Exception:
        _emoji_logger.exception("Failed to validate custom emoji IDs")


async def main() -> None:
    await init_db()

    container = create_container()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    setup_dishka(container, router=dp)

    dp.include_router(commands.router)
    dp.include_router(admin.router)
    dp.include_router(inline.router)
    dp.include_router(chosen.router)
    dp.include_router(callbacks.router)

    await _validate_emoji_ids(bot)

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "inline_query", "callback_query", "chosen_inline_result"],
        )
    finally:
        await container.close()


if __name__ == "__main__":
    asyncio.run(main())
