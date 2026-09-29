"""Entity extraction scored per article: does the set of names the model found
match the set the labeller wrote down?

Both sides are canonicalized with the gazetteer first, so "राहुल गांधी" and
"Rahul Gandhi" count as the same entity. Two scores are reported:
- strict: names must match exactly (after canonicalization and casefolding)
- lenient: a match also counts when one name contains the other
  ("Sukhbir Singh" vs "Sukhbir Singh Sandhu")
Only people, organisations and places are scored; policy terms from the
gazetteer (tariffs, trade deal…) are a different kind of output.
"""

from pipeline.entities.extractor import Gazetteer, clean_surface

SCORED_TYPES = {"PERSON", "ORG", "PARTY", "GOV", "LOC", "COUNTRY"}


def normalize(name: str, gazetteer: Gazetteer) -> str | None:
    name = clean_surface(name.split("|")[0])
    if not name:
        return None
    known = gazetteer.canonicalize(name)
    return (known[0] if known else name).casefold()


def parse_gold(cell: str, gazetteer: Gazetteer) -> set[str] | None:
    """'Rahul Gandhi; चुनाव आयोग; Delhi' -> normalized set. 'none' -> empty set. Blank -> not labelled."""
    cell = (cell or "").strip()
    if not cell:
        return None
    if cell.lower() in {"none", "-", "na", "n/a"}:
        return set()
    names = (normalize(part, gazetteer) for part in cell.replace("\n", ";").split(";"))
    return {n for n in names if n}


def _matches(a: str, b: str, lenient: bool) -> bool:
    return a == b or (lenient and (a in b or b in a))


def score_sets(gold_sets: list[set[str]], pred_sets: list[set[str]], lenient: bool = False) -> dict:
    """Micro-averaged precision/recall/F1 over all articles."""
    tp = fp = fn = 0
    for gold, pred in zip(gold_sets, pred_sets):
        matched_gold: set[str] = set()
        for p in pred:
            hit = next((g for g in gold if g not in matched_gold and _matches(p, g, lenient)), None)
            if hit is None:
                fp += 1
            else:
                tp += 1
                matched_gold.add(hit)
        fn += len(gold - matched_gold)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3), "tp": tp, "fp": fp, "fn": fn}
