import wave

from cratedig.db import Database
from cratedig.db.models import Sample
from cratedig.scan import scan_directory


def _write_wav(path, seconds=1, sr=8000):
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * (sr * seconds))


def test_scan_indexes_wav(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    _write_wav(lib / "kick_01.wav")
    _write_wav(lib / "b.wav")
    (lib / "notes.txt").write_text("ignore me")

    db = Database(tmp_path / "s.db")
    n = scan_directory(db, lib, extensions=(".wav",))
    assert n == 2
    assert db.count_samples() == 2

    # second scan is a no-op (paths already present)
    assert scan_directory(db, lib, extensions=(".wav",)) == 0

    s = db.all_samples()[0]
    assert s.format == "wav"
    assert s.file_hash and len(s.file_hash) == 40
    # kick_01.wav has instrument_class="kick" and category=None
    # b.wav has both category=None and instrument_class=None
    assert {sample.category for sample in db.all_samples()} == {None}
    assert {sample.instrument_class for sample in db.all_samples()} == {None, "kick"}
    db.close()


def test_scan_prunes_deleted_local_files(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    keep = lib / "keep.wav"
    gone = lib / "gone.wav"
    _write_wav(keep)
    _write_wav(gone)

    db = Database(tmp_path / "s.db")
    assert scan_directory(db, lib, extensions=(".wav",)) == 2
    gone.unlink()

    assert scan_directory(db, lib, extensions=(".wav",)) == 0
    samples = db.all_samples()
    assert db.count_samples() == 1
    assert samples[0].path == str(keep.resolve())
    db.close()


def test_scan_prunes_deleted_files_under_root_regardless_of_source(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    gone = lib / "gone.wav"
    outside = tmp_path / "outside.wav"
    _write_wav(gone)
    _write_wav(outside)

    db = Database(tmp_path / "s.db")
    assert scan_directory(db, lib, extensions=(".wav",), source="freesound") == 1
    db.upsert_sample(Sample(
        id=None,
        path=str(outside.resolve()),
        filename=outside.name,
        source="freesound",
        created_at="now",
    ))
    gone.unlink()

    assert scan_directory(db, lib, extensions=(".wav",)) == 0
    samples = db.all_samples()
    assert db.count_samples() == 1
    assert samples[0].path == str(outside.resolve())
    db.close()


def test_scan_saved_updates_existing_local_row_to_edit(tmp_path):
    saved = tmp_path / "_saved"
    saved.mkdir()
    audio = saved / "edit.wav"
    _write_wav(audio)

    db = Database(tmp_path / "s.db")
    assert scan_directory(db, saved, extensions=(".wav",), source="local") == 1
    assert db.all_samples()[0].source == "local"

    assert scan_directory(db, saved, extensions=(".wav",), source="edit") == 0

    samples = db.all_samples()
    assert len(samples) == 1
    assert samples[0].source == "edit"
    db.close()


def test_scan_builds_desktop_preview_cache(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    audio = lib / "kick.wav"
    _write_wav(audio)
    calls = []

    def fake_ensure(path, cache_dir, *, file_hash, sample_rate=44100):
        calls.append((path, cache_dir, file_hash, sample_rate))

    monkeypatch.setattr("cratedig.audio.playback.ensure_mono_preview_cache", fake_ensure)

    db = Database(tmp_path / "s.db")
    assert scan_directory(
        db,
        lib,
        extensions=(".wav",),
        preview_cache_dir=tmp_path / "cache",
    ) == 1

    assert calls
    assert calls[0][0] == audio
    assert calls[0][1] == tmp_path / "cache"
    assert len(calls[0][2]) == 40
    assert calls[0][3] == 44100
    db.close()
