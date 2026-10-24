"""Run the evaluation and write evaluation/results/metrics.json + report.md.

    uv run python -m evaluation.run_eval

Sections:
- benchmarks: sentiment and NER on public human-labelled datasets (evaluation/benchmarks.py),
  downloaded on first use; --skip-benchmarks turns them off
- clustering: needs a completed run with narratives in the database
- brief: needs a generated brief (faithfulness also needs the LLM)
"""

import argparse
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

log = logging.getLogger("evaluation")
RESULTS = Path(__file__).parent / "results"


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


def render_benchmarks(results: dict) -> list[str]:
    out = []
    sb = results.get("sentiment_benchmarks")
    out.append("## Sentiment on public benchmarks")
    if sb:
        out += [f"Model: `{sb['model']}`", "", "| Dataset | Lang | n | Accuracy | Macro-F1 | Majority baseline acc / F1 | Predicted neutral |", "|---|---|---|---|---|---|---|"]
        for name, d in sb["datasets"].items():
            m, b = d["model"], d["majority_baseline"]
            out.append(f"| {name} | {d['language']} | {m['n']} | {m['accuracy']} | {m['macro_f1']} | {b['accuracy']} / {b['macro_f1']} | {d['predicted_neutral_share']} |")
    else:
        out.append("_Not run._")
    out.append("")

    nb = results.get("ner_benchmarks")
    out.append("## Entities on public benchmarks (entity-level, exact span + type)")
    if nb:
        out += [f"Models: English `{nb['english_model']}`, Hindi `{nb['hindi_model']}`", "",
                "| Dataset | Lang | Sentences | P / R / F1 | PER F1 | ORG F1 | LOC F1 |", "|---|---|---|---|---|---|---|"]
        for name, d in nb["datasets"].items():
            a = d["all"]
            out.append(f"| {name} | {d['language']} | {d['sentences']} | {a['precision']} / {a['recall']} / {a['f1']} | {d['PER']['f1']} | {d['ORG']['f1']} | {d['LOC']['f1']} |")
    else:
        out.append("_Not run._")
    out.append("")
    return out


def render_report(results: dict) -> str:
    out = [f"# Nazar evaluation report", f"_Generated {results['generated_at']}_", ""]
    out += render_benchmarks(results)

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
    parser.add_argument("--skip-benchmarks", action="store_true", help="skip the public-benchmark sentiment/NER evaluation")
    parser.add_argument("--benchmark-limit", type=int, default=None, help="evaluate at most this many examples per benchmark")
    args = parser.parse_args()
    setup_logging()

    results = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not args.skip_benchmarks:
        from evaluation.benchmarks import eval_ner_benchmarks, eval_sentiment_benchmarks

        results["sentiment_benchmarks"] = eval_sentiment_benchmarks(args.benchmark_limit)
        results["ner_benchmarks"] = eval_ner_benchmarks(args.benchmark_limit)
    results["clustering"] = eval_clustering(args.run_id)
    results["briefs"] = eval_briefs(not args.no_llm)

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "metrics.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS / "report.md").write_text(render_report(results), encoding="utf-8")
    log.info("wrote %s and %s", RESULTS / "metrics.json", RESULTS / "report.md")


if __name__ == "__main__":
    main()
