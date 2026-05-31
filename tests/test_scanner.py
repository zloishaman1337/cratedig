import wave

from cratedig.db import Database
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
    assert {sample.category for sample in db.all_samples()} == {"kick", None}
    db.close()
