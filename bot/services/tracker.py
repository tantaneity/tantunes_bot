from bot.repositories.stats import DownloadRepository, SearchRepository
from bot.repositories.user import UserRepository


class TrackingService:
    def __init__(
        self,
        user_repo: UserRepository,
        download_repo: DownloadRepository,
        search_repo: SearchRepository,
    ) -> None:
        self._user_repo = user_repo
        self._download_repo = download_repo
        self._search_repo = search_repo

    async def record_user(self, user_id: int, username: str | None) -> None:
        await self._user_repo.get_or_create(user_id, username)

    async def record_download(
        self,
        user_id: int | None,
        source: str | None,
        performer: str | None,
        title: str | None,
    ) -> None:
        await self._download_repo.add(user_id, source, performer, title)

    async def record_search(self, user_id: int | None, query: str | None) -> None:
        await self._search_repo.add(user_id, query)
