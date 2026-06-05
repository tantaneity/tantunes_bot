from html import escape

from bot.emoji import (
    ERROR,
    MUSIC,
    MUSIC_EMOJI_ID,
    MUSIC_FALLBACK,
    PROCESSING,
    SOURCE_EMOJI,
    SOURCE_EMOJI_FALLBACKS,
    SOURCE_EMOJI_IDS,
)
from bot.models.album import AlbumInfo

_CHANNEL_URL = "https://t.me/instantaneity"
_SPOTIFY_TRACK_URL = "https://open.spotify.com/track/{video_id}"
_YOUTUBE_TRACK_URL = "https://www.youtube.com/watch?v={video_id}"
_PROGRESS_BAR_WIDTH = 10


class CaptionRenderer:
    def track(self, source: str, performer: str, title: str) -> str:
        music_tag = f'<tg-emoji emoji-id="{MUSIC_EMOJI_ID}">{MUSIC_FALLBACK}</tg-emoji>'
        source_id = SOURCE_EMOJI_IDS.get(source)
        source_fallback = SOURCE_EMOJI_FALLBACKS.get(source, source.upper())
        source_tag = (
            f'<tg-emoji emoji-id="{source_id}">{source_fallback}</tg-emoji>'
            if source_id
            else source_fallback
        )
        return (
            f"{music_tag} "
            f'<a href="{_CHANNEL_URL}"><b>{escape(performer)} — {escape(title)}</b></a>'
            f" · {source_tag}"
        )

    def processing(self) -> str:
        return f"{PROCESSING} Downloading..."

    def download_failed(self) -> str:
        return f"{ERROR} Failed to download. Please try again."

    def bot_not_started(self) -> str:
        return f"{ERROR} Start the bot in PM first, then try again."

    def track_url(self, source: str, video_id: str, download_url: str | None) -> str | None:
        if source == "spotify" and video_id:
            return _SPOTIFY_TRACK_URL.format(video_id=video_id)
        if source == "youtube" and video_id:
            return _YOUTUBE_TRACK_URL.format(video_id=video_id)
        if download_url and download_url.startswith(("http://", "https://")):
            return download_url
        return None

    def album(self, album: AlbumInfo, index: int, total: int) -> str:
        icon = SOURCE_EMOJI.get(album.source, MUSIC)
        parts = [part for part in (album.year, f"{album.track_count} tracks") if part]
        if total > 1:
            parts.append(f"{index + 1}/{total}")
        return f"{icon} <b>{escape(album.artist)} — {escape(album.title)}</b>\n{' · '.join(parts)}"

    def album_header(self, album: AlbumInfo) -> str:
        return f"{MUSIC} <b>{escape(album.artist)} — {escape(album.title)}</b>"

    def album_progress(self, album: AlbumInfo, done: int, total: int) -> str:
        return f"{self.album_header(album)}\n<code>{self._bar(done, total)}</code> {done}/{total}"

    def album_done(self, album: AlbumInfo, delivered: int, total: int) -> str:
        tail = f"{delivered}/{total} tracks" if delivered != total else f"{total} tracks"
        return f"{self.album_header(album)}\n{album.year} · {tail}"

    def album_error(self, text: str) -> str:
        return f"{ERROR} {text}"

    def _bar(self, done: int, total: int) -> str:
        filled = round(_PROGRESS_BAR_WIDTH * done / total) if total else 0
        return "█" * filled + "░" * (_PROGRESS_BAR_WIDTH - filled)
