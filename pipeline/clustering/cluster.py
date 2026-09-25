"""Narrative clustering: language centering, UMAP to a few dimensions, then HDBSCAN.

Multilingual embeddings still carry a per-language offset: an English and a
Hindi report of the same story sit further apart than two English reports of
different stories. Left alone, clusters split by language, which defeats the
English/Hindi comparison. Subtracting each language's mean vector removes that
shared offset while keeping what distinguishes stories.

HDBSCAN suits narrative discovery because the number of narratives isn't known
in advance. "leaf" selection keeps fine-grained storylines instead of merging
them into one broad topic cluster. Density estimates degrade in 1024
dimensions, hence the UMAP step first.
"""

from collections.abc import Sequence

import numpy as np

UMAP_DIMS = 5


def default_min_cluster_size(n: int) -> int:
    return max(5, n // 40)


def normalize(vectors: np.ndarray) -> np.ndarray:
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)


def remove_language_offsets(vectors: np.ndarray, languages: Sequence[str | None]) -> np.ndarray:
    langs = np.array([lang or "" for lang in languages])
    centered = vectors.astype(np.float32).copy()
    if len(set(langs)) > 1:
        for lang in set(langs):
            mask = langs == lang
            centered[mask] -= vectors[mask].mean(axis=0)
    return normalize(centered).astype(np.float32)


def centroid(vectors: np.ndarray) -> np.ndarray:
    c = vectors.mean(axis=0)
    return (c / np.linalg.norm(c)).astype(np.float32)


def attach_unclustered(vectors: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Give each unclustered item to its nearest narrative if it is at least as
    close to that narrative's centroid as the narrative's own least-similar
    member. Items further away than any narrative's members stay unclustered."""
    labels = labels.copy()
    clusters = sorted(set(labels.tolist()) - {-1})
    if not clusters:
        return labels
    centers = np.stack([centroid(vectors[labels == c]) for c in clusters])
    radius = np.array([float((vectors[labels == c] @ centers[k]).min()) for k, c in enumerate(clusters)])
    for i in np.flatnonzero(labels == -1):
        sims = centers @ vectors[i]
        k = int(np.argmax(sims))
        if sims[k] >= radius[k]:
            labels[i] = clusters[k]
    return labels


def cluster_embeddings(
    vectors: np.ndarray,
    min_cluster_size: int | None = None,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Cluster (already language-centered) vectors. Returns (labels, reduced); -1 = unclustered."""
    from sklearn.cluster import HDBSCAN

    n = len(vectors)
    mcs = min_cluster_size or default_min_cluster_size(n)
    if n < 2 * mcs:
        # too few items to find more than one dense group
        return np.zeros(n, dtype=int), vectors

    import umap

    reducer = umap.UMAP(
        n_neighbors=min(15, n - 1),
        n_components=UMAP_DIMS,
        metric="cosine",
        min_dist=0.0,
        random_state=random_state,
    )
    reduced = reducer.fit_transform(vectors)
    labels = HDBSCAN(min_cluster_size=mcs, cluster_selection_method="leaf", copy=True).fit_predict(reduced)
    return attach_unclustered(vectors, labels), reduced


# A narrative is a storyline several articles share, so its articles must be
# close to one another, not just the nearest leftovers. Calibrated on the first
# two real runs: real narratives had mean pairwise similarity >= 0.57 (raw
# bge-m3 vectors), a bag of unrelated articles 0.45. Provisional until the
# evaluation set is labelled.
MIN_NARRATIVE_ARTICLES = 3
MIN_COHESION = 0.52


def cohesion(vectors: np.ndarray) -> float:
    """Mean pairwise cosine similarity of L2-normalized vectors."""
    k = len(vectors)
    if k < 2:
        return 1.0
    sims = vectors @ vectors.T
    return float((sims.sum() - k) / (k * (k - 1)))


def drop_incoherent(raw_vectors: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Unlabel clusters that are too small or too loose to be one storyline."""
    labels = labels.copy()
    for c in set(labels.tolist()) - {-1}:
        mask = labels == c
        if mask.sum() < MIN_NARRATIVE_ARTICLES or cohesion(raw_vectors[mask]) < MIN_COHESION:
            labels[mask] = -1
    return labels
