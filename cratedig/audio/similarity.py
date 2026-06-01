"""Similarity nearest-neighbor search over feature vectors.

Brute-force numpy is fine up to ~100k samples. Swap in hnswlib later for scale
behind the same interface.
"""

from __future__ import annotations

import numpy as np

from .features import ASPECT_BLOCKS, ASPECTS


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


def aspect_topk(
    query: np.ndarray,
    candidates: list[tuple[int, np.ndarray]],
    aspects: list[str] | tuple[str, ...],
    k: int = 20,
    exclude_id: int | None = None,
) -> list[tuple[int, float, dict[str, float]]]:
    """Return up to k (sample_id, combined_score, per_aspect_scores) sorted by combined desc.

    Each aspect score = cosine over that sub-block (ASPECT_BLOCKS slice) of the
    vector, L2-normalized within the slice. combined_score = mean of the selected
    aspects' cosines. Candidates whose vector shape != query shape are skipped
    (stale dim). Empty/invalid aspects defaults to ['Overall'].
    """
    valid_aspects = [a for a in aspects if a in ASPECT_BLOCKS]
    if not valid_aspects:
        valid_aspects = ["Overall"]

    if not candidates:
        return []

    q = query.astype(np.float32)
    usable = [(cid, v) for cid, v in candidates if v.shape == q.shape]
    if not usable:
        return []

    ids = np.array([cid for cid, _ in usable])
    mat = np.vstack([v for _, v in usable]).astype(np.float32)

    # Pre-normalize query slices per aspect
    q_slices: dict[str, np.ndarray] = {}
    for aspect in valid_aspects:
        start, end = ASPECT_BLOCKS[aspect]
        qs = q[start:end]
        qn = float(np.linalg.norm(qs))
        q_slices[aspect] = qs / qn if qn > 1e-9 else qs

    # Compute per-aspect cosines: (n_candidates,) per aspect
    aspect_sims: dict[str, np.ndarray] = {}
    for aspect in valid_aspects:
        start, end = ASPECT_BLOCKS[aspect]
        block = mat[:, start:end]
        norms = np.linalg.norm(block, axis=1, keepdims=True)
        norms = np.where(norms > 1e-9, norms, 1.0)
        block_normed = block / norms
        aspect_sims[aspect] = block_normed @ q_slices[aspect]

    combined = np.mean(np.stack(list(aspect_sims.values()), axis=0), axis=0)
    order = np.argsort(-combined)

    out: list[tuple[int, float, dict[str, float]]] = []
    for idx in order:
        sid = int(ids[idx])
        if exclude_id is not None and sid == exclude_id:
            continue
        per_aspect = {a: float(aspect_sims[a][idx]) for a in valid_aspects}
        out.append((sid, float(combined[idx]), per_aspect))
        if len(out) >= k:
            break
    return out
