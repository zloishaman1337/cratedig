from cratedig.sources.base import SearchHit


def test_search_hit_preview_url_from_extra():
    hit = SearchHit(backend="freesound", id="1", title="Kick", extra={"preview": "https://x/a.mp3"})
    assert hit.preview_url() == "https://x/a.mp3"


def test_search_hit_preview_url_missing():
    hit = SearchHit(backend="youtube", id="1", title="Track", url="https://example.com")
    assert hit.preview_url() is None
