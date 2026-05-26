_ZW = "⁠"


def _e(emoji_id: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{_ZW}</tg-emoji>'


MUSIC = _e("5352857362078117231")
CLOCK = _e("5350462668702496711")
DOWNLOAD = _e("5350374905340770766")
PROCESSING = _e("5353025909479715412")
ERROR = _e("5350561938281607564")

SOURCE_EMOJI = {
    "soundcloud": _e("5226660562812818287"),
    "spotify": _e("5330338002436633953"),
    "youtube": _e("5222297223932419849"),
}

MUSIC_EMOJI_ID = "5352857362078117231"

SOURCE_EMOJI_IDS: dict[str, str] = {
    "soundcloud": "5226660562812818287",
    "spotify": "5330338002436633953",
    "youtube": "5222297223932419849",
}

SOURCE_LABEL = {
    "soundcloud": "SC",
    "spotify": "SP",
    "youtube": "YTM",
}

DOWNLOAD_EMOJI_ID = "5350374905340770766"
