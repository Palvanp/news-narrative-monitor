# Nazar evaluation report
_Generated 2026-09-29T12:04:24+00:00_

## Sentiment
_Not run: no sentiment labels yet._

## Entities (people, organisations, places)
_Not run: no entity labels yet._

## Narrative clustering
Run 4 (Election Commission CEC Gyanesh Kumar SIR controversy), 152 relevant articles.

| Setup | Narratives | Clustered | Silhouette | Bilingual narratives | Mean cohesion |
|---|---|---|---|---|---|
| Nazar (centered + HDBSCAN leaf) | 12 | 139 | 0.18 | 12 (1.0) | 0.678 |
| KMeans, same k (baseline) | 12 | 152 | 0.157 | 12 (1.0) | 0.662 |
| Without language centering (ablation) | 13 | 132 | 0.161 | 3 (0.231) | 0.708 |

## Intelligence brief
_Not run: no generated brief yet._
