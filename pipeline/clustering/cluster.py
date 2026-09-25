"""Narrative clustering: UMAP to a few dimensions, then HDBSCAN.

HDBSCAN suits narrative discovery because the number of narratives isn't known
in advance and off-topic or one-off articles can stay unclustered (label -1).
Density estimates degrade in 1024 dimensions, hence the UMAP step first.
"""

import numpy as np

UMAP_DIMS = 5


def default_min_cluster_size(n: int) -> int:
    return max(5, n // 40)


def cluster_embeddings(
    vectors: np.ndarray,
    min_cluster_size: int | None = None,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (labels, reduced vectors). Label -1 means unclustered."""
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
    labels = HDBSCAN(min_cluster_size=mcs, cluster_selection_method="eom").fit_predict(reduced)
    return labels, reduced


def centroid(vectors: np.ndarray) -> np.ndarray:
    c = vectors.mean(axis=0)
    return (c / np.linalg.norm(c)).astype(np.float32)
