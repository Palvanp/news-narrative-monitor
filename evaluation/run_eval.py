"""Run the evaluation and write evaluation/results/metrics.json + report.md.

    uv run python -m evaluation.run_eval

Sections run when their inputs exist:
- sentiment / entities: need labels in evaluation/datasets/labels.csv
- clustering: needs a completed run with narratives in the database
- brief: needs a generated brief (faithfulness also needs the LLM)
"""

import argparse
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import select

from backend.config import get_settings
from backend.db import SessionLocal
from backend.logging_setup import setup_logging
from backend.models import Article, Brief, MonitoringRun
from evaluation.metrics.classification import classification_report, majority_baseline
from evaluation.metrics.entities import SCORED_TYPES, normalize, parse_gold, score_sets

log = logging.getLogger("evaluation")
HERE = Path(__file__).parent
DATASETS = HERE / "datasets"
RESULTS = HERE / "results"
SENTIMENTS = ["negative", "neutral", "positive"]


def load_labelled() -> list[dict]:
    articles = {}
    path = DATASETS / "eval_articles.jsonl"
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        articles[record["id"]] = record
    rows = []
    with open(DATASETS / "labels.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["id"] in articles:
                rows.append({**articles[row["id"]], **{k: row.get(k, "") for k in ("sentiment", "entities", "notes")}})
    return rows


def eval_sentiment(rows: list[dict]) -> dict | None:
    from pipeline import models
    from pipeline.sentiment.classifier import sentiment_text

    labelled = [r for r in rows if r["sentiment"].strip().lower() in SENTIMENTS]
    invalid = [r["id"] for r in rows if r["sentiment"].strip() and r["sentiment"].strip().lower() not in SENTIMENTS]
    if invalid:
        log.warning("ignoring %d rows with unrecognised sentiment labels: %s", len(invalid), invalid[:10])
    if not labelled:
        return None
    preds = models.sentiment().predict([sentiment_text(r["title"], r["text"]) for r in labelled])
    result = {"model": get_settings().sentiment_model}
    for lang in ("all", "en", "hi"):
        subset = [(r, p) for r, p in zip(labelled, preds) if lang == "all" or r["language"] == lang]
        if not subset:
            continue
        gold = [r["sentiment"].strip().lower() for r, _ in subset]
        pred = [p.label for _, p in subset]
        result[lang] = {"model": classification_report(gold, pred, SENTIMENTS), "majority_baseline": majority_baseline(gold, SENTIMENTS)}
    result["errors"] = [
        {"id": r["id"], "language": r["language"], "title": r["title"], "gold": r["sentiment"].strip().lower(), "predicted": p.label}
        for r, p in zip(labelled, preds)
        if r["sentiment"].strip().lower() != p.label
    ]
    return result


def eval_entities(rows: list[dict]) -> dict | None:
    from pipeline import models
    from pipeline.entities.extractor import Gazetteer

    gazetteer = Gazetteer()  # cheap; the NER models only load if there are labels to score
    labelled = []
    for r in rows:
        if not r.get("label_entities"):
            continue
        gold = parse_gold(r["entities"], gazetteer)
        if gold is not None:
            labelled.append((r, gold))
    if not labelled:
        return None
    extractor = models.entities()
    mentions = extractor.extract_many([(r["title"], r["text"], r["language"]) for r, _ in labelled])
    preds = [
        {n for n in (normalize(m.canonical, gazetteer) for m in counter if m.type in SCORED_TYPES) if n}
        for counter in mentions
    ]
    result = {"hindi_model": get_settings().hindi_ner_model, "english_model": "spacy en_core_web_sm"}
    for lang in ("all", "en", "hi"):
        idx = [i for i, (r, _) in enumerate(labelled) if lang == "all" or r["language"] == lang]
        if not idx:
            continue
        gold_sets = [labelled[i][1] for i in idx]
        pred_sets = [preds[i] for i in idx]
        result[lang] = {"articles": len(idx), "strict": score_sets(gold_sets, pred_sets), "lenient": score_sets(gold_sets, pred_sets, lenient=True)}
    result["examples"] = [
        {"id": r["id"], "language": r["language"], "missed": sorted(g - p), "extra": sorted(p - g)}
        for (r, g), p in zip(labelled, preds)
        if g != p
    ][:40]
    return result


def eval_clustering(run_id: int | None) -> dict | None:
    from evaluation.metrics.clustering import evaluate_clustering

    with SessionLocal() as session:
        query = select(MonitoringRun).where(MonitoringRun.status == "completed").order_by(MonitoringRun.id.desc())
        runs = [r for r in session.scalars(query) if (r.stats or {}).get("narratives")]
        run = next((r for r in runs if r.id == run_id), None) if run_id else (runs[0] if runs else None)
        if run is None:
            return None
        min_rel = get_settings().relevance_min
        arts = [
            a
            for a in session.scalars(select(Article).where(Article.run_id == run.id, Article.duplicate_of.is_(None)))
            if a.embedding is not None and (a.relevance is None or a.relevance >= min_rel)
        ]
        raw = np.stack([a.embedding.vector for a in arts])
        languages = [a.language for a in arts]
        topic = run.monitor.topic
    return {"run_id": run.id, "topic": topic, "articles": len(arts), **evaluate_clustering(raw, languages)}


def eval_briefs(use_llm: bool) -> dict | None:
    from backend.services.naming import llm_client
    from evaluation.metrics.brief import evaluate_brief

    with SessionLocal() as session:
        briefs = list(session.scalars(select(Brief).where(Brief.status == "completed").order_by(Brief.id.desc())))
        if not briefs:
            return None
        client = llm_client(session) if use_llm else None
        if client is not None and not client.available():
            log.warning("LLM unreachable: skipping the faithfulness judge")
            client = None
        return {f"brief_{b.id}": evaluate_brief(b.content, client, get_settings().llm_brief_model) for b in briefs[:3]}


def render_report(results: dict) -> str:
    out = [f"# Nazar evaluation report", f"_Generated {results['generated_at']}_", ""]

    s = results.get("sentiment")
    out.append("## Sentiment")
    if s:
        out += [f"Model: `{s['model']}`", "", "| Language | n | Accuracy | Macro-F1 | Majority baseline acc / F1 |", "|---|---|---|---|---|"]
        for lang in ("all", "en", "hi"):
            if lang in s:
                m, b = s[lang]["model"], s[lang]["majority_baseline"]
                out.append(f"| {lang} | {m['n']} | {m['accuracy']} | {m['macro_f1']} | {b['accuracy']} / {b['macro_f1']} (always *{b['always_predicts']}*) |")
    else:
        out.append("_Not run: no sentiment labels yet._")
    out.append("")

    e = results.get("entities")
    out.append("## Entities (people, organisations, places)")
    if e:
        out += ["| Language | Articles | Strict P / R / F1 | Lenient P / R / F1 |", "|---|---|---|---|"]
        for lang in ("all", "en", "hi"):
            if lang in e:
                st, le = e[lang]["strict"], e[lang]["lenient"]
                out.append(f"| {lang} | {e[lang]['articles']} | {st['precision']} / {st['recall']} / {st['f1']} | {le['precision']} / {le['recall']} / {le['f1']} |")
    else:
        out.append("_Not run: no entity labels yet._")
    out.append("")

    c = results.get("clustering")
    out.append("## Narrative clustering")
    if c:
        out += [f"Run {c['run_id']} ({c['topic']}), {c['articles']} relevant articles.", "",
                "| Setup | Narratives | Clustered | Silhouette | Bilingual narratives | Mean cohesion |", "|---|---|---|---|---|---|"]
        for key, name in (("pipeline", "Nazar (centered + HDBSCAN leaf)"), ("kmeans_same_k", "KMeans, same k (baseline)"), ("without_language_centering", "Without language centering (ablation)")):
            if key in c:
                d = c[key]
                share = f"{d['bilingual_narratives']} ({d['bilingual_share']})" if d["bilingual_share"] is not None else "n/a"
                out.append(f"| {name} | {d['narratives']} | {d['clustered_articles']} | {d['silhouette']} | {share} | {d['mean_cohesion']} |")
    else:
        out.append("_Not run: no completed run with narratives._")
    out.append("")

    b = results.get("briefs")
    out.append("## Intelligence brief")
    if b:
        for name, d in b.items():
            f = d.get("faithfulness")
            faith = f"{f['supported']} supported / {f['partial']} partial / {f['unsupported']} unsupported" if f else "not judged (LLM unavailable)"
            out.append(f"- **{name}**: evidence coverage {d['evidence_coverage']} of {d['claims']} claims; faithfulness: {faith}")
    else:
        out.append("_Not run: no generated brief yet._")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, default=None, help="run to evaluate clustering on (default: latest with narratives)")
    parser.add_argument("--no-llm", action="store_true", help="skip the LLM faithfulness judge")
    args = parser.parse_args()
    setup_logging()

    rows = load_labelled() if (DATASETS / "labels.csv").exists() else []
    results = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    results["sentiment"] = eval_sentiment(rows) if rows else None
    results["entities"] = eval_entities(rows) if rows else None
    results["clustering"] = eval_clustering(args.run_id)
    results["briefs"] = eval_briefs(not args.no_llm)

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "metrics.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS / "report.md").write_text(render_report(results), encoding="utf-8")
    log.info("wrote %s and %s", RESULTS / "metrics.json", RESULTS / "report.md")


if __name__ == "__main__":
    main()
