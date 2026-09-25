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


def test_language_centering_groups_same_story_across_languages():
    from pipeline.clustering.cluster import remove_language_offsets

    # story A and story B, each reported in en and hi; hi carries a shared offset
    story_a, story_b, hindi = np.array([1.0, 0, 0, 0]), np.array([0, 1.0, 0, 0]), np.array([0, 0, 0, 3.0])
    vecs = np.stack([story_a, story_b, story_a + hindi, story_b + hindi])
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    raw_sim = vecs[0] @ vecs[2]
    centered = remove_language_offsets(vecs, ["en", "en", "hi", "hi"])
    assert centered[0] @ centered[2] > centered[0] @ centered[1]  # same story beats same language
    assert centered[0] @ centered[2] > raw_sim


def test_attach_unclustered_only_within_cluster_radius():
    from pipeline.clustering.cluster import attach_unclustered

    vecs = np.array([[1.0, 0.0], [0.99, 0.14], [0.97, 0.24], [0.0, 1.0]])
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    labels = attach_unclustered(vecs, np.array([0, 0, -1, -1]))
    assert labels[2] == -1  # further than the cluster's own members
    near = attach_unclustered(vecs, np.array([0, -1, 0, -1]))
    assert near[1] == 0 and near[3] == -1


def test_keywords_ignore_danda_and_evidence_skips_boilerplate():
    kw = ctfidf_keywords(["यह बड़ा फैसला है। आयोग ने कहा।", "दूसरी खबर है। अदालत"], [0, 1], top_k=5)
    assert not any("।" in k for ks in kw.values() for k in ks)
    assert split_sentences("Also Read: Gyanesh Kumar controversy explained in full detail here. The commission denied every allegation made by the opposition today.") == [
        "The commission denied every allegation made by the opposition today."
    ]


def test_evidence_drops_headline_prefix_and_page_furniture():
    title = "CJP's ultimatum to Gyanesh Kumar"
    body = "CJP's ultimatum to Gyanesh Kumar The party said it will begin nationwide protests from October 2. News18 Mobile App - https://onelink.to/x Advertisement more videos here."
    assert split_sentences(body, title) == ["The party said it will begin nationwide protests from October 2."]
    assert split_sentences("With inputs from PTI Quick Answers Rahul Gandhi criticised the commission over the report.") == [
        "Rahul Gandhi criticised the commission over the report."
    ]
