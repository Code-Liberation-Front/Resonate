import asyncio
import random
from collections import deque
from collections.abc import Iterable, Iterator

from .track import Track


class TrackQueue:
    """A FIFO track queue that supports async waiting plus inspection."""

    def __init__(self) -> None:
        self._tracks: deque[Track] = deque()
        self._not_empty = asyncio.Condition()

    async def put(self, track: Track) -> None:
        async with self._not_empty:
            self._tracks.append(track)
            self._not_empty.notify()

    async def put_many(self, tracks: Iterable[Track]) -> None:
        async with self._not_empty:
            self._tracks.extend(tracks)
            self._not_empty.notify()

    async def get(self) -> Track:
        async with self._not_empty:
            while not self._tracks:
                await self._not_empty.wait()
            return self._tracks.popleft()

    def clear(self) -> None:
        self._tracks.clear()

    def shuffle(self) -> None:
        random.shuffle(self._tracks)

    def remove(self, index: int) -> Track:
        track = self._tracks[index]
        del self._tracks[index]
        return track

    def __len__(self) -> int:
        return len(self._tracks)

    def __iter__(self) -> Iterator[Track]:
        return iter(self._tracks)
