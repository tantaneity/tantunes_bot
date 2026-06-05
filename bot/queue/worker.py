import logging
from typing import Any

from arq.connections import RedisSettings

from bot.config import settings
from bot.core.container import create_container
from bot.core.db import init_db
from bot.queue.jobs import download_album, download_track
from bot.services.delivery import AlbumDeliveryService, TrackDeliveryService

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
    ctx["track_delivery"] = await container.get(TrackDeliveryService)
    ctx["album_delivery"] = await container.get(AlbumDeliveryService)


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
