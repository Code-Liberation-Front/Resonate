from dataclasses import dataclass

from ..utils import format_duration


@dataclass
class Track:
    video_id: str
    title: str
    artists: str
    duration: int = 0
    thumbnail: str | None = None
    requested_by: int | None = None

    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def music_url(self) -> str:
        return f"https://music.youtube.com/watch?v={self.video_id}"

    @property
    def duration_str(self) -> str:
        return format_duration(self.duration)
