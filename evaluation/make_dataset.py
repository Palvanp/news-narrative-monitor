"""Build the human-labelling set from articles collected by real runs.

    uv run python -m evaluation.make_dataset

Writes, under evaluation/datasets/:
- eval_articles.jsonl: the exact title and text the labeller sees and each
  model is scored on (self-contained, so evaluation doesn't depend on the
  database surviving). Models see only this short text too, so a model isn't
  penalised for names further down the article the labeller never saw.
- labels.csv: what the labeller fills in. Model predictions are deliberately
  not included, so they can't influence the labels.

Sampling: unique articles (by normalized URL) across all runs, up to
N_HINDI Hindi and the rest English, shuffled with a fixed seed. The first
N_ENTITY_PER_LANGUAGE of each language are also marked for entity labelling.
"""

import argparse
import csv
import html
import json
import random
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.db import SessionLocal
from backend.models import Article
from pipeline.evidence.select import strip_title

DATASETS = Path(__file__).parent / "datasets"
SEED = 13
N_TOTAL = 150
N_HINDI = 75
N_ENTITY_PER_LANGUAGE = 25
SNIPPET_CHARS = 400
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=।)\s*")


def lead_text(body: str | None, max_chars: int = SNIPPET_CHARS) -> str:
    """The article's opening sentences, up to max_chars, cut at a sentence end."""
    if not body:
        return ""
    out = ""
    for sentence in _SENTENCE_END.split(body.replace("\n", " ")):
        sentence = sentence.strip()
        if not sentence:
            continue
        if out and len(out) + len(sentence) + 1 > max_chars:
            break
        out = f"{out} {sentence}".strip()
    return out[:max_chars]


def snippet(article: Article) -> str:
    """Opening text without a repeated headline (older runs stored HTML entities)."""
    title = html.unescape(article.title)
    return lead_text(strip_title(html.unescape(article.body or ""), title))


def collect_unique(session) -> list[Article]:
    seen: set[str] = set()
    unique = []
    query = select(Article).where(Article.duplicate_of.is_(None)).options(selectinload(Article.source)).order_by(Article.id)
    for a in session.scalars(query):
        # labels need something to judge beyond the headline
        if a.language in ("en", "hi") and a.body and a.normalized_url not in seen:
            seen.add(a.normalized_url)
            unique.append(a)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="overwrite an existing labels.csv (loses labels!)")
    args = parser.parse_args()

    labels_path = DATASETS / "labels.csv"
    if labels_path.exists() and not args.force:
        raise SystemExit(f"{labels_path} already exists; refusing to overwrite labels (use --force)")

    with SessionLocal() as session:
        articles = collect_unique(session)
    rng = random.Random(SEED)
    hindi = [a for a in articles if a.language == "hi"]
    english = [a for a in articles if a.language == "en"]
    rng.shuffle(hindi)
    rng.shuffle(english)
    hindi = hindi[:N_HINDI]
    english = english[: N_TOTAL - len(hindi)]
    entity_ids = {a.id for a in hindi[:N_ENTITY_PER_LANGUAGE] + english[:N_ENTITY_PER_LANGUAGE]}
    sample = english + hindi
    rng.shuffle(sample)

    DATASETS.mkdir(parents=True, exist_ok=True)
    with open(DATASETS / "eval_articles.jsonl", "w", encoding="utf-8") as f:
        for i, a in enumerate(sample, 1):
            record = {
                "id": f"A{i:03d}",
                "article_id": a.id,
                "language": a.language,
                "source": a.source.domain if a.source else None,
                "url": a.url,
                "title": html.unescape(a.title),
                "text": snippet(a),
                "label_entities": a.id in entity_ids,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # utf-8-sig so Excel opens Hindi text correctly
    with open(labels_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "language", "label_entities", "title", "text", "sentiment", "entities", "notes"])
        for i, a in enumerate(sample, 1):
            writer.writerow([
                f"A{i:03d}",
                a.language,
                "yes" if a.id in entity_ids else "",
                html.unescape(a.title),
                snippet(a),
                "",
                "",
                "",
            ])

    print(f"wrote {len(sample)} articles ({len(english)} English, {len(hindi)} Hindi); "
          f"{len(entity_ids)} marked for entity labelling -> {labels_path}")


if __name__ == "__main__":
    main()
