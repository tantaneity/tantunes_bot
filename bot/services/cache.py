import json

import redis.asyncio as aioredis

_AUDIO_TTL = 30 * 24 * 3600
_META_TTL = 7 * 24 * 3600
_SEARCH_TTL = 5 * 60
_ALBUM_TTL = 60 * 60


class CacheService:
    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._url, decode_responses=True)
        return self._client



    def _audio_key(self, source: str, video_id: str) -> str:
        return f"audio:{source}:{video_id}"

    def _meta_key(self, source: str, video_id: str) -> str:
        return f"meta:{source}:{video_id}"

    def _search_key(self, query: str) -> str:
        return f"search:{query.lower()}"

    def _albums_key(self, token: str) -> str:
        return f"albums:{token}"

    async def get_file_id(self, source: str, video_id: str) -> str | None:
        r = await self._get_client()
        return await r.get(self._audio_key(source, video_id))

    async def set_file_id(self, source: str, video_id: str, file_id: str) -> None:
        r = await self._get_client()
        await r.set(self._audio_key(source, video_id), file_id, ex=_AUDIO_TTL)



    async def get_track_meta(self, source: str, video_id: str) -> dict | None:
        r = await self._get_client()
        data = await r.hgetall(self._meta_key(source, video_id))
        return data or None

    async def set_track_meta(
        self,
        source: str,
        video_id: str,
        title: str,
        performer: str,
        duration: int,
        url: str,
        thumbnail: str = "",
    ) -> None:
        r = await self._get_client()
        key = self._meta_key(source, video_id)
        await r.hset(
            key,
            mapping={
                "title": title,
                "performer": performer,
                "duration": str(duration),
                "url": url,
                "thumbnail": thumbnail,
            },
        )
        await r.expire(key, _META_TTL)



    async def get_search_cache(self, query: str) -> list[dict] | None:
        r = await self._get_client()
        data = await r.get(self._search_key(query))
        return json.loads(data) if data else None

    async def set_search_cache(self, query: str, tracks: list[dict]) -> None:
        r = await self._get_client()
        await r.set(self._search_key(query), json.dumps(tracks), ex=_SEARCH_TTL)

    async def get_albums(self, token: str) -> list[dict] | None:
        r = await self._get_client()
        data = await r.get(self._albums_key(token))
        return json.loads(data) if data else None

    async def set_albums(self, token: str, albums: list[dict]) -> None:
        r = await self._get_client()
        await r.set(self._albums_key(token), json.dumps(albums), ex=_ALBUM_TTL)
