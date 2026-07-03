from resonate.utils import format_duration, trim


def test_format_duration_minutes():
    assert format_duration(195) == "3:15"


def test_format_duration_hours():
    assert format_duration(3671) == "1:01:11"


def test_format_duration_unknown():
    assert format_duration(0) == "?:??"
    assert format_duration(None) == "?:??"


def test_trim_short_text_unchanged():
    assert trim("hello", 10) == "hello"


def test_trim_long_text():
    result = trim("a" * 20, 10)
    assert len(result) == 10
    assert result.endswith("…")
