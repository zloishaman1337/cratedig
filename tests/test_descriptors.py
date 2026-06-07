import numpy as np

from cratedig.audio.descriptors import derive_character_tags


def _tone(freq: float, sr: int = 22050, duration: float = 0.5) -> np.ndarray:
    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


# ---------------------------------------------------------------------------
# Existing tests (kept intact)
# ---------------------------------------------------------------------------

def test_bright_high_frequency_tone():
    tags = derive_character_tags(_tone(8000.0), None, 22050)

    assert "bright" in tags


def test_dark_low_frequency_tone():
    tags = derive_character_tags(_tone(90.0, duration=0.6), None, 22050)

    assert "dark" in tags


def test_reverb_from_late_tail_ratio():
    sr = 22050
    early = np.linspace(1.0, 0.5, int(sr * 0.4), dtype=np.float32)
    late = np.linspace(0.45, 0.25, int(sr * 0.6), dtype=np.float32)
    y = np.concatenate([early, late])

    tags = derive_character_tags(y, None, sr)

    assert "reverb" in tags


def test_short_from_duration():
    tags = derive_character_tags(np.ones(1000, dtype=np.float32), None, 22050)

    assert "short" in tags


def test_wide_from_low_stereo_correlation():
    left = _tone(440.0)
    right = _tone(880.0)
    stereo = np.vstack([left, right])

    tags = derive_character_tags((left + right) / 2.0, stereo, 22050)

    assert "wide" in tags


def test_empty_signal_has_no_tags():
    assert derive_character_tags(np.array([], dtype=np.float32), None, 22050) == []


# ---------------------------------------------------------------------------
# New tags via scalars= injection (deterministic threshold tests)
# ---------------------------------------------------------------------------

def test_punchy_via_scalars():
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(y, None, 22050, scalars={"crest": 7.0, "attack": 0.05})

    assert "punchy" in tags


def test_soft_via_scalars():
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(y, None, 22050, scalars={"crest": 2.0, "attack": 0.30})

    assert "soft" in tags


def test_noisy_via_scalars():
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(y, None, 22050, scalars={"flatness": 0.60, "zcr": 0.35})

    assert "noisy" in tags


def test_clean_via_scalars():
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"flatness": 0.04, "zcr": 0.04, "crest": 5.0},
    )

    assert "clean" in tags


def test_tonal_via_scalars():
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(y, None, 22050, scalars={"flatness": 0.04})

    assert "tonal" in tags


def test_tight_via_scalars():
    # decay <= 0.25 and late_ratio <= 0.06 → tight
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"decay": 0.20, "late_ratio": 0.04, "duration": 0.5},
    )

    assert "tight" in tags


def test_long_tail_via_scalars():
    # decay >= 0.75 and duration >= 1.5 → long-tail
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"decay": 0.80, "duration": 2.0},
    )

    assert "long-tail" in tags


def test_muddy_via_scalars():
    # mid_ratio >= 0.30 and high_ratio <= 0.06 → muddy
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"mid_ratio": 0.35, "high_ratio": 0.04},
    )

    assert "muddy" in tags


def test_airy_via_scalars():
    # very_high_ratio >= 0.12 and very_high_flatness <= 0.25 → airy
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"very_high_ratio": 0.15, "very_high_flatness": 0.20},
    )

    assert "airy" in tags


def test_subby_via_scalars():
    y = _tone(60.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"sub_ratio": 0.40, "mid_band_ratio": 0.08, "high_ratio": 0.03},
    )

    assert "subby" in tags


def test_thin_via_scalars():
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"bass_ratio": 0.04, "sub_ratio": 0.02},
    )

    assert "thin" in tags


def test_crunchy_via_scalars():
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"mid_band_ratio": 0.35, "mid_flatness": 0.50},
    )

    assert "crunchy" in tags


def test_metallic_via_scalars():
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"high_flatness": 0.50, "centroid": 0.40},
    )

    assert "metallic" in tags


def test_percussive_via_scalars():
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"decay": 0.30, "attack": 0.05, "mid_band_ratio": 0.25, "high_ratio": 0.12},
    )

    assert "percussive" in tags


def test_mono_via_scalars():
    # mono fires when corr > 0.97; use a genuine stereo identical pair
    sr = 22050
    y = _tone(440.0, sr=sr, duration=0.5)
    stereo = np.vstack([y, y])  # perfect correlation → mono tag

    tags = derive_character_tags(y, stereo, sr)

    assert "mono" in tags
    assert "wide" not in tags


# ---------------------------------------------------------------------------
# Mutually-exclusive pair assertions
# ---------------------------------------------------------------------------

def test_tight_and_long_tail_never_co_occur():
    # Force tight: decay small, late_ratio small
    y = _tone(440.0, duration=0.5)
    tags_tight = derive_character_tags(
        y, None, 22050,
        scalars={"decay": 0.15, "late_ratio": 0.03, "duration": 0.5},
    )
    assert not ("tight" in tags_tight and "long-tail" in tags_tight)

    # Force long-tail: decay large, duration large
    tags_long = derive_character_tags(
        y, None, 22050,
        scalars={"decay": 0.90, "duration": 2.0},
    )
    assert not ("tight" in tags_long and "long-tail" in tags_long)


def test_mono_and_wide_never_co_occur():
    # wide requires corr < 0.35; mono requires corr > 0.97 — they share the same
    # computed corr, so only one can win.
    sr = 22050
    y = _tone(440.0, sr=sr, duration=0.5)

    # High correlation → mono, not wide
    stereo_mono = np.vstack([y, y])
    tags = derive_character_tags(y, stereo_mono, sr)
    assert not ("mono" in tags and "wide" in tags)

    # Low correlation → wide, not mono
    left = _tone(440.0, sr=sr, duration=0.5)
    right = _tone(880.0, sr=sr, duration=0.5)
    stereo_wide = np.vstack([left, right])
    tags2 = derive_character_tags((left + right) / 2.0, stereo_wide, sr)
    assert not ("mono" in tags2 and "wide" in tags2)


def test_subby_and_thin_never_co_occur():
    # subby: sub_ratio=0.40, mid_band_ratio=0.08, high_ratio=0.03
    # thin: bass_ratio <= 0.06 and sub_ratio <= 0.04 — contradicts subby's sub_ratio
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"sub_ratio": 0.40, "mid_band_ratio": 0.08, "high_ratio": 0.03,
                 "bass_ratio": 0.04},
    )
    assert not ("subby" in tags and "thin" in tags)


def test_punchy_and_soft_never_co_occur():
    # punchy: crest >= 6.0, attack <= 0.08
    # soft: crest <= 2.5, attack >= 0.25 — the elif guarantees exclusion
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(
        y, None, 22050,
        scalars={"crest": 7.0, "attack": 0.05},
    )
    assert not ("punchy" in tags and "soft" in tags)


# ---------------------------------------------------------------------------
# Membership assertion (tag is present, exact list not constrained)
# ---------------------------------------------------------------------------

def test_tag_result_is_list():
    tags = derive_character_tags(_tone(440.0), None, 22050)

    assert isinstance(tags, list)


def test_dedup_no_repeated_tags():
    # The function uses dict.fromkeys — verify no duplicates even if thresholds
    # could theoretically be hit by multiple scalars paths.
    y = _tone(440.0, duration=0.5)
    tags = derive_character_tags(y, None, 22050)

    assert len(tags) == len(set(tags))
