from dataclasses import dataclass


@dataclass
class TrackInfo:
    video_id: str
    url: str
    source: str
    title: str
    performer: str
    duration: int
    thumbnail: str
