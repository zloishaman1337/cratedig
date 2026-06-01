from cratedig.audio.category import classify_category, classify_instrument, classify_from_audio


def test_classify_category_from_filename():
    """Test that CATEGORY keywords (drum/bass/synth/pad/vocal/fx/loop/oneshot) are recognized."""
    assert classify_category("/packs/drums/dirty_drum_01.wav") == "drum"
    assert classify_category("/packs/loops/short_loop.wav") == "loop"
    assert classify_category("/packs/bass/sub_bass.wav") == "bass"


def test_classify_category_from_folder_name():
    """Test category is detected from folder names."""
    assert classify_category("/packs/Basses/clean_01.wav") == "bass"


def test_classify_category_unknown():
    """Test that unknown filenames/paths return None."""
    assert classify_category("/packs/misc/texture.wav") is None


def test_classify_instrument_from_filename():
    """Test that INSTRUMENT keywords (kick/snare/hat/clap/tom/cymbal/perc) are recognized."""
    assert classify_instrument("/packs/kicks/dirty_kick_01.wav") == "kick"
    assert classify_instrument("/packs/snares/snare_sample.wav") == "snare"
    assert classify_instrument("/packs/hats/openhihat.wav") == "hat"
    assert classify_instrument("/packs/percussion/clave_hit.wav") == "perc"


def test_classify_instrument_unknown():
    """Test that unknown instruments return None."""
    assert classify_instrument("/packs/misc/texture.wav") is None


def test_kick_is_instrument_not_category():
    """Verify that 'kick' is classified as instrument, not category."""
    assert classify_category("/packs/kicks/kick_01.wav") is None
    assert classify_instrument("/packs/kicks/kick_01.wav") == "kick"


def test_classify_from_audio_loop_category():
    """Test classify_from_audio with duration >= 1.5 yields 'loop' category."""
    cat, instr = classify_from_audio(duration_sec=2.0, centroid_norm=0.3, zcr=0.1)
    assert cat == "loop"
    assert instr is None  # instrument only for short sounds


def test_classify_from_audio_oneshot_category():
    """Test classify_from_audio with 0 < duration < 1.5 yields 'oneshot' category."""
    cat, instr = classify_from_audio(duration_sec=0.5, centroid_norm=0.3, zcr=0.1)
    assert cat == "oneshot"


def test_classify_from_audio_no_duration():
    """Test classify_from_audio with None duration yields None category."""
    cat, instr = classify_from_audio(duration_sec=None, centroid_norm=0.3, zcr=0.1)
    assert cat is None


def test_classify_from_audio_hat_bright():
    """Test that high centroid or high ZCR yields 'hat' instrument."""
    # High centroid → hat
    cat, instr = classify_from_audio(duration_sec=0.5, centroid_norm=0.6, zcr=0.1)
    assert instr == "hat"

    # High ZCR → hat
    cat, instr = classify_from_audio(duration_sec=0.5, centroid_norm=0.3, zcr=0.2)
    assert instr == "hat"


def test_classify_from_audio_kick_dark():
    """Test that low centroid yields 'kick' instrument."""
    cat, instr = classify_from_audio(duration_sec=0.5, centroid_norm=0.1, zcr=0.05)
    assert instr == "kick"


def test_classify_from_audio_snare_mid():
    """Test that mid-range centroid (0.15-0.45) yields 'snare' instrument."""
    cat, instr = classify_from_audio(duration_sec=0.5, centroid_norm=0.3, zcr=0.08)
    assert instr == "snare"


def test_classify_from_audio_missing_descriptors():
    """Test that missing centroid_norm or zcr yields None instrument."""
    cat, instr = classify_from_audio(duration_sec=0.5, centroid_norm=None, zcr=0.1)
    assert instr is None

    cat, instr = classify_from_audio(duration_sec=0.5, centroid_norm=0.3, zcr=None)
    assert instr is None
