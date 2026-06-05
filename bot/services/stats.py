import asyncio
import io
from dataclasses import dataclass
from datetime import datetime, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from bot.emoji import MUSIC
from bot.repositories.stats import DownloadRepository, SearchRepository
from bot.repositories.user import UserRepository

_SOURCE_NAME = {"soundcloud": "SoundCloud", "spotify": "Spotify", "youtube": "YouTube"}


@dataclass
class StatsData:
    total_users: int
    total_downloads: int
    total_searches: int
    by_source: list[tuple[str, int]]
    dl_per_day: list[tuple[str, int]]
    users_per_day: list[tuple[str, int]]


class StatsService:
    def __init__(
        self,
        user_repo: UserRepository,
        download_repo: DownloadRepository,
        search_repo: SearchRepository,
    ) -> None:
        self._user_repo = user_repo
        self._download_repo = download_repo
        self._search_repo = search_repo

    async def fetch(self) -> StatsData:
        since = datetime.utcnow() - timedelta(days=14)
        total_users, total_downloads, total_searches, by_source, dl_per_day, users_per_day = (
            await asyncio.gather(
                self._user_repo.count(),
                self._download_repo.count(),
                self._search_repo.count(),
                self._download_repo.by_source(),
                self._download_repo.per_day(since),
                self._user_repo.per_day(since),
            )
        )
        return StatsData(
            total_users=total_users,
            total_downloads=total_downloads,
            total_searches=total_searches,
            by_source=by_source,
            dl_per_day=dl_per_day,
            users_per_day=users_per_day,
        )

    def _fill_days(
        self, data: list[tuple[str, int]], days: int = 14
    ) -> tuple[list[str], list[int]]:
        mapping = dict(data)
        labels, values = [], []
        for i in range(days - 1, -1, -1):
            day = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
            labels.append((datetime.utcnow() - timedelta(days=i)).strftime("%d.%m"))
            values.append(mapping.get(day, 0))
        return labels, values

    def _build_chart_sync(self, data: StatsData) -> bytes:
        labels_dl, values_dl = self._fill_days(data.dl_per_day)
        labels_u, values_u = self._fill_days(data.users_per_day)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
        fig.patch.set_facecolor("#1a1a2e")

        for ax in (ax1, ax2):
            ax.set_facecolor("#16213e")
            ax.tick_params(colors="#cccccc", labelsize=8)
            ax.spines[:].set_color("#333355")
            ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

        ax1.bar(labels_dl, values_dl, color="#7b68ee")
        ax1.set_title("downloads / day", color="#cccccc", fontsize=11)
        ax1.set_xticks(range(len(labels_dl)))
        ax1.set_xticklabels(labels_dl, rotation=45, ha="right")

        ax2.bar(labels_u, values_u, color="#48cae4")
        ax2.set_title("new users / day", color="#cccccc", fontsize=11)
        ax2.set_xticks(range(len(labels_u)))
        ax2.set_xticklabels(labels_u, rotation=45, ha="right")

        fig.tight_layout(pad=2)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    async def build_chart(self, data: StatsData) -> bytes:
        return await asyncio.to_thread(self._build_chart_sync, data)

    def format_text(self, data: StatsData) -> str:
        by_source = "\n".join(
            f"  {_SOURCE_NAME.get(src, src)}: {count}"
            for src, count in data.by_source
        ) or "  —"
        return (
            f"<b>tantunes stats</b>\n\n"
            f"👤 users: <b>{data.total_users}</b>\n"
            f"{MUSIC} sent: <b>{data.total_downloads}</b>\n"
            f"🔍 searches: <b>{data.total_searches}</b>\n\n"
            f"<b>by source</b>\n{by_source}"
        )
