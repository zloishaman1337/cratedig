"""Similarity nearest-neighbor search over feature vectors.

Brute-force numpy is fine up to ~100k samples. Swap in hnswlib later for scale
behind the same interface.
"""

from __future__ import annotations

import numpy as np


def cosine_topk(
    query: np.ndarray,
    candidates: list[tuple[int, np.ndarray]],
    k: int = 20,
    exclude_id: int | None = None,
) -> list[tuple[int, float]]:
    """Return up to k (sample_id, similarity) sorted by similarity desc.

    Vectors are assumed L2-normalized (see features.extract_features), so the
    dot product equals cosine similarity. Candidates with a different vector
    shape are ignored; they were produced by an older analyzer and need re-run.
    """
    if not candidates:
        return []

    q = query.astype(np.float32)
    qn = np.linalg.norm(q)
    if qn > 0:
        q = q / qn
    usable = [(cid, v) for cid, v in candidates if v.shape == q.shape]
    if not usable:
        return []

    ids = np.array([cid for cid, _ in usable])
    mat = np.vstack([v for _, v in usable]).astype(np.float32)

    sims = mat @ q
    order = np.argsort(-sims)

    out: list[tuple[int, float]] = []
    for idx in order:
        sid = int(ids[idx])
        if exclude_id is not None and sid == exclude_id:
            continue
        out.append((sid, float(sims[idx])))
        if len(out) >= k:
            break
    return out
