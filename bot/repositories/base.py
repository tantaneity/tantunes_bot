from abc import ABC

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository(ABC):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
