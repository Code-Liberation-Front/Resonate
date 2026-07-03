import asyncio

import pytest

from resonate.music.track import Track
from resonate.storage.database import Database

OWNER = 1234


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    yield database


def make_track(n: int) -> Track:
    return Track(video_id=f"vid{n}", title=f"Song {n}", artists=f"Artist {n}", duration=100 + n)


def test_create_and_list_playlists(db):
    async def scenario():
        await db.connect()
        assert await db.create_playlist(OWNER, "Chill") is True
        assert await db.create_playlist(OWNER, "chill") is False  # case-insensitive dupe
        assert await db.create_playlist(OWNER, "Workout") is True
        assert await db.create_playlist(OWNER + 1, "Chill") is True  # other user OK
        playlists = await db.list_playlists(OWNER)
        assert [name for name, _ in playlists] == ["Chill", "Workout"]
        assert await db.count_playlists(OWNER) == 2
        await db.close()

    run(scenario())


def test_add_and_get_tracks(db):
    async def scenario():
        await db.connect()
        await db.create_playlist(OWNER, "Mix")
        playlist_id = await db.get_playlist_id(OWNER, "Mix")
        assert playlist_id is not None
        assert await db.add_track(playlist_id, make_track(1)) == 1
        assert await db.add_track(playlist_id, make_track(2)) == 2
        assert await db.add_track(playlist_id, make_track(3)) == 3
        tracks = await db.get_tracks(playlist_id)
        assert [t.video_id for t in tracks] == ["vid1", "vid2", "vid3"]
        assert tracks[0].title == "Song 1"
        assert tracks[0].duration == 101
        assert await db.count_tracks(playlist_id) == 3
        await db.close()

    run(scenario())


def test_remove_track_reorders_positions(db):
    async def scenario():
        await db.connect()
        await db.create_playlist(OWNER, "Mix")
        playlist_id = await db.get_playlist_id(OWNER, "Mix")
        for n in (1, 2, 3):
            await db.add_track(playlist_id, make_track(n))
        removed = await db.remove_track(playlist_id, 2)
        assert removed is not None and removed.video_id == "vid2"
        tracks = await db.get_tracks(playlist_id)
        assert [t.video_id for t in tracks] == ["vid1", "vid3"]
        # New track lands at position 3, right after the compacted list.
        assert await db.add_track(playlist_id, make_track(4)) == 3
        assert await db.remove_track(playlist_id, 99) is None
        await db.close()

    run(scenario())


def test_delete_playlist_cascades(db):
    async def scenario():
        await db.connect()
        await db.create_playlist(OWNER, "Mix")
        playlist_id = await db.get_playlist_id(OWNER, "Mix")
        await db.add_track(playlist_id, make_track(1))
        assert await db.delete_playlist(OWNER, "Mix") is True
        assert await db.delete_playlist(OWNER, "Mix") is False
        assert await db.get_playlist_id(OWNER, "Mix") is None
        # Cascade removed the orphaned tracks.
        assert await db.count_tracks(playlist_id) == 0
        await db.close()

    run(scenario())
