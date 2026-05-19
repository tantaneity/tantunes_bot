from datetime import datetime

from sqlalchemy import func, select

from bot.models.entities import Download, Search
from bot.repositories.base import BaseRepository


class DownloadRepository(BaseRepository):
    async def add(
        self,
        user_id: int | None,
        source: str | None,
        performer: str | None,
        title: str | None,
    ) -> None:
        download = Download(
            user_id=user_id,
            source=source,
            performer=performer,
            title=title,
            created_at=datetime.utcnow(),
        )
        self._session.add(download)
        await self._session.flush()

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Download)
        )
        return result.scalar_one()

    async def per_day(self, since: datetime) -> list[tuple[str, int]]:
        result = await self._session.execute(
            select(
                func.strftime("%Y-%m-%d", Download.created_at).label("day"),
                func.count().label("cnt"),
            )
            .where(Download.created_at >= since)
            .group_by("day")
            .order_by("day")
        )
        return [(row.day, row.cnt) for row in result]

    async def by_source(self) -> list[tuple[str, int]]:
        result = await self._session.execute(
            select(Download.source, func.count().label("cnt"))
            .group_by(Download.source)
            .order_by(func.count().desc())
        )
        return [(row.source or "unknown", row.cnt) for row in result]


class SearchRepository(BaseRepository):
    async def add(self, user_id: int | None, query: str | None) -> None:
        search = Search(
            user_id=user_id,
            query=query,
            created_at=datetime.utcnow(),
        )
        self._session.add(search)
        await self._session.flush()

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Search)
        )
        return result.scalar_one()

    async def per_day(self, since: datetime) -> list[tuple[str, int]]:
        result = await self._session.execute(
            select(
                func.strftime("%Y-%m-%d", Search.created_at).label("day"),
                func.count().label("cnt"),
            )
            .where(Search.created_at >= since)
            .group_by("day")
            .order_by("day")
        )
        return [(row.day, row.cnt) for row in result]
