import asyncio
import logging

from bot.models.track import TrackInfo
from bot.services.search import SearchProvider
from bot.services.search_urls import build_youtube_search_url

logger = logging.getLogger(__name__)


class SpotifyProvider(SearchProvider):
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    @property
    def source(self) -> str:
        return "spotify"

    def _search_sync(self, query: str, max_results: int) -> list[TrackInfo]:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials

        sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=self._client_id,
                client_secret=self._client_secret,
            )
        )

        data = sp.search(q=query, type="track", limit=max_results)
        tracks: list[TrackInfo] = []
        for item in data["tracks"]["items"]:
            artist = item["artists"][0]["name"] if item["artists"] else "Unknown"
            title = item["name"]
            duration = item["duration_ms"] // 1000
            video_id = item["id"]
            images = item["album"]["images"]
            thumbnail = images[0]["url"] if images else ""

            tracks.append(
                TrackInfo(
                    video_id=video_id,
                    url=build_youtube_search_url(artist, title),
                    source="spotify",
                    title=title,
                    performer=artist,
                    duration=duration,
                    thumbnail=thumbnail,
                )
            )
        return tracks

    async def search(self, query: str, max_results: int) -> list[TrackInfo]:
        return await asyncio.to_thread(self._search_sync, query, max_results)
