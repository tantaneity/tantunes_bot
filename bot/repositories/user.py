from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from bot.models.entities import User
from bot.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get(self, user_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: int, username: str | None) -> User:

        stmt = (
            sqlite_insert(User)
            .values(
                user_id=user_id,
                username=username,
                first_seen=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await self._session.execute(stmt)
        return await self.get(user_id)

    async def count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(User))
        return result.scalar_one()

    async def per_day(self, since: datetime) -> list[tuple[str, int]]:
        result = await self._session.execute(
            select(
                func.strftime("%Y-%m-%d", User.first_seen).label("day"),
                func.count().label("cnt"),
            )
            .where(User.first_seen >= since)
            .group_by("day")
            .order_by("day")
        )
        return [(row.day, row.cnt) for row in result]
