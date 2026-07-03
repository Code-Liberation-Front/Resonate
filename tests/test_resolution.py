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


def test_resolve_track_url_uses_extractor():
    track = Track(video_id="abc", title="T", artists="A")
    with patch.object(extractor, "resolve", new=AsyncMock(return_value=track)) as mock:
        result = asyncio.run(resolver.resolve_track("https://youtu.be/abc"))
    assert result is track
    mock.assert_awaited_once_with("https://youtu.be/abc")


def test_resolve_track_text_uses_ytmusic():
    track = Track(video_id="abc", title="T", artists="A")
    with (
        patch.object(ytmusic, "search_songs", new=AsyncMock(return_value=[track])),
        patch.object(extractor, "resolve", new=AsyncMock()) as extract_mock,
    ):
        result = asyncio.run(resolver.resolve_track("some song"))
    assert result is track
    extract_mock.assert_not_awaited()


def test_resolve_track_falls_back_to_ytdlp():
    track = Track(video_id="abc", title="T", artists="A")
    with (
        patch.object(ytmusic, "search_songs", new=AsyncMock(side_effect=RuntimeError)),
        patch.object(extractor, "resolve", new=AsyncMock(return_value=track)) as extract_mock,
    ):
        result = asyncio.run(resolver.resolve_track("some song"))
    assert result is track
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
