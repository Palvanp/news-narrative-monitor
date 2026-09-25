"""Evidence selection: which articles represent a narrative, and which sentence in
each article best supports it."""

import re
from collections import Counter

import numpy as np

MMR_LAMBDA = 0.7
MAX_PER_SOURCE = 2
MIN_SENTENCE_CHARS = 40
MAX_SENTENCE_CHARS = 400

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=।)\s*")


def representatives(
    vectors: np.ndarray,
    center: np.ndarray,
    sources: list[str | None],
    k: int = 8,
    mmr_lambda: float = MMR_LAMBDA,
) -> list[int]:
    """Maximal marginal relevance: close to the narrative centroid, but not near
    copies of each other, and at most MAX_PER_SOURCE articles per outlet."""
    n = len(vectors)
    if n == 0:
        return []
    relevance = vectors @ center
    selected: list[int] = []
    per_source: Counter = Counter()
    candidates = set(range(n))
    while candidates and len(selected) < k:
        best, best_score = None, -np.inf
        for i in candidates:
            if sources[i] and per_source[sources[i]] >= MAX_PER_SOURCE:
                continue
            redundancy = max((float(vectors[i] @ vectors[j]) for j in selected), default=0.0)
            score = mmr_lambda * relevance[i] - (1 - mmr_lambda) * redundancy
            if score > best_score:
                best, best_score = i, score
        if best is None:
            break
        selected.append(best)
        candidates.discard(best)
        if sources[best]:
            per_source[sources[best]] += 1
    return selected


# Navigation and promo lines publishers put inside article text.
_BOILERPLATE = re.compile(
    r"^(also read|read more|read also|click here|subscribe|follow us|यह भी पढ़ें|ये भी पढ़ें|इसे भी पढ़ें|और पढ़ें)",
    re.IGNORECASE,
)


# Page furniture that leaks into extracted text (video pages, app promos, datelines).
_JUNK = re.compile(r"https?://|www\.|advertisement|last updated|download the app|mobile app", re.IGNORECASE)
_LEADING_JUNK = re.compile(r"^(with inputs from \w+\s*|quick answers\s*|new delhi:\s*)+", re.IGNORECASE)


def strip_title(body: str, title: str) -> str:
    """Extracted article text often starts with the headline and no full stop,
    which would glue it onto the first sentence."""
    body = body.lstrip()
    return body[len(title) :] if title and body.startswith(title) else body


def split_sentences(text: str, title: str | None = None) -> list[str]:
    if title:
        text = strip_title(text, title)
    parts = (_LEADING_JUNK.sub("", p.strip()) for p in _SENTENCE_END.split(text.replace("\n", " ")))
    return [
        p
        for p in parts
        if MIN_SENTENCE_CHARS <= len(p) <= MAX_SENTENCE_CHARS and not _BOILERPLATE.match(p) and not _JUNK.search(p)
    ]


def best_sentence(sentences: list[str], sentence_vectors: np.ndarray, center: np.ndarray) -> str | None:
    if not sentences:
        return None
    return sentences[int(np.argmax(sentence_vectors @ center))]
