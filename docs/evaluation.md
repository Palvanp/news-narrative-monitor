# Evaluation

How Nazar's components are measured, and the results so far. The raw numbers live in `evaluation/results/metrics.json` and `report.md` (regenerate them with `uv run python -m evaluation.run_eval`).

## What is measured, and how

| Component | Metric | Data | Status |
|---|---|---|---|
| Sentiment | accuracy, macro-F1, vs an always-majority baseline | public benchmarks: Financial PhraseBank (EN news), IndicSentiment (EN + HI, same items) | ✅ results below |
| Entities | entity-level precision / recall / F1 (exact span + type), per type | public benchmarks: CoNLL-2003 (EN news), Naamapadam (HI news), HiNER (HI, in-domain reference) | ✅ results below |
| Narrative clustering | silhouette, bilingual share, cohesion, vs a KMeans baseline and an ablation without language centering | a completed run | ✅ results below |
| Brief | evidence coverage (claims citing real sources); faithfulness via an LLM judge | generated briefs + the LLM | ✅ results below |
| Sentiment / entities on our own articles | as above, on 150 articles from real runs | hand labels (`labels.csv`) | optional, not done |

**Why public benchmarks instead of hand labels.** Labels made by the developer for their own system are slow to make and easy to doubt. Public test sets were labelled by other people, are used in published work, and are reproducible: `run_eval` downloads them on first use (into `data/benchmarks/`). The cost is **domain shift**: none of them is political news from Indian outlets, so each one stands in for part of our setting, as described per result below. The labelling set and guide are kept if someone wants in-domain numbers later.

**Design choices**
- **Benchmarks run the pipeline's own models and thresholds** (the same `MIN_NER_SCORE`, the same spaCy/HiNER setup), not a cleaned-up variant.
- **NER uses the standard CoNLL metric**: an entity counts only if both its exact span and its type (person / organisation / place) match. CoNLL's MISC class has no equivalent in Nazar and isn't scored.
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

### Sentiment (model: `cardiffnlp/twitter-xlm-roberta-base-sentiment`)

| Dataset | Lang | n | Accuracy | Macro-F1 | Majority baseline acc / F1 | Predicted neutral |
|---|---|---|---|---|---|---|
| Financial PhraseBank (English financial news, 3 classes) | en | 2,264 | 0.663 | **0.457** | 0.614 / 0.254 | 89.8% |
| IndicSentiment, English originals (reviews, pos/neg) | en | 998 | 0.809 | 0.879 | 0.507 / 0.337 | 16.0% |
| IndicSentiment, Hindi translations (same items) | hi | 998 | 0.675 | 0.782 | 0.507 / 0.337 | 28.1% |

**Reading the results**
- **The model beats the baseline everywhere, but it is weak on news.** On news sentences it calls 90% of them neutral, while only 61% actually are. It finds only 20% of the positive sentences and 17% of the negative ones. That explains the journal's observation that Hindi protest stories came out "neutral": the model was trained on tweets, where sentiment is loud. News states sentiment through facts ("sales fell 30%").
- **Hindi costs about 13 accuracy points on identical content** (0.809 → 0.675). With IndicSentiment, English and Hindi are the same reviews, so this gap is the language alone. Most of it is extra "neutral" predictions (16% → 28%).
- On IndicSentiment, macro-F1 is higher than accuracy because the gold labels have no neutral class: a "neutral" prediction counts against accuracy and recall, but not against precision.
- **What it means for Nazar:** narrative sentiment shares are best read *relative* (narrative A is more negative than B; English coverage is more negative than Hindi), not as absolute levels. And the Hindi side is likely to under-report polarity. Fine-tuning on news sentiment, or an LLM classifier, is the clear next step.

### Entities (models: spaCy `en_core_web_sm` for English, `cfilt/HiNER-collapsed-muril-base-cased` for Hindi)

| Dataset | Lang | Sentences | Precision / Recall / F1 | Person F1 | Org F1 | Place F1 |
|---|---|---|---|---|---|---|
| CoNLL-2003 test (English Reuters news) | en | 3,453 | 0.653 / 0.542 / **0.592** | 0.646 | 0.360 | 0.749 |
| Naamapadam test (Hindi news, not seen by the model) | hi | 867 | 0.804 / 0.783 / **0.793** | 0.834 | 0.705 | 0.811 |
| HiNER test (Hindi, the model's own training distribution) | hi | 21,657 | 0.922 / 0.912 / 0.917 | 0.836 | 0.801 | 0.948 |

**Reading the results**
- **Hindi NER is solid: 0.79 F1 on Hindi news it was never trained on.** The drop from its in-domain 0.92 is the usual cost of moving to new data. This is the model whose broken tokenizer we repaired (journal, entry 5), so the fix is now measured, not just eyeballed.
- **English is the weaker side, mainly because of organisations (0.36).** Much of CoNLL's test set is sports results, where teams are named by their city ("Glentoran 1 Coleraine 0"), and the small spaCy model tags those as places or misses them. Spans are also sometimes too long ("Karin Kuster (Switzerland" as one person). Our political news has far fewer such cases, and the gazetteer adds parties and government bodies directly. Even so, a larger spaCy model (`en_core_web_trf`) is the obvious upgrade.
- The ranking is counter-intuitive: Hindi beats English here. It reflects model size and training data (a fine-tuned MuRIL vs spaCy's smallest English model), not the languages.

### Intelligence brief

| Brief | Claims | Evidence coverage | Faithfulness (LLM judge): supported / partial / unsupported |
|---|---|---|---|
| 1 | 14 | 100% | 8 / 6 / 0 |
| 2 | 14 | 100% | 5 / 9 / 0 |
| 3 (claims must stand on cited evidence alone) | 14 | 100% | 7 / 4 / 3 |

- **Every claim in every brief cites real, existing evidence.** Citations are validated in code, so an invented source can't get through.
- **About half the claims are fully supported by their citations alone.** "Partial" usually means the claim adds a detail that's in the narrative summary but not in the specific excerpt it cites. All 3 "unsupported" claims in brief 3 describe Nazar's own measured metrics (sentiment share, +1200% growth). They're true, but the judge only sees article text. Giving the judge the metrics, or keeping numbers out of the claims, would resolve this.
- The judge is itself an LLM (gpt-oss-120b), a known weakness. Its verdicts per claim are in `metrics.json` for spot-checking.

### Limitations
- Benchmarks are out of domain for Nazar: financial news, product reviews, Reuters 1996, and general Hindi news, not Indian political coverage from 2026.
- Clustering is measured on a single run and a single topic.
- Brief faithfulness uses an LLM judge without a human check.
