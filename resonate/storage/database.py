"""SQLite persistence for user playlists."""

import aiosqlite

from ..music.track import Track

_SCHEMA = """
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL COLLATE NOCASE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (owner_id, name)
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artists TEXT NOT NULL,
    duration INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist
    ON playlist_tracks (playlist_id, position);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database is not connected")
        return self._db

    async def count_playlists(self, owner_id: int) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM playlists WHERE owner_id = ?", (owner_id,)
        ) as cursor:
            (count,) = await cursor.fetchone()
        return count

    async def create_playlist(self, owner_id: int, name: str) -> bool:
        """Create a playlist; returns False if the name is already taken."""
        try:
            await self.db.execute(
                "INSERT INTO playlists (owner_id, name) VALUES (?, ?)",
                (owner_id, name),
            )
        except aiosqlite.IntegrityError:
            return False
        await self.db.commit()
        return True

    async def delete_playlist(self, owner_id: int, name: str) -> bool:
        cursor = await self.db.execute(
            "DELETE FROM playlists WHERE owner_id = ? AND name = ?",
            (owner_id, name),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def list_playlists(self, owner_id: int) -> list[tuple[str, int]]:
        """Return (name, track_count) for each playlist the user owns."""
        async with self.db.execute(
            """
            SELECT p.name, COUNT(t.id)
            FROM playlists p
            LEFT JOIN playlist_tracks t ON t.playlist_id = p.id
            WHERE p.owner_id = ?
            GROUP BY p.id
            ORDER BY p.name
            """,
            (owner_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [(name, count) for name, count in rows]

    async def get_playlist_id(self, owner_id: int, name: str) -> int | None:
        async with self.db.execute(
            "SELECT id FROM playlists WHERE owner_id = ? AND name = ?",
            (owner_id, name),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

    async def count_tracks(self, playlist_id: int) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ) as cursor:
            (count,) = await cursor.fetchone()
        return count

    async def add_track(self, playlist_id: int, track: Track) -> int:
        """Append a track to a playlist and return its 1-based position."""
        async with self.db.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ) as cursor:
            (position,) = await cursor.fetchone()
        await self.db.execute(
            """
            INSERT INTO playlist_tracks (playlist_id, video_id, title, artists, duration, position)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (playlist_id, track.video_id, track.title, track.artists, track.duration, position),
        )
        await self.db.commit()
        return position

    async def get_tracks(self, playlist_id: int) -> list[Track]:
        async with self.db.execute(
            """
            SELECT video_id, title, artists, duration
            FROM playlist_tracks
            WHERE playlist_id = ?
            ORDER BY position
            """,
            (playlist_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            Track(video_id=video_id, title=title, artists=artists, duration=duration)
            for video_id, title, artists, duration in rows
        ]

    async def remove_track(self, playlist_id: int, position: int) -> Track | None:
        """Remove the track at a 1-based position and close the gap."""
        async with self.db.execute(
            """
            SELECT video_id, title, artists, duration
            FROM playlist_tracks
            WHERE playlist_id = ? AND position = ?
            """,
            (playlist_id, position),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        await self.db.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND position = ?",
            (playlist_id, position),
        )
        await self.db.execute(
            "UPDATE playlist_tracks SET position = position - 1 "
            "WHERE playlist_id = ? AND position > ?",
            (playlist_id, position),
        )
        await self.db.commit()
        video_id, title, artists, duration = row
        return Track(video_id=video_id, title=title, artists=artists, duration=duration)
