# Nazar evaluation report
_Generated 2026-10-23T16:50:30+00:00_

## Sentiment on public benchmarks
Model: `cardiffnlp/twitter-xlm-roberta-base-sentiment`

| Dataset | Lang | n | Accuracy | Macro-F1 | Majority baseline acc / F1 | Predicted neutral |
|---|---|---|---|---|---|---|
| Financial PhraseBank (English financial news) | en | 2264 | 0.663 | 0.457 | 0.614 / 0.254 | 0.898 |
| IndicSentiment, English originals (reviews) | en | 998 | 0.809 | 0.879 | 0.507 / 0.337 | 0.16 |
| IndicSentiment, Hindi translations (same items) | hi | 998 | 0.675 | 0.782 | 0.507 / 0.337 | 0.281 |

## Entities on public benchmarks (entity-level, exact span + type)
Models: English `spacy en_core_web_sm`, Hindi `cfilt/HiNER-collapsed-muril-base-cased`

| Dataset | Lang | Sentences | P / R / F1 | PER F1 | ORG F1 | LOC F1 |
|---|---|---|---|---|---|---|
| CoNLL-2003 test (English news) | en | 3453 | 0.653 / 0.542 / 0.592 | 0.646 | 0.36 | 0.749 |
| Naamapadam test (Hindi news) | hi | 867 | 0.804 / 0.783 / 0.793 | 0.834 | 0.705 | 0.811 |
| HiNER test (Hindi, model's own training distribution) | hi | 21657 | 0.922 / 0.912 / 0.917 | 0.836 | 0.801 | 0.948 |

## Sentiment (our articles, hand labels)
_Optional, not run: no hand labels in labels.csv._

## Entities (our articles, hand labels)
_Optional, not run: no hand labels in labels.csv._

## Narrative clustering
Run 4 (Election Commission CEC Gyanesh Kumar SIR controversy), 152 relevant articles.

| Setup | Narratives | Clustered | Silhouette | Bilingual narratives | Mean cohesion |
|---|---|---|---|---|---|
| Nazar (centered + HDBSCAN leaf) | 12 | 139 | 0.18 | 12 (1.0) | 0.678 |
| KMeans, same k (baseline) | 12 | 152 | 0.157 | 12 (1.0) | 0.662 |
| Without language centering (ablation) | 13 | 132 | 0.161 | 3 (0.231) | 0.708 |

## Intelligence brief
- **brief_3**: evidence coverage 1.0 of 14 claims; faithfulness: 7 supported / 4 partial / 3 unsupported
- **brief_2**: evidence coverage 1.0 of 14 claims; faithfulness: 5 supported / 9 partial / 0 unsupported
- **brief_1**: evidence coverage 1.0 of 14 claims; faithfulness: 8 supported / 6 partial / 0 unsupported
