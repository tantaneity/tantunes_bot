from bot.models.track import TrackInfo
from bot.services.search import _pick_sc_candidate


def _sc(slug: str, duration: int) -> TrackInfo:
    return TrackInfo(
        video_id=slug,
        url=f"https://soundcloud.com/artist/{slug}",
        source="soundcloud",
        title="Cross My Heart, Hope To Die",
        performer="Fordirelifesake",
        duration=duration,
        thumbnail="",
    )


def test_should_skip_preview_and_take_full_track_when_first_hit_is_snippet():
    candidates = [_sc("preview", 30), _sc("best-part", 74), _sc("full", 266)]
    assert _pick_sc_candidate(candidates, 267).video_id == "full"


def test_should_return_none_when_every_candidate_is_a_preview():
    assert _pick_sc_candidate([_sc("preview", 30), _sc("remaster-preview", 30)], 267) is None


def test_should_return_none_when_expected_duration_is_unknown():
    assert _pick_sc_candidate([_sc("full", 266)], 0) is None


if __name__ == "__main__":
    test_should_skip_preview_and_take_full_track_when_first_hit_is_snippet()
    test_should_return_none_when_every_candidate_is_a_preview()
    test_should_return_none_when_expected_duration_is_unknown()
    print("ok")
