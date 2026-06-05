import logging
from typing import Any

from aiogram import Bot
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import settings
from bot.core.container import create_container
from bot.core.db import init_db
from bot.queue.jobs import download_album, download_track
from bot.services.album import AlbumService
from bot.services.cache import CacheService
from bot.services.download import DownloaderService
from bot.services.soundcloud_album import SoundCloudAlbumService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_MAX_JOBS = 5
_JOB_TIMEOUT = 600


async def startup(ctx: dict[str, Any]) -> None:
    await init_db()
    container = create_container()
    ctx["container"] = container
    ctx["bot"] = await container.get(Bot)
    ctx["cache"] = await container.get(CacheService)
    ctx["downloader"] = await container.get(DownloaderService)
    ctx["album_service"] = await container.get(AlbumService | None)
    ctx["soundcloud_album_service"] = await container.get(SoundCloudAlbumService)
    ctx["session_factory"] = await container.get(async_sessionmaker[AsyncSession])
    ctx["upload_channel_id"] = settings.UPLOAD_CHANNEL_ID


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["container"].close()


class WorkerSettings:
    functions = [download_track, download_album]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = _MAX_JOBS
    job_timeout = _JOB_TIMEOUT
    keep_result = 0
