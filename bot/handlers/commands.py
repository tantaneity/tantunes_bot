from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from dishka.integrations.aiogram import FromDishka, inject

from bot.services.tracker import TrackingService

router = Router()

_START_TEXT = (
    "<b>tantunes</b> — inline music bot\n\n"
    "type <code>@tantunes_bot query</code> in any chat to search"
)

_START_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="channel",
                url="https://t.me/instantaneity",
                icon_custom_emoji_id="5875465628285931233",
            )
        ],
        [
            InlineKeyboardButton(
                text="source",
                url="https://github.com/tantaneity/tantunes_bot",
                icon_custom_emoji_id="5300931211764441870",
            )
        ],
    ]
)


@router.message(Command("start"))
@inject
async def handle_start(
    message: Message,
    tracking: FromDishka[TrackingService],
) -> None:
    await tracking.record_user(message.from_user.id, message.from_user.username)
    await message.answer(_START_TEXT, reply_markup=_START_KEYBOARD)


@router.message(Command("emoji_id"))
async def handle_emoji_id(message: Message) -> None:
    if not message.reply_to_message:
        await message.answer("reply to a message containing custom emoji")
        return

    entities = message.reply_to_message.entities or []
    ids = [
        e.custom_emoji_id
        for e in entities
        if e.type == "custom_emoji" and e.custom_emoji_id
    ]

    if not ids:
        await message.answer("no custom emoji found in that message")
        return

    await message.answer("\n".join(f"<code>{eid}</code>" for eid in ids))
