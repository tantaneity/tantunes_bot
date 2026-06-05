from abc import ABC, abstractmethod

from bot.services.download.request import DownloadRequest


class DownloadSource(ABC):
    @abstractmethod
    def can_handle(self, request: DownloadRequest) -> bool: ...

    @abstractmethod
    async def download(self, request: DownloadRequest) -> str: ...
