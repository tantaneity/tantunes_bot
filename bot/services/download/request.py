from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class DownloadRequest:
    url: str
    output_dir: str
    title: str = ""
    artist: str = ""
    isrc: str = ""
    expected_duration: int = 0
    expected_title: str = ""
    expected_artist: str = ""
    use_deezer: bool = False
    on_progress: Callable[[int], None] | None = None
