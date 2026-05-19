from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from bot.models.base import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str | None]
    first_seen: Mapped[datetime]


class Download(Base):
    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None]
    source: Mapped[str | None]
    performer: Mapped[str | None]
    title: Mapped[str | None]
    created_at: Mapped[datetime]


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None]
    query: Mapped[str | None]
    created_at: Mapped[datetime]
