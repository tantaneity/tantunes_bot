from dataclasses import dataclass


@dataclass
class AlbumInfo:
    album_id: str
    title: str
    artist: str
    cover: str
    track_count: int
    year: str
    source: str
