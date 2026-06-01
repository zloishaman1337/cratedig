import numpy as np

from cratedig.audio.features import ASPECT_BLOCKS, FEATURE_DIM
from cratedig.audio.similarity import cosine_topk, aspect_topk


def test_topk_orders_by_similarity():
    q = np.array([1.0, 0.0], dtype=np.float32)
    cands = [
        (1, np.array([1.0, 0.0], dtype=np.float32)),   # identical
        (2, np.array([0.0, 1.0], dtype=np.float32)),   # orthogonal
        (3, np.array([0.7, 0.7], dtype=np.float32)),   # 45 deg
    ]
    out = cosine_topk(q, cands, k=3)
    assert [i for i, _ in out] == [1, 3, 2]
    assert out[0][1] > out[1][1] > out[2][1]


def test_topk_excludes_self():
    q = np.array([1.0, 0.0], dtype=np.float32)
    cands = [(1, q.copy()), (2, np.array([0.5, 0.5], dtype=np.float32))]
    out = cosine_topk(q, cands, k=5, exclude_id=1)
    assert [i for i, _ in out] == [2]


def test_empty():
    assert cosine_topk(np.zeros(3, dtype=np.float32), [], k=5) == []


def test_topk_skips_vectors_with_old_dimensions():
    q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    cands = [
        (1, np.array([1.0, 0.0], dtype=np.float32)),
        (2, np.array([0.8, 0.2, 0.0], dtype=np.float32)),
    ]

    assert [i for i, _ in cosine_topk(q, cands, k=5)] == [2]


# --- aspect_topk tests ---


def test_aspect_topk_returns_correct_shape():
    """aspect_topk returns (id, combined_score, per_aspect_dict)."""
    # Create a query vector and candidates of length FEATURE_DIM
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    cands = [
        (1, np.ones(FEATURE_DIM, dtype=np.float32)),
        (2, np.zeros(FEATURE_DIM, dtype=np.float32)),
    ]

    out = aspect_topk(q, cands, aspects=["Overall"], k=5)

    assert len(out) == 2
    # First result should be (id, combined_score, per_aspect_dict)
    result_id, combined_score, per_aspect = out[0]
    assert isinstance(result_id, int)
    assert isinstance(combined_score, float)
    assert isinstance(per_aspect, dict)
    assert "Overall" in per_aspect


def test_aspect_topk_respects_k_limit():
    """aspect_topk respects the k parameter."""
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    cands = [
        (i, np.ones(FEATURE_DIM, dtype=np.float32) * (1.0 - i * 0.1))
        for i in range(1, 11)
    ]

    out = aspect_topk(q, cands, aspects=["Overall"], k=3)
    assert len(out) == 3
    assert [i for i, _, _ in out] == [1, 2, 3]


def test_aspect_topk_excludes_self():
    """aspect_topk excludes query sample by exclude_id."""
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    cands = [
        (1, np.ones(FEATURE_DIM, dtype=np.float32)),
        (2, np.ones(FEATURE_DIM, dtype=np.float32) * 0.9),
    ]

    out = aspect_topk(q, cands, aspects=["Overall"], k=5, exclude_id=1)
    assert [i for i, _, _ in out] == [2]


def test_aspect_topk_empty_candidates():
    """aspect_topk returns empty list for empty candidates."""
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    out = aspect_topk(q, [], aspects=["Overall"], k=5)
    assert out == []


def test_aspect_topk_invalid_aspects_defaults_to_overall():
    """Invalid/empty aspects list defaults to ['Overall']."""
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    cands = [(1, np.ones(FEATURE_DIM, dtype=np.float32))]

    # Empty aspects list
    out = aspect_topk(q, cands, aspects=[], k=5)
    assert len(out) == 1
    _, _, per_aspect = out[0]
    assert "Overall" in per_aspect

    # Invalid aspect names
    out = aspect_topk(q, cands, aspects=["NonExistent"], k=5)
    assert len(out) == 1
    _, _, per_aspect = out[0]
    assert "Overall" in per_aspect


def test_aspect_topk_multiple_aspects():
    """aspect_topk computes per-aspect scores for multiple aspects."""
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    cands = [(1, np.ones(FEATURE_DIM, dtype=np.float32))]

    out = aspect_topk(q, cands, aspects=["Overall", "Spectrum", "Timbre"], k=5)
    assert len(out) == 1
    _, _, per_aspect = out[0]

    # All requested aspects should be in the dict
    assert "Overall" in per_aspect
    assert "Spectrum" in per_aspect
    assert "Timbre" in per_aspect
    assert len(per_aspect) == 3


def test_aspect_topk_scores_are_floats():
    """Per-aspect scores are plain Python floats."""
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    cands = [(1, np.ones(FEATURE_DIM, dtype=np.float32))]

    out = aspect_topk(q, cands, aspects=["Overall"], k=5)
    _, combined_score, per_aspect = out[0]

    assert isinstance(combined_score, float)
    assert not isinstance(combined_score, np.floating)
    for score in per_aspect.values():
        assert isinstance(score, float)
        assert not isinstance(score, np.floating)


def test_aspect_topk_combined_is_mean_of_aspects():
    """Combined score is the mean of requested aspect scores."""
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    cands = [(1, np.ones(FEATURE_DIM, dtype=np.float32))]

    aspects_list = ["Spectrum", "Timbre", "Pitch"]
    out = aspect_topk(q, cands, aspects=aspects_list, k=5)
    _, combined_score, per_aspect = out[0]

    # Combined should be mean of the aspect scores
    expected_mean = np.mean([per_aspect[a] for a in aspects_list])
    assert np.isclose(combined_score, expected_mean, atol=1e-5)


def test_aspect_topk_skips_mismatched_dimensions():
    """aspect_topk skips candidates with wrong vector dimensions."""
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    cands = [
        (1, np.ones(FEATURE_DIM, dtype=np.float32)),        # correct size
        (2, np.ones(FEATURE_DIM - 10, dtype=np.float32)),   # wrong size
        (3, np.ones(FEATURE_DIM, dtype=np.float32)),        # correct size
    ]

    out = aspect_topk(q, cands, aspects=["Overall"], k=5)
    assert [i for i, _, _ in out] == [1, 3]


def test_aspect_topk_orders_by_combined_score():
    """Results are ordered by combined score (descending)."""
    q = np.zeros(FEATURE_DIM, dtype=np.float32)
    q[0] = 1.0  # [1, 0, 0, ...]

    cands = [
        (1, np.zeros(FEATURE_DIM, dtype=np.float32)),  # [0, 0, 0, ...] (very different)
        (2, np.zeros(FEATURE_DIM, dtype=np.float32)),  # [0, 0, 0, ...] (very different)
        (3, np.ones(FEATURE_DIM, dtype=np.float32)),   # [1, 1, 1, ...] (similar)
    ]

    out = aspect_topk(q, cands, aspects=["Overall"], k=5)
    # First result should have highest combined score
    assert out[0][1] > out[1][1]


def test_aspect_topk_all_aspects_in_aspect_blocks():
    """aspect_topk works with all aspect names from ASPECT_BLOCKS."""
    q = np.ones(FEATURE_DIM, dtype=np.float32)
    cands = [(1, np.ones(FEATURE_DIM, dtype=np.float32))]

    # Use all aspects from ASPECT_BLOCKS
    out = aspect_topk(q, cands, aspects=list(ASPECT_BLOCKS.keys()), k=5)
    _, _, per_aspect = out[0]

    # All aspect names should be in the result
    for aspect_name in ASPECT_BLOCKS.keys():
        assert aspect_name in per_aspect
