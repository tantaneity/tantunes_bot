from aiogram.types import URLInputFile


def thumbnail_file(url: str | None) -> URLInputFile | None:
    return URLInputFile(url, filename="thumb.jpg") if url else None
