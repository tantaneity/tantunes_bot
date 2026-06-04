import asyncio
import logging

from bot.models.album import AlbumInfo
from bot.models.track import TrackInfo

logger = logging.getLogger(__name__)

_TRACKS_PAGE = 50
_FULL_TRACKS_BATCH = 50


class AlbumService:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def _client(self):
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials

        return spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=self._client_id,
                client_secret=self._client_secret,
            )
        )

    def _search_sync(self, query: str, limit: int) -> list[AlbumInfo]:
        sp = self._client()
        data = sp.search(q=query, type="album", limit=limit)

        albums: list[AlbumInfo] = []
        for item in data["albums"]["items"]:
            images = item.get("images") or []
            artists = item.get("artists") or []
            albums.append(
                AlbumInfo(
                    album_id=item["id"],
                    title=item["name"],
                    artist=artists[0]["name"] if artists else "Unknown",
                    cover=images[0]["url"] if images else "",
                    track_count=item.get("total_tracks", 0),
                    year=(item.get("release_date") or "")[:4],
                    source="spotify",
                )
            )
        return albums

    def _tracks_sync(self, album_id: str) -> list[TrackInfo]:
        sp = self._client()
        album = sp.album(album_id)
        images = album.get("images") or []
        cover = images[0]["url"] if images else ""

        simple: list[dict] = []
        page = sp.album_tracks(album_id, limit=_TRACKS_PAGE)
        simple.extend(page["items"])
        while page.get("next"):
            page = sp.next(page)
            simple.extend(page["items"])

        track_ids = [t["id"] for t in simple if t.get("id")]
        isrc_by_id: dict[str, str] = {}
        for start in range(0, len(track_ids), _FULL_TRACKS_BATCH):
            batch = sp.tracks(track_ids[start : start + _FULL_TRACKS_BATCH])["tracks"]
            for full in batch:
                if full:
                    isrc_by_id[full["id"]] = (full.get("external_ids") or {}).get("isrc", "")

        tracks: list[TrackInfo] = []
        for item in simple:
            track_id = item.get("id")
            if not track_id:
                continue
            artists = item.get("artists") or []
            artist = artists[0]["name"] if artists else "Unknown"
            title = item["name"]
            tracks.append(
                TrackInfo(
                    video_id=track_id,
                    url=f"ytmsearch1:{artist} {title}",
                    source="spotify",
                    title=title,
                    performer=artist,
                    duration=item["duration_ms"] // 1000,
                    thumbnail=cover,
                    isrc=isrc_by_id.get(track_id, ""),
                )
            )
        return tracks

    async def search_albums(self, query: str, limit: int) -> list[AlbumInfo]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    async def get_tracks(self, album_id: str) -> list[TrackInfo]:
        return await asyncio.to_thread(self._tracks_sync, album_id)
