from evaluation.metrics.classification import classification_report, majority_baseline

LABELS = ["negative", "neutral", "positive"]


def test_classification_report_and_baseline():
    gold = ["negative", "negative", "neutral", "positive"]
    pred = ["negative", "neutral", "neutral", "negative"]
    r = classification_report(gold, pred, LABELS)
    assert r["accuracy"] == 0.5
    assert r["per_class"]["negative"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 2}
    assert r["per_class"]["positive"]["f1"] == 0.0
    assert r["macro_f1"] == round((0.5 + 0.667 + 0.0) / 3, 3)
    assert r["confusion"]["positive"]["negative"] == 1
    b = majority_baseline(gold, LABELS)
    assert b["always_predicts"] == "negative" and b["accuracy"] == 0.5


def test_bio_spans_follow_conlleval_and_skip_misc():
    from evaluation.benchmarks import bio_spans

    tags = ["B-PER", "I-PER", "O", "I-LOC", "B-MISC", "B-ORGANIZATION", "I-ORGANIZATION", "I-PER"]
    assert bio_spans(tags) == {("PER", 0, 2), ("LOC", 3, 4), ("ORG", 5, 7), ("PER", 7, 8)}


def test_char_spans_map_back_to_benchmark_words():
    from evaluation.benchmarks import char_span_to_words, word_offsets

    words = ["कांग्रेस", "नेता", "अहमद", "पटेल", "ने"]
    offsets = word_offsets(words)
    text = " ".join(words)
    start = text.index("अहमद")
    assert char_span_to_words(offsets, start, start + len("अहमद पटेल")) == (2, 4)
    # a span that stops mid-word (missing vowel sign) still covers that word
    assert char_span_to_words(offsets, 0, len("कांग्रे")) == (0, 1)


def test_span_scores_are_exact_match_per_type():
    from evaluation.benchmarks import score_spans

    gold = [{("PER", 0, 2), ("LOC", 3, 4)}]
    pred = [{("PER", 0, 2), ("ORG", 3, 4)}]
    s = score_spans(gold, pred)
    assert s["all"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5, "support": 2}
    assert s["PER"]["f1"] == 1.0 and s["LOC"]["recall"] == 0.0
