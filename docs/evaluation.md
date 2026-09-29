# Evaluation

How Nazar's components are measured, and the results so far. The raw numbers live in `evaluation/results/metrics.json` and `report.md` (regenerate them with `uv run python -m evaluation.run_eval`).

## What is measured, and how

| Component | Metric | Needs | Status |
|---|---|---|---|
| Sentiment | accuracy, macro-F1, per class and per language, vs an always-majority baseline | human labels (150 articles) | ⏳ waiting for labels |
| Entities | precision / recall / F1 per article, strict and lenient name matching, per language | human labels (50 articles) | ⏳ waiting for labels |
| Narrative clustering | silhouette, bilingual share, cohesion, vs a KMeans baseline and an ablation without language centering | a completed run | ✅ results below |
| Brief | evidence coverage (claims citing real sources); faithfulness via an LLM judge plus a human spot-check | a generated brief + the LLM | ⏳ waiting for the LLM server |

**Design choices**
- **The labelling set is self-contained** (`evaluation/datasets/eval_articles.jsonl`): 150 unique articles from real runs, 75 English and 75 Hindi, sampled with a fixed seed.
- **Labeller and models see the same short text** (headline + opening ~400 characters), so a model isn't penalised for names the labeller never saw.
- **Model predictions are hidden during labelling**, to avoid anchoring.
- **Entities are compared after canonicalizing both sides** with the gazetteer, so राहुल गांधी = Rahul Gandhi. Only people, organisations and places are scored.
- **"Lenient" name matching** counts containment ("Sukhbir Singh" vs "Sukhbir Singh Sandhu") as a match; strict doesn't. Both are reported.
- **The brief's LLM judge is itself an LLM**, which is a known weakness. Its verdicts are exported so a human can spot-check them.

How to label: [evaluation/LABELLING_GUIDE.md](../evaluation/LABELLING_GUIDE.md).

## Results so far

### Narrative clustering (run 4: Election Commission / CEC controversy, 152 relevant articles)

| Setup | Narratives | Clustered | Silhouette | Narratives with both languages | Mean cohesion |
|---|---|---|---|---|---|
| **Nazar** (language-centered + HDBSCAN leaf) | 12 | 139 | **0.180** | **12 of 12 (100%)** | 0.678 |
| KMeans, same number of groups (baseline) | 12 | 152 | 0.157 | 12 of 12 | 0.662 |
| Without language centering (ablation) | 13 | 132 | 0.161* | **3 of 13 (23%)** | 0.708 |

\* measured on uncentered vectors, so not directly comparable to the rows above.

**Reading the results**
- **Language centering is what makes narratives bilingual:** 100% vs 23% without it. That's the property that makes English-vs-Hindi comparison within a narrative possible.
- **HDBSCAN's groups separate slightly better than KMeans'** with the same number of groups (0.180 vs 0.157). HDBSCAN also leaves 13 outlying articles unassigned instead of forcing them into a group.
- **The absolute silhouette is modest.** All narratives are sub-stories of one controversy and share vocabulary and actors, so they overlap by nature. Silhouette measures separation, not whether each group is one coherent storyline; cohesion and manual inspection cover that.
- The ablation's slightly higher cohesion is expected: same-language groups are tighter, and that tightness is exactly the language bias centering removes.

**Limitations:** a single run, a single topic, and thresholds (cohesion 0.52, relevance 0.33) calibrated on the first two runs. Treat these numbers as indicative.

### Sentiment, entities, brief

Pending labels and the LLM server. This page will be updated with results and error analysis.
