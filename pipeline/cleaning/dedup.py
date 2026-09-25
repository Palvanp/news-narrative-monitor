"""Deduplication in three tiers: exact URL, normalized headline, embedding similarity.

Tier 3 runs after embeddings are computed.
Syndicated copies are kept but marked with the canonical item, so narratives
count a story once while the syndication itself stays visible.
"""

import re
import unicodedata
from collections.abc import Sequence

import numpy as np

from pipeline.cleaning.urls import normalize_url
from pipeline.ingestion.gdelt import RawArticle

_SITE_SUFFIX = re.compile(r"\s+[-|–—:]\s+[^-|–—:]{2,60}$")
MIN_HEADLINE_WORDS = 4
NEAR_DUP_THRESHOLD = 0.93


def normalize_headline(title: str) -> str:
    """Casefold, strip a trailing " - Site Name" suffix, punctuation and symbols."""
    title = unicodedata.normalize("NFC", title).strip()
    stripped = _SITE_SUFFIX.sub("", title)
    if len(stripped.split()) >= MIN_HEADLINE_WORDS:
        title = stripped
    chars = [" " if unicodedata.category(ch)[0] in "PS" else ch for ch in title.casefold()]
    return " ".join("".join(chars).split())


def _sort_key(a: RawArticle):
    # earliest first; among simultaneous copies prefer one with a body
    return (a.seen_at, a.body_status != "ok")


def dedup_urls(articles: Sequence[RawArticle]) -> tuple[list[RawArticle], int]:
    """Drop exact-URL repeats (the same article returned by overlapping queries)."""
    seen: dict[str, RawArticle] = {}
    for article in sorted(articles, key=_sort_key):
        seen.setdefault(normalize_url(article.url), article)
    unique = list(seen.values())
    return unique, len(articles) - len(unique)


def headline_duplicates(articles: Sequence[RawArticle]) -> list[int | None]:
    """For each article, the index of the earlier article with the same headline, else None.

    Very short headlines ("Live updates", "Top news") are never matched, since
    identical wording there doesn't mean identical stories.
    """
    order = sorted(range(len(articles)), key=lambda i: _sort_key(articles[i]))
    canonical: dict[str, int] = {}
    result: list[int | None] = [None] * len(articles)
    for i in order:
        key = normalize_headline(articles[i].title)
        if len(key.split()) < MIN_HEADLINE_WORDS:
            continue
        if key in canonical:
            result[i] = canonical[key]
        else:
            canonical[key] = i
    return result


def near_duplicates(
    vectors: np.ndarray,
    languages: Sequence[str | None],
    threshold: float = NEAR_DUP_THRESHOLD,
) -> list[int | None]:
    """Tier 3: for each item, the index of an earlier item it near-duplicates, else None.

    Items must be given in chronological order and vectors L2-normalized.
    Only same-language pairs count: an English and a Hindi report of the same
    event are separate coverage, not syndication. Each item points at the first
    surviving item it matches, so chains collapse onto one canonical copy.
    """
    n = len(vectors)
    result: list[int | None] = [None] * n
    if n == 0:
        return result
    sims = vectors @ vectors.T
    langs = np.array([lang or "" for lang in languages])
    for j in range(1, n):
        candidates = np.flatnonzero((sims[j, :j] >= threshold) & (langs[:j] == langs[j]))
        for i in candidates:
            if result[i] is None:
                result[j] = int(i)
                break
    return result
