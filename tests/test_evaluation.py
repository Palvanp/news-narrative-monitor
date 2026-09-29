from evaluation.metrics.classification import classification_report, majority_baseline
from evaluation.metrics.entities import parse_gold, score_sets
from pipeline.entities.extractor import Gazetteer

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


def test_gold_entities_canonicalize_across_languages_and_blank_means_unlabelled():
    gaz = Gazetteer()
    assert parse_gold("राहुल गांधी; Election Commission; Delhi|LOC", gaz) == {"rahul gandhi", "election commission of india", "delhi"}
    assert parse_gold("none", gaz) == set()
    assert parse_gold("  ", gaz) is None


def test_entity_scores_strict_and_lenient():
    gold = [{"rahul gandhi", "sukhbir singh sandhu"}, set()]
    pred = [{"rahul gandhi", "sukhbir singh"}, {"delhi"}]
    strict = score_sets(gold, pred)
    assert (strict["tp"], strict["fp"], strict["fn"]) == (1, 2, 1)
    lenient = score_sets(gold, pred, lenient=True)
    assert (lenient["tp"], lenient["fp"], lenient["fn"]) == (2, 1, 0)
