from cratedig.tui.status import format_operations, progress_label


def test_progress_label_with_total():
    assert progress_label("analyze", 3, 10, "kick.wav") == "analyze · 3/10 30% · kick.wav"


def test_progress_label_without_total():
    assert progress_label("scan", 4, None, "snare.wav") == "scan · 4 · snare.wav"


def test_progress_label_without_counts():
    assert progress_label("download", detail="indexing") == "download · indexing"


def test_format_operations_uses_fixed_order_and_idle_defaults():
    out = format_operations({"analyze": "12/100 12%", "download": "done"})
    assert out.splitlines() == [
        "scan: idle",
        "analyze: 12/100 12%",
        "classify: idle",
        "download: done",
    ]
