import numpy as np

from cratedig.audio.similarity import cosine_topk


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
