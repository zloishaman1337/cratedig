from cratedig.sources.base import SearchHit, safe_filename, unique_path


def test_search_hit_preview_url_from_extra():
    hit = SearchHit(backend="freesound", id="1", title="Kick", extra={"preview": "https://x/a.mp3"})
    assert hit.preview_url() == "https://x/a.mp3"


def test_search_hit_preview_url_missing():
    hit = SearchHit(backend="youtube", id="1", title="Track", url="https://example.com")
    assert hit.preview_url() is None


def test_safe_filename_track_dash_artist():
    assert safe_filename("Song", "Artist") == "Song - Artist"


def test_safe_filename_no_artist():
    assert safe_filename("Song", "") == "Song"


def test_safe_filename_strips_illegal_chars():
    assert safe_filename('a/b:c?', "x|y") == "abc - xy"


def test_safe_filename_keeps_unicode():
    assert safe_filename("Минор", "Казах") == "Минор - Казах"


def test_safe_filename_empty_falls_back():
    assert safe_filename("", "") == "track"


def test_safe_filename_collapses_whitespace():
    assert safe_filename("a   b", "c") == "a b - c"


def test_safe_filename_strips_trailing_dot():
    assert safe_filename("Song", "Artist.") == "Song - Artist"


def test_unique_path_no_clobber(tmp_path):
    first = unique_path(tmp_path, "Song - Artist", ".mp3")
    assert first.name == "Song - Artist.mp3"
    first.write_bytes(b"")
    second = unique_path(tmp_path, "Song - Artist", "mp3")
    assert second.name == "Song - Artist (2).mp3"
