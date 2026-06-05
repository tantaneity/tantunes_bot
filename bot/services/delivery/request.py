from dataclasses import dataclass


@dataclass
class TrackDeliveryRequest:
    user_id: int
    chat_id: int
    source: str
    video_id: str
    message_id: int | None = None
    inline_message_id: str | None = None


@dataclass
class AlbumDeliveryRequest:
    token: str
    index: int
    chat_id: int
    picker_message_id: int
    user_id: int
