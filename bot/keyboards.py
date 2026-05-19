from urllib.parse import urlsplit
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def track_keyboard(track_url: str | None) -> InlineKeyboardMarkup | None:
    if not _is_http_url(track_url):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔗 track", url=track_url)
    ]])


def _is_http_url(url: str | None) -> bool:
    if not url:
        return False
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)
