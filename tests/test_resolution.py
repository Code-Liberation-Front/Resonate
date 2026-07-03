import asyncio
from unittest.mock import AsyncMock, patch

from resonate.music import extractor, resolver, ytmusic
from resonate.music.track import Track

SAMPLE_SEARCH = [
    {
        "videoId": "abc",
        "title": "Song A",
        "artists": [{"name": "X"}, {"name": "Y"}],
        "duration_seconds": 200,
        "thumbnails": [{"url": "small"}, {"url": "big"}],
    },
    {"title": "no videoId — should be skipped"},
    {
        "videoId": "def",
        "title": "Song B",
        "artists": [],
        "duration_seconds": None,
        "thumbnails": [],
    },
]


def test_search_result_parsing():
    with patch.object(ytmusic, "_search_blocking", return_value=SAMPLE_SEARCH):
        tracks = asyncio.run(ytmusic.search_songs("query", limit=5))
    assert [t.video_id for t in tracks] == ["abc", "def"]
    assert tracks[0].artists == "X, Y"
    assert tracks[0].thumbnail == "big"
    assert tracks[0].duration == 200
    assert tracks[1].artists == "Unknown artist"
    assert tracks[1].duration == 0
    assert tracks[1].thumbnail is None


def test_is_url():
    assert resolver.is_url("https://music.youtube.com/watch?v=abc")
    assert resolver.is_url("  http://youtu.be/abc")
    assert not resolver.is_url("never gonna give you up")


def test_search_or_resolve_url_uses_extractor():
    track = Track(video_id="abc", title="T", artists="A")
    with patch.object(extractor, "resolve", new=AsyncMock(return_value=track)) as mock:
        result = asyncio.run(resolver.search_or_resolve("https://youtu.be/abc"))
    assert result == [track]
    mock.assert_awaited_once_with("https://youtu.be/abc")


def test_search_or_resolve_text_returns_ytmusic_matches():
    tracks = [
        Track(video_id="abc", title="T1", artists="A"),
        Track(video_id="def", title="T2", artists="B"),
    ]
    with (
        patch.object(ytmusic, "search_songs", new=AsyncMock(return_value=tracks)),
        patch.object(extractor, "resolve", new=AsyncMock()) as extract_mock,
    ):
        result = asyncio.run(resolver.search_or_resolve("some song", limit=10))
    assert result == tracks
    extract_mock.assert_not_awaited()


def test_search_or_resolve_falls_back_when_ytmusic_errors():
    track = Track(video_id="abc", title="T", artists="A")
    with (
        patch.object(ytmusic, "search_songs", new=AsyncMock(side_effect=RuntimeError)),
        patch.object(extractor, "resolve", new=AsyncMock(return_value=track)) as extract_mock,
    ):
        result = asyncio.run(resolver.search_or_resolve("some song"))
    assert result == [track]
    extract_mock.assert_awaited_once_with("ytsearch1:some song")


def test_search_or_resolve_falls_back_when_ytmusic_is_empty():
    track = Track(video_id="abc", title="T", artists="A")
    with (
        patch.object(ytmusic, "search_songs", new=AsyncMock(return_value=[])),
        patch.object(extractor, "resolve", new=AsyncMock(return_value=track)) as extract_mock,
    ):
        result = asyncio.run(resolver.search_or_resolve("some song"))
    assert result == [track]
    extract_mock.assert_awaited_once_with("ytsearch1:some song")


def test_extractor_to_track_prefers_artist():
    info = {
        "id": "abc",
        "title": "Song",
        "artist": "Real Artist",
        "uploader": "Some Channel",
        "duration": 123.4,
        "thumbnail": "thumb",
    }
    track = extractor._to_track(info)
    assert track.artists == "Real Artist"
    assert track.duration == 123
    assert track.watch_url == "https://www.youtube.com/watch?v=abc"

    info.pop("artist")
    assert extractor._to_track(info).artists == "Some Channel"
