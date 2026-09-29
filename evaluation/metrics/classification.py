"""Accuracy, per-class precision/recall/F1, macro-F1 and a confusion matrix."""

from collections import Counter


def classification_report(gold: list[str], pred: list[str], labels: list[str]) -> dict:
    if len(gold) != len(pred):
        raise ValueError("gold and pred must be the same length")
    n = len(gold)
    per_class = {}
    for label in labels:
        tp = sum(g == label and p == label for g, p in zip(gold, pred))
        fp = sum(g != label and p == label for g, p in zip(gold, pred))
        fn = sum(g == label and p != label for g, p in zip(gold, pred))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": sum(g == label for g in gold),
        }
    present = [lbl for lbl in labels if per_class[lbl]["support"] > 0]
    return {
        "n": n,
        "accuracy": round(sum(g == p for g, p in zip(gold, pred)) / n, 3) if n else None,
        # macro-F1 averages over classes that occur in the gold labels, so a class
        # with no examples can't drag the score down
        "macro_f1": round(sum(per_class[lbl]["f1"] for lbl in present) / len(present), 3) if present else None,
        "per_class": per_class,
        "confusion": {g: {p: sum(1 for x, y in zip(gold, pred) if x == g and y == p) for p in labels} for g in labels},
    }


def majority_baseline(gold: list[str], labels: list[str]) -> dict:
    """What you'd score by always predicting the most common gold label."""
    majority = Counter(gold).most_common(1)[0][0]
    return {"always_predicts": majority, **classification_report(gold, [majority] * len(gold), labels)}
