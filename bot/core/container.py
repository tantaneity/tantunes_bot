from collections.abc import AsyncGenerator, AsyncIterator

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from dishka import Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings, settings
from bot.core.db import AsyncSessionFactory
from bot.repositories.stats import DownloadRepository, SearchRepository
from bot.repositories.user import UserRepository
from bot.services.album import AlbumService
from bot.services.cache import CacheService
from bot.services.deezer import DeezerDownloader
from bot.services.delivery import (
    AlbumDeliveryService,
    AudioMessenger,
    AudioUploader,
    CaptionRenderer,
    TrackDeliveryService,
)
from bot.services.download import DownloaderService
from bot.services.download.deezer_source import DeezerDownloadSource
from bot.services.download.ytdlp_source import YtDlpDownloadSource
from bot.services.search import SearchService, YtDlpProvider
from bot.services.soundcloud_album import SoundCloudAlbumService
from bot.services.stats import StatsService
from bot.services.tracker import TrackingService


class AppProvider(Provider):

    scope = Scope.APP

    @provide
    def get_settings(self) -> Settings:
        return settings

    @provide
    async def get_bot(self, s: Settings) -> AsyncIterator[Bot]:
        bot = Bot(
            token=s.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        yield bot
        await bot.session.close()

    @provide
    def get_cache(self, s: Settings) -> CacheService:
        return CacheService(s.REDIS_URL)

    @provide
    def get_deezer(self, s: Settings) -> DeezerDownloader | None:
        if s.deezer_enabled:
            return DeezerDownloader(s.DEEZER_ARL)
        return None

    @provide
    def get_downloader(self, deezer: DeezerDownloader | None) -> DownloaderService:
        deezer_source = DeezerDownloadSource(deezer) if deezer is not None else None
        return DownloaderService(YtDlpDownloadSource(), deezer_source)

    @provide
    def get_album_service(self, s: Settings) -> AlbumService | None:
        if s.spotify_enabled:
            return AlbumService(s.SPOTIFY_CLIENT_ID, s.SPOTIFY_CLIENT_SECRET)
        return None

    @provide
    def get_soundcloud_album_service(self) -> SoundCloudAlbumService:
        return SoundCloudAlbumService()

    @provide
    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        return AsyncSessionFactory

    @provide
    async def get_arq_pool(self, s: Settings) -> AsyncIterator[ArqRedis]:
        pool = await create_pool(RedisSettings.from_dsn(s.REDIS_URL))
        yield pool
        await pool.aclose()

    @provide
    def get_captions(self) -> CaptionRenderer:
        return CaptionRenderer()

    @provide
    def get_messenger(self, bot: Bot, captions: CaptionRenderer) -> AudioMessenger:
        return AudioMessenger(bot, captions)

    @provide
    def get_uploader(self, bot: Bot, cache: CacheService) -> AudioUploader:
        return AudioUploader(bot, cache)

    @provide
    def get_track_delivery(
        self,
        cache: CacheService,
        downloader: DownloaderService,
        uploader: AudioUploader,
        messenger: AudioMessenger,
        captions: CaptionRenderer,
        session_factory: async_sessionmaker[AsyncSession],
        s: Settings,
    ) -> TrackDeliveryService:
        return TrackDeliveryService(
            cache, downloader, uploader, messenger, captions, session_factory, s
        )

    @provide
    def get_album_delivery(
        self,
        bot: Bot,
        spotify: AlbumService | None,
        soundcloud: SoundCloudAlbumService,
        downloader: DownloaderService,
        uploader: AudioUploader,
        cache: CacheService,
        captions: CaptionRenderer,
        session_factory: async_sessionmaker[AsyncSession],
        s: Settings,
    ) -> AlbumDeliveryService:
        return AlbumDeliveryService(
            bot, spotify, soundcloud, downloader, uploader, cache, captions, session_factory, s
        )

    @provide
    def get_search_service(self, cache: CacheService, s: Settings) -> SearchService:
        providers = []
        if s.spotify_enabled:
            from bot.services.spotify import SpotifyProvider
            providers.append(SpotifyProvider(s.SPOTIFY_CLIENT_ID, s.SPOTIFY_CLIENT_SECRET))
        providers += [
            YtDlpProvider("soundcloud", "scsearch"),
            YtDlpProvider("youtube", "ytmsearch"),
        ]
        return SearchService(providers, cache)


class RequestProvider(Provider):

    scope = Scope.REQUEST

    @provide
    async def get_session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @provide
    def get_user_repo(self, session: AsyncSession) -> UserRepository:
        return UserRepository(session)

    @provide
    def get_download_repo(self, session: AsyncSession) -> DownloadRepository:
        return DownloadRepository(session)

    @provide
    def get_search_repo(self, session: AsyncSession) -> SearchRepository:
        return SearchRepository(session)

    @provide
    def get_tracking(
        self,
        user_repo: UserRepository,
        download_repo: DownloadRepository,
        search_repo: SearchRepository,
    ) -> TrackingService:
        return TrackingService(user_repo, download_repo, search_repo)

    @provide
    def get_stats_service(
        self,
        user_repo: UserRepository,
        download_repo: DownloadRepository,
        search_repo: SearchRepository,
    ) -> StatsService:
        return StatsService(user_repo, download_repo, search_repo)


def create_container():
    return make_async_container(AppProvider(), RequestProvider())
