"""Cosine similarity nearest-neighbor search over feature vectors.

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
    dot product equals cosine similarity.
    """
    if not candidates:
        return []
    ids = np.array([cid for cid, _ in candidates])
    mat = np.vstack([v for _, v in candidates]).astype(np.float32)

    q = query.astype(np.float32)
    qn = np.linalg.norm(q)
    if qn > 0:
        q = q / qn

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
