"""Narrative clustering quality, without human labels.

- silhouette: how much closer articles are to their own narrative than to the
  nearest other one (-1 bad, 0 overlapping, 1 well separated), cosine distance
- KMeans baseline: the same number of groups found by plain KMeans on the same
  vectors, to check HDBSCAN isn't just drawing arbitrary lines
- bilingual share: fraction of narratives containing both English and Hindi,
  the property language centering is meant to fix
- ablation: the same pipeline without language centering, to measure what
  that step actually changes
"""

from collections import Counter

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from pipeline.clustering.cluster import cluster_embeddings, cohesion, drop_incoherent, remove_language_offsets


def _silhouette(vectors: np.ndarray, labels: np.ndarray) -> float | None:
    mask = labels >= 0
    if len(set(labels[mask].tolist())) < 2:
        return None
    return round(float(silhouette_score(vectors[mask], labels[mask], metric="cosine")), 3)


def describe(raw: np.ndarray, vectors: np.ndarray, labels: np.ndarray, languages: list[str]) -> dict:
    langs = np.array(languages)
    clusters = sorted(set(labels.tolist()) - {-1})
    bilingual = sum(len(set(langs[labels == c])) > 1 for c in clusters)
    return {
        "narratives": len(clusters),
        "clustered_articles": int((labels >= 0).sum()),
        "unclustered_articles": int((labels < 0).sum()),
        "silhouette": _silhouette(vectors, labels),
        "bilingual_narratives": bilingual,
        "bilingual_share": round(bilingual / len(clusters), 3) if clusters else None,
        "mean_cohesion": round(float(np.mean([cohesion(raw[labels == c]) for c in clusters])), 3) if clusters else None,
        "sizes": sorted(Counter(labels[labels >= 0].tolist()).values(), reverse=True),
    }


def evaluate_clustering(raw: np.ndarray, languages: list[str], seed: int = 42) -> dict:
    centered = remove_language_offsets(raw, languages)
    labels, _ = cluster_embeddings(centered, random_state=seed)
    labels = drop_incoherent(raw, labels)
    result = {"pipeline": describe(raw, centered, labels, languages)}

    k = result["pipeline"]["narratives"]
    if k >= 2:
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(centered)
        result["kmeans_same_k"] = describe(raw, centered, km, languages)

    plain = raw / np.linalg.norm(raw, axis=1, keepdims=True)
    ablation, _ = cluster_embeddings(plain, random_state=seed)
    ablation = drop_incoherent(raw, ablation)
    result["without_language_centering"] = describe(raw, plain, ablation, languages)
    return result
