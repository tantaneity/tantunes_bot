from typing import Any

from bot.services.delivery import (
    AlbumDeliveryRequest,
    AlbumDeliveryService,
    TrackDeliveryRequest,
    TrackDeliveryService,
)


async def download_track(
    ctx: dict[str, Any],
    *,
    user_id: int,
    chat_id: int,
    message_id: int | None,
    inline_message_id: str | None,
    source: str,
    video_id: str,
) -> None:
    service: TrackDeliveryService = ctx["track_delivery"]
    await service.deliver(
        TrackDeliveryRequest(
            user_id=user_id,
            chat_id=chat_id,
            source=source,
            video_id=video_id,
            message_id=message_id,
            inline_message_id=inline_message_id,
        )
    )


async def download_album(
    ctx: dict[str, Any],
    *,
    token: str,
    index: int,
    chat_id: int,
    picker_message_id: int,
    user_id: int,
) -> None:
    service: AlbumDeliveryService = ctx["album_delivery"]
    await service.run(
        AlbumDeliveryRequest(
            token=token,
            index=index,
            chat_id=chat_id,
            picker_message_id=picker_message_id,
            user_id=user_id,
        )
    )
