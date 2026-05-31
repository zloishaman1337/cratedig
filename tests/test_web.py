import numpy as np

from cratedig.audio.playback import WaveformData
from cratedig.db import Database
from cratedig.db.models import Sample
from cratedig.web.server import build_tree, sample_to_payload, sample_url, waveform_to_payload
from cratedig.tui.app import _tree_rows


def _sample(path: str, **kw) -> Sample:
    return Sample(id=None, path=path, filename=path.split("/")[-1], **kw)


def test_build_tree_groups_samples_under_library_root(tmp_path):
    root = tmp_path / "packs"
    samples = [
        Sample(id=1, path=str(root / "drums" / "kick.wav"), filename="kick.wav", category="kick"),
        Sample(id=2, path=str(root / "bass" / "sub.wav"), filename="sub.wav", category="bass"),
    ]

    tree = build_tree(samples, (root,))

    assert tree[0]["name"] == "packs"
    assert [child["name"] for child in tree[0]["children"]] == ["bass", "drums"]
    bass = tree[0]["children"][0]["children"][0]
    assert bass["type"] == "sample"
    assert bass["id"] == 2


def test_sample_to_payload_includes_tags_and_media_urls(tmp_path):
    db = Database(tmp_path / "t.db")
    sid = db.upsert_sample(_sample(str(tmp_path / "kick.wav"), bpm=128.0))
    db.add_tag(sid, "drum")

    payload = sample_to_payload(db, db.get_sample(sid))

    assert payload["id"] == sid
    assert payload["tags"] == ["drum"]
    assert payload["audio_url"] == f"/audio?id={sid}"
    assert payload["waveform_url"] == f"/api/waveform?id={sid}"
    db.close()


def test_waveform_to_payload_is_canvas_friendly():
    data = WaveformData(
        peaks=np.array([[[-1.0, 0.5], [-0.25, 1.0]]], dtype=np.float32),
        rms=np.array([[0.5, 0.25]], dtype=np.float32),
        duration_sec=2.0,
        sample_rate=2,
        channels=1,
    )

    payload = waveform_to_payload(data)

    assert payload["bins"] == 2
    assert payload["channels"] == 1
    assert payload["peaks"][0][0] == [-1.0, 0.5]
    assert payload["rms"][0] == [0.5, 0.25]


def test_sample_url_appends_selected_sample():
    assert sample_url("http://127.0.0.1:8765", 42) == "http://127.0.0.1:8765/?sample=42"


def test_tui_tree_rows_include_folder_and_sample_rows(tmp_path):
    root = tmp_path / "packs"
    sample = Sample(id=7, path=str(root / "drums" / "kick.wav"), filename="kick.wav")

    rows = _tree_rows([sample], (root,))

    assert rows[0][0].startswith("folder:")
    assert rows[0][1][1] == "▾ packs"
    assert rows[1][1][1] == "  ▾ drums"
    assert rows[2][0] == "7"
    assert "kick.wav" in rows[2][1][1]
