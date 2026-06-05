from dataclasses import dataclass


@dataclass
class AudioMessage:
    source: str
    video_id: str
    performer: str
    title: str
    url: str = ""
    thumbnail_url: str = ""
    file_id: str = ""

    @classmethod
    def from_meta(
        cls, source: str, video_id: str, meta: dict, file_id: str = ""
    ) -> "AudioMessage":
        return cls(
            source=source,
            video_id=video_id,
            performer=meta.get("performer", "Unknown"),
            title=meta.get("title", "Unknown"),
            url=meta.get("url", ""),
            thumbnail_url=meta.get("thumbnail", ""),
            file_id=file_id,
        )
