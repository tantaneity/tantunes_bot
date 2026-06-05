import asyncio
import logging
import shutil
import tempfile
import time
from collections.abc import Iterator
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InputMediaAudio

from bot.emoji import ERROR, MUSIC
from bot.models.album import AlbumInfo
from bot.models.track import TrackInfo
from bot.services.cache import CacheService
from bot.services.download import DownloaderService, DownloadRequest
from bot.services.sender import thumbnail_file

logger = logging.getLogger(__name__)

_MAX_CONCURRENCY = 3
_MEDIA_GROUP_SIZE = 10
_PROGRESS_MIN_INTERVAL = 1.5


def _bar(done: int, total: int, width: int = 10) -> str:
    filled = round(width * done / total) if total else 0
    return "█" * filled + "░" * (width - filled)


def _progress_caption(album: AlbumInfo, done: int, total: int) -> str:
    return (
        f"{MUSIC} <b>{escape(album.artist)} — {escape(album.title)}</b>\n"
        f"<code>{_bar(done, total)}</code> {done}/{total}"
    )


def _done_caption(album: AlbumInfo, delivered: int, total: int) -> str:
    tail = f"{delivered}/{total} tracks" if delivered != total else f"{total} tracks"
    return (
        f"{MUSIC} <b>{escape(album.artist)} — {escape(album.title)}</b>\n"
        f"{album.year} · {tail}"
    )


def _chunks(items: list[InputMediaAudio]) -> Iterator[list[InputMediaAudio]]:
    for start in range(0, len(items), _MEDIA_GROUP_SIZE):
        yield items[start : start + _MEDIA_GROUP_SIZE]


async def _download_track(
    track: TrackInfo,
    cache: CacheService,
    downloader: DownloaderService,
    bot: Bot,
    upload_channel_id: int,
) -> str | None:
    cached = await cache.get_file_id(track.source, track.video_id)
    if cached:
        return cached

    tmp_dir = tempfile.mkdtemp(prefix="tantunes_album_")
    try:
        request = DownloadRequest(
            url=track.url,
            output_dir=tmp_dir,
            title=track.title,
            artist=track.performer,
            isrc=track.isrc,
            expected_duration=track.duration,
            expected_title=track.title,
            expected_artist=track.performer,
            use_deezer=track.source == "spotify",
        )
        mp3_path = await downloader.download(request)

        audio_data = FSInputFile(mp3_path, filename=f"{track.performer} - {track.title}.mp3")

        uploaded = await bot.send_audio(
            upload_channel_id,
            audio=audio_data,
            title=track.title,
            performer=track.performer,
            thumbnail=thumbnail_file(track.thumbnail),
            disable_notification=True,
        )
        file_id = uploaded.audio.file_id
        await cache.set_file_id(track.source, track.video_id, file_id)
        return file_id
    except Exception:
        logger.warning(
            "Album track failed: %s — %s", track.performer, track.title, exc_info=True
        )
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _send_audios(
    bot: Bot,
    chat_id: int,
    album: AlbumInfo,
    ordered: list[tuple[TrackInfo, str]],
) -> None:
    items: list[InputMediaAudio] = []
    for index, (track, file_id) in enumerate(ordered):
        caption = (
            f"{MUSIC} <b>{escape(album.artist)} — {escape(album.title)}</b>"
            if index == 0
            else None
        )
        items.append(
            InputMediaAudio(
                media=file_id,
                title=track.title,
                performer=track.performer,
                caption=caption,
                parse_mode="HTML" if caption else None,
            )
        )

    if len(items) == 1:
        only = items[0]
        await bot.send_audio(
            chat_id,
            audio=only.media,
            title=only.title,
            performer=only.performer,
            caption=only.caption,
            parse_mode="HTML",
        )
        return

    for chunk in _chunks(items):
        await bot.send_media_group(chat_id, media=chunk)


async def deliver_album(
    *,
    bot: Bot,
    chat_id: int,
    picker_message_id: int,
    album: AlbumInfo,
    tracks: list[TrackInfo],
    cache: CacheService,
    downloader: DownloaderService,
    upload_channel_id: int,
) -> int:
    total = len(tracks)
    file_ids: list[str | None] = [None] * total
    done = 0
    last_edit = 0.0
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _edit_progress(force: bool = False) -> None:
        nonlocal last_edit
        now = time.monotonic()
        if not force and now - last_edit < _PROGRESS_MIN_INTERVAL:
            return
        last_edit = now
        try:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=picker_message_id,
                caption=_progress_caption(album, done, total),
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            pass

    async def _worker(index: int, track: TrackInfo) -> None:
        nonlocal done
        async with semaphore:
            file_id = await _download_track(track, cache, downloader, bot, upload_channel_id)
        async with lock:
            done += 1
            file_ids[index] = file_id
        await _edit_progress()

    await _edit_progress(force=True)
    await asyncio.gather(*(_worker(i, t) for i, t in enumerate(tracks)))

    ordered = [(tracks[i], fid) for i, fid in enumerate(file_ids) if fid]
    if not ordered:
        try:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=picker_message_id,
                caption=f"{ERROR} couldn't download any track from this album",
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            pass
        return 0

    await _send_audios(bot, chat_id, album, ordered)

    try:
        await bot.edit_message_caption(
            chat_id=chat_id,
            message_id=picker_message_id,
            caption=_done_caption(album, len(ordered), total),
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        pass

    return len(ordered)
