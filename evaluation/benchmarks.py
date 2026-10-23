"""Sentiment and NER measured on public, human-labelled benchmarks.

These replace hand-labelling our own articles. None of them is political news
from Indian outlets, so each one stands in for part of our setting:

Sentiment (the pipeline's XLM-R model, headline-style short texts)
- Financial PhraseBank, all-annotators-agree subset: English financial news
  sentences, 3 classes. Closest to news.
- IndicSentiment test set: product/service reviews written in English and
  translated into Hindi by humans. Positive/negative only. The same items in
  both languages, so the English-vs-Hindi gap is measured on identical content.

NER (the pipeline's models: spaCy for English, HiNER/MuRIL for Hindi)
- CoNLL-2003 test set: English Reuters news.
- Naamapadam test set: Hindi news sentences, human-annotated. HiNER was not
  trained on it, so it is the fair Hindi number.
- HiNER test set: the data the Hindi model was trained on (held-out split), as
  an in-domain reference point.

NER is scored at entity level (exact span and type, PER/ORG/LOC), the standard
CoNLL metric. Files are downloaded once into data/benchmarks/.
"""

import json
import logging
import random
import zipfile
from pathlib import Path

import httpx

from backend.config import get_settings
from evaluation.metrics.classification import classification_report, majority_baseline

log = logging.getLogger("evaluation")

HF = "https://huggingface.co/datasets"
SOURCES = {
    "conll2003_test.json": f"{HF}/tner/conll2003/resolve/main/dataset/test.json",
    "naamapadam_hi.zip": f"{HF}/ai4bharat/naamapadam/resolve/main/data/hi_IndicNER_v1.0.zip",
    "hiner_test.conll": f"{HF}/cfilt/HiNER-collapsed/resolve/main/data/test.conll",
    "financial_phrasebank.zip": f"{HF}/takala/financial_phrasebank/resolve/main/data/FinancialPhraseBank-v1.0.zip",
    "indicsentiment_hi_test.json": f"{HF}/ai4bharat/IndicSentiment/resolve/main/data/test/hi.json",
}
SENTIMENTS = ["negative", "neutral", "positive"]
NER_TYPES = ("PER", "ORG", "LOC")
# tner/conll2003 label ids
CONLL_LABELS = {0: "O", 1: "B-ORG", 2: "B-MISC", 3: "B-PER", 4: "I-PER", 5: "B-LOC", 6: "I-ORG", 7: "I-MISC", 8: "I-LOC"}
# Gold tag types -> PER/ORG/LOC (MISC and anything else is not scored)
GOLD_TYPES = {"PER": "PER", "PERSON": "PER", "ORG": "ORG", "ORGANIZATION": "ORG", "LOC": "LOC", "LOCATION": "LOC"}
# Model output types -> PER/ORG/LOC. spaCy's GPE (countries, cities) is CoNLL's LOC.
SPACY_TO_CONLL = {"PERSON": "PER", "ORG": "ORG", "GPE": "LOC", "LOC": "LOC", "FAC": "LOC"}

Span = tuple[str, int, int]  # (type, first word, last word + 1)


def benchmark_dir() -> Path:
    return get_settings().data_dir / "benchmarks"


def fetch(name: str) -> Path:
    path = benchmark_dir() / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading %s", SOURCES[name])
        with httpx.stream("GET", SOURCES[name], follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            tmp = path.with_suffix(path.suffix + ".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        tmp.replace(path)
    return path


# ---------- loaders ----------

def load_conll2003() -> list[tuple[list[str], list[str]]]:
    rows = [json.loads(line) for line in fetch("conll2003_test.json").read_text(encoding="utf-8").splitlines() if line.strip()]
    # this copy writes brackets as Penn Treebank tokens, which the tagger has never seen
    brackets = {"-LPR-": "(", "-RPR-": ")", "-LRB-": "(", "-RRB-": ")"}
    return [([brackets.get(w, w) for w in r["tokens"]], [CONLL_LABELS[t] for t in r["tags"]]) for r in rows]


def load_naamapadam() -> list[tuple[list[str], list[str]]]:
    with zipfile.ZipFile(fetch("naamapadam_hi.zip")) as z:
        lines = z.read("hi_test.json").decode("utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return [(r["words"], r["ner"]) for r in rows]


def parse_conll(text: str) -> list[tuple[list[str], list[str]]]:
    sentences, words, tags = [], [], []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            if words:
                sentences.append((words, tags))
            words, tags = [], []
        elif len(parts) >= 2:
            words.append(parts[0])
            tags.append(parts[-1])
    if words:
        sentences.append((words, tags))
    return sentences


def load_hiner() -> list[tuple[list[str], list[str]]]:
    return parse_conll(fetch("hiner_test.conll").read_text(encoding="utf-8"))


def load_financial_phrasebank() -> list[tuple[str, str]]:
    with zipfile.ZipFile(fetch("financial_phrasebank.zip")) as z:
        lines = z.read("FinancialPhraseBank-v1.0/Sentences_AllAgree.txt").decode("latin-1").splitlines()
    rows = []
    for line in lines:
        text, _, label = line.rpartition("@")
        if label.strip() in SENTIMENTS:
            rows.append((text.strip(), label.strip()))
    return rows


def load_indicsentiment() -> list[dict]:
    lines = fetch("indicsentiment_hi_test.json").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return [
        {"en": r["ENGLISH REVIEW"].strip(), "hi": r["INDIC REVIEW"].strip(), "label": r["LABEL"].strip().lower()}
        for r in rows
        if (r.get("LABEL") or "").strip().lower() in SENTIMENTS and r.get("INDIC REVIEW") and r.get("ENGLISH REVIEW")
    ]


# ---------- NER scoring ----------

def bio_spans(tags: list[str]) -> set[Span]:
    """BIO tags -> entity spans of the scored types. An I- tag that doesn't
    continue an entity of its type starts a new one (the usual conlleval rule)."""
    spans: set[Span] = set()
    current: list | None = None  # [type, start]
    for i, tag in enumerate(list(tags) + ["O"]):
        prefix, _, raw = tag.partition("-")
        etype = GOLD_TYPES.get(raw)
        continues = prefix == "I" and current is not None and current[0] == etype
        if current is not None and not continues:
            spans.add((current[0], current[1], i))
            current = None
        if etype and prefix in ("B", "I") and not continues:
            current = [etype, i]
    return spans


def word_offsets(words: list[str]) -> list[tuple[int, int]]:
    offsets, pos = [], 0
    for w in words:
        offsets.append((pos, pos + len(w)))
        pos += len(w) + 1
    return offsets


def char_span_to_words(offsets: list[tuple[int, int]], start: int, end: int) -> tuple[int, int] | None:
    """Character span over ' '.join(words) -> (first word, last word + 1), or None."""
    first = next((i for i, (s, e) in enumerate(offsets) if e > start), None)
    last = next((i for i in range(len(offsets) - 1, -1, -1) if offsets[i][0] < end), None)
    if first is None or last is None or last < first:
        return None
    return first, last + 1


def score_spans(gold: list[set[Span]], pred: list[set[Span]]) -> dict:
    result = {}
    for etype in (None, *NER_TYPES):
        tp = fp = fn = 0
        for g, p in zip(gold, pred):
            g = {s for s in g if etype is None or s[0] == etype}
            p = {s for s in p if etype is None or s[0] == etype}
            tp += len(g & p)
            fp += len(p - g)
            fn += len(g - p)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        result[etype or "all"] = {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3), "support": tp + fn}
    return result


def predict_english(extractor, sentences: list[list[str]]) -> list[set[Span]]:
    from spacy.tokens import Doc

    nlp = extractor._spacy
    docs = (Doc(nlp.vocab, words=words) for words in sentences)  # keep the benchmark's tokenization
    preds = []
    for doc in nlp.pipe(docs, batch_size=64):
        preds.append({(SPACY_TO_CONLL[e.label_], e.start, e.end) for e in doc.ents if e.label_ in SPACY_TO_CONLL})
    return preds


def predict_hindi(extractor, sentences: list[list[str]]) -> list[set[Span]]:
    from pipeline.entities.extractor import MIN_NER_SCORE

    texts = [" ".join(words) for words in sentences]
    preds = []
    for words, ents in zip(sentences, extractor._indic(texts, batch_size=16)):
        offsets = word_offsets(words)
        spans = set()
        for ent in ents:
            etype = GOLD_TYPES.get(ent["entity_group"])
            if ent["score"] < MIN_NER_SCORE or not etype or ent.get("start") is None:
                continue
            words_span = char_span_to_words(offsets, ent["start"], ent["end"])
            if words_span:
                spans.add((etype, *words_span))
        preds.append(spans)
    return preds


def _sample(items: list, limit: int | None, seed: int = 13) -> list:
    if limit is None or len(items) <= limit:
        return items
    return random.Random(seed).sample(items, limit)


def eval_ner_benchmarks(limit: int | None = None) -> dict:
    from pipeline import models

    extractor = models.entities()
    out = {"english_model": "spacy en_core_web_sm", "hindi_model": get_settings().hindi_ner_model, "datasets": {}}
    for name, loader, lang, predict in (
        ("CoNLL-2003 test (English news)", load_conll2003, "en", predict_english),
        ("Naamapadam test (Hindi news)", load_naamapadam, "hi", predict_hindi),
        ("HiNER test (Hindi, model's own training distribution)", load_hiner, "hi", predict_hindi),
    ):
        data = _sample(loader(), limit)
        gold = [bio_spans(tags) for _, tags in data]
        pred = predict(extractor, [words for words, _ in data])
        out["datasets"][name] = {"language": lang, "sentences": len(data), **score_spans(gold, pred)}
        log.info("NER %s: F1 %.3f", name, out["datasets"][name]["all"]["f1"])
    return out


# ---------- sentiment ----------

def eval_sentiment_benchmarks(limit: int | None = None) -> dict:
    from pipeline import models

    classifier = models.sentiment()
    out = {"model": get_settings().sentiment_model, "datasets": {}}

    def score(name: str, lang: str, texts: list[str], gold: list[str], note: str) -> None:
        pred = [p.label for p in classifier.predict(texts)]
        out["datasets"][name] = {
            "language": lang,
            "note": note,
            "model": classification_report(gold, pred, SENTIMENTS),
            "majority_baseline": majority_baseline(gold, SENTIMENTS),
            "predicted_neutral_share": round(pred.count("neutral") / len(pred), 3),
        }
        log.info("sentiment %s: macro-F1 %.3f", name, out["datasets"][name]["model"]["macro_f1"])

    fpb = _sample(load_financial_phrasebank(), limit)
    score("Financial PhraseBank (English financial news)", "en", [t for t, _ in fpb], [g for _, g in fpb], "3 classes")
    indic = _sample(load_indicsentiment(), limit)
    gold = [r["label"] for r in indic]
    note = "positive/negative only: every 'neutral' prediction counts as wrong"
    score("IndicSentiment, English originals (reviews)", "en", [r["en"] for r in indic], gold, note)
    score("IndicSentiment, Hindi translations (same items)", "hi", [r["hi"] for r in indic], gold, note)
    return out
