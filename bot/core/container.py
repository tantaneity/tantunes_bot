from collections.abc import AsyncGenerator

from dishka import Provider, Scope, make_async_container, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings, settings
from bot.core.db import AsyncSessionFactory
from bot.repositories.stats import DownloadRepository, SearchRepository
from bot.repositories.user import UserRepository
from bot.services.album import AlbumService
from bot.services.cache import CacheService
from bot.services.deezer import DeezerDownloader
from bot.services.downloader import DownloaderService
from bot.services.search import SearchService, YtDlpProvider
from bot.services.stats import StatsService
from bot.services.tracker import TrackingService


class AppProvider(Provider):

    scope = Scope.APP

    @provide
    def get_settings(self) -> Settings:
        return settings

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
        return DownloaderService(deezer)

    @provide
    def get_album_service(self, s: Settings) -> AlbumService | None:
        if s.spotify_enabled:
            return AlbumService(s.SPOTIFY_CLIENT_ID, s.SPOTIFY_CLIENT_SECRET)
        return None

    @provide
    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        return AsyncSessionFactory

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
