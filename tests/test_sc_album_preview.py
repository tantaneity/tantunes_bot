from bot.services.soundcloud_album import _is_preview


def _entry(*format_ids: str) -> dict:
    return {"formats": [{"format_id": format_id} for format_id in format_ids]}


def test_should_detect_preview_when_every_format_is_a_snippet():
    assert _is_preview(_entry("hls_mp3_1_0_preview", "http_mp3_1_0_preview"))


def test_should_not_flag_preview_when_full_stream_is_available():
    assert not _is_preview(_entry("hls_mp3_1_0", "http_mp3_1_0_preview"))


def test_should_not_flag_preview_when_formats_are_missing():
    assert not _is_preview({})


if __name__ == "__main__":
    test_should_detect_preview_when_every_format_is_a_snippet()
    test_should_not_flag_preview_when_full_stream_is_available()
    test_should_not_flag_preview_when_formats_are_missing()
    print("ok")
