import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dishka.integrations.aiogram import setup_dishka

from bot.config import settings
from bot.core.container import create_container
from bot.core.db import init_db
from bot.handlers import admin, callbacks, chosen, commands, inline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


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

    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "inline_query", "callback_query", "chosen_inline_result"],
        )
    finally:
        await container.close()


if __name__ == "__main__":
    asyncio.run(main())
