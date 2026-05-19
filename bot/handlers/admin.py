from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from dishka.integrations.aiogram import FromDishka, inject

from bot.config import Settings
from bot.services.stats import StatsService

router = Router()


@router.message(Command("stats"))
@inject
async def handle_stats(
    message: Message,
    stats_service: FromDishka[StatsService],
    s: FromDishka[Settings],
) -> None:
    if message.from_user.id not in s.admin_ids:
        return

    data = await stats_service.fetch()
    chart = await stats_service.build_chart(data)

    await message.answer_photo(
        BufferedInputFile(chart, filename="stats.png"),
        caption=stats_service.format_text(data),
    )
