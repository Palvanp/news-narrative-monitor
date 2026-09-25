from datetime import datetime, timedelta, timezone

import numpy as np

from pipeline.clustering.keywords import ctfidf_keywords
from pipeline.evidence.select import best_sentence, representatives, split_sentences
from pipeline.temporal.stats import Item, histogram, bin_edges, narrative_stats, spike_bins

START = datetime(2026, 9, 23, tzinfo=timezone.utc)
END = START + timedelta(hours=24)


def items_at(hours, **kw):
    return [Item(published_at=START + timedelta(hours=h), language=kw.get("lang", "en"), source=kw.get("src", "a.in"), sentiment=kw.get("sent", "negative")) for h in hours]


def test_growth_compares_second_half_to_first_half():
    stats = narrative_stats(items_at([1, 2, 13, 14, 15, 16]), START, END)
    assert (stats["previous_window"], stats["current_window"]) == (2, 4)
    assert stats["growth_pct"] == 100.0
    assert stats["is_new"] is False


def test_new_narrative_has_no_growth_pct():
    stats = narrative_stats(items_at([13, 14, 20]), START, END)
    assert stats["growth_pct"] is None and stats["is_new"] is True


def test_sentiment_shift_in_percentage_points():
    items = items_at([1, 2], sent="neutral") + items_at([13, 14], sent="negative")
    stats = narrative_stats(items, START, END)
    assert stats["sentiment_shift_pp"] == 100.0
    assert stats["sentiment"] == {"neutral": 0.5, "negative": 0.5}


def test_histogram_includes_window_end_and_spikes_are_detected():
    edges = bin_edges(START, END, 24)
    assert sum(histogram([START, END], edges)) == 2
    assert spike_bins([1, 0, 1, 0, 9, 1, 0, 1]) == [4]
    assert spike_bins([1, 1, 1, 2]) == []


def test_ctfidf_keywords_separate_clusters_and_handle_hindi():
    texts = ["tariff hike on steel exports", "steel tariff hike", "रूसी तेल आयात पर प्रतिबंध", "रूसी तेल खरीद"]
    kw = ctfidf_keywords(texts, [0, 0, 1, 1], top_k=3)
    assert "steel" in " ".join(kw[0]) and "रूसी" in " ".join(kw[1])


def test_representatives_prefer_central_diverse_sources():
    center = np.array([1.0, 0.0])
    vecs = np.array([[1.0, 0.0], [0.99, 0.14], [0.99, 0.14], [0.6, 0.8]])
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    picked = representatives(vecs, center, ["a", "a", "a", "b"], k=3)
    assert picked[0] == 0
    assert sum(1 for i in picked if i < 3) <= 2  # at most two from source "a"


def test_split_and_best_sentence():
    sentences = split_sentences("Short. The tariff decision will hurt Indian textile exporters badly this quarter. Another sentence about cricket results today.")
    assert len(sentences) == 2
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert best_sentence(sentences, vecs, np.array([1.0, 0.0])) == sentences[0]
