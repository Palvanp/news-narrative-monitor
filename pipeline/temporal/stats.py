"""Observed narrative metrics over the monitoring window.

Everything here is deterministic counting. These numbers are shown to the
analyst as observed metrics and passed to the LLM as facts; the LLM never
computes them.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

import numpy as np

N_BINS = 24
SPIKE_Z = 2.0
SPIKE_MIN_COUNT = 3
NEW_MIN_COUNT = 3


@dataclass
class Item:
    published_at: datetime
    language: str | None
    source: str | None
    sentiment: str | None


def bin_edges(start: datetime, end: datetime, n_bins: int = N_BINS) -> list[datetime]:
    step = (end - start) / n_bins
    return [start + step * i for i in range(n_bins + 1)]


def histogram(times: list[datetime], edges: list[datetime]) -> list[int]:
    counts = [0] * (len(edges) - 1)
    for t in times:
        for i in range(len(counts)):
            last = i == len(counts) - 1
            if edges[i] <= t < edges[i + 1] or (last and t == edges[i + 1]):
                counts[i] += 1
                break
    return counts


def spike_bins(counts: list[int]) -> list[int]:
    """Bins whose count exceeds the mean of the other bins by SPIKE_Z standard deviations."""
    arr = np.asarray(counts, dtype=float)
    spikes = []
    for i, c in enumerate(arr):
        if c < SPIKE_MIN_COUNT:
            continue
        rest = np.delete(arr, i)
        if c > rest.mean() + SPIKE_Z * max(rest.std(), 1.0):
            spikes.append(i)
    return spikes


def _share(counter: Counter, total: int) -> dict[str, float]:
    return {k: round(v / total, 3) for k, v in counter.most_common()} if total else {}


def narrative_stats(items: list[Item], start: datetime, end: datetime, n_bins: int = N_BINS) -> dict:
    """Volume, growth (second half vs first half of the window), sentiment,
    language and source distributions, timeline and spikes."""
    mid = start + (end - start) / 2
    previous = [it for it in items if it.published_at < mid]
    current = [it for it in items if it.published_at >= mid]

    growth_pct = None if not previous else round(100 * (len(current) - len(previous)) / len(previous), 1)

    def negative_share(group: list[Item]) -> float | None:
        labelled = [it for it in group if it.sentiment]
        return round(sum(it.sentiment == "negative" for it in labelled) / len(labelled), 3) if labelled else None

    neg_prev, neg_cur = negative_share(previous), negative_share(current)
    edges = bin_edges(start, end, n_bins)
    counts = histogram([it.published_at for it in items], edges)
    sources = Counter(it.source for it in items if it.source)
    times = sorted(it.published_at for it in items)

    return {
        "volume": len(items),
        "previous_window": len(previous),
        "current_window": len(current),
        "growth_pct": growth_pct,
        "is_new": not previous and len(current) >= NEW_MIN_COUNT,
        "sentiment": _share(Counter(it.sentiment for it in items if it.sentiment), sum(1 for it in items if it.sentiment)),
        "negative_share_previous": neg_prev,
        "negative_share_current": neg_cur,
        "sentiment_shift_pp": None if neg_prev is None or neg_cur is None else round(100 * (neg_cur - neg_prev), 1),
        "languages": _share(Counter(it.language for it in items if it.language), len(items)),
        "unique_sources": len(sources),
        "top_sources": [{"domain": d, "count": c} for d, c in sources.most_common(5)],
        "timeline": {"edges": [e.isoformat() for e in edges], "counts": counts},
        "spikes": [edges[i].isoformat() for i in spike_bins(counts)],
        "first_seen": times[0].isoformat() if times else None,
        "last_seen": times[-1].isoformat() if times else None,
    }

