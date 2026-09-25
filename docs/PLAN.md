# Nazar: Build Plan

> **Changes since this plan was written** (details in [JOURNAL.md](JOURNAL.md)): news comes from publisher RSS feeds (GDELT's API rate-limits us; kept behind `NEWS_SOURCES`); SQLite is the default database; Hindi NER uses the open HiNER (MuRIL) model because IndicNER is gated; clustering removes per-language offsets and requires a minimum cohesion; runs with too little coherent coverage end with an explicit "not enough coverage" outcome.

## Context
`../Nazar_Project_Description.md` describes **Nazar**, a prototype that monitors a fast-moving political event in English and Hindi news, groups the coverage into narratives, tracks how each narrative grows and how its sentiment and entities change, and writes an evidence-backed brief for an analyst. The repo (`news-narrative-monitor/`) is empty right now: it has only a LICENSE, a Python .gitignore and a one-line README. This plan builds the full V1 (spec §17) plus the evaluation harness (§15).

**Decisions made with the user:** **Ollama running on an Oracle Cloud Always Free VM** (CPU, reached through an SSH tunnel), **SQLite for V1 (Docker is not working yet); PostgreSQL + pgvector in Docker once it is**, and full V1 + evaluation. Reddit and the other add-ons (§18) are out of scope.

**Machine:** Windows 11, Python 3.13.7, Node 22, RTX 3050 6 GB, WSL2 (Ubuntu). Docker Desktop is installed at `C:\Program Files\Docker\Docker`, but it isn't on this shell's PATH. Ollama is not installed.

## Prerequisites (the user does these once)
1. **Docker (Postgres + pgvector):** start Docker Desktop and let the engine start (WSL2 backend). **Restart Claude Code** from a new terminal so `docker` is on PATH. Until then I'll call `"C:\Program Files\Docker\Docker\resources\bin\docker.exe"` directly. `docker-compose.yml` runs only the `pgvector/pgvector:pg17` image (port 5432, named volume, credentials in `.env`). The migration runs `CREATE EXTENSION vector`. Python runs natively so it can use the local GPU for the NLP models.
2. **Oracle Always Free LLM server** (the user does this; I'll guide each step):
   - cloud.oracle.com signup → create instance **VM.Standard.A1.Flex, 4 OCPU / 24 GB RAM, Ubuntu** → save the SSH key.
   - On the VM: `curl -fsSL https://ollama.com/install.sh | sh`, then `ollama pull qwen2.5:7b-instruct` and `ollama pull qwen2.5:3b-instruct`.
   - From the laptop, keep a tunnel open while using Nazar: `ssh -i key.pem -N -L 11434:localhost:11434 ubuntu@<ip>`. **Never open port 11434 publicly**, because Ollama has no authentication.
   - Nazar's `.env` sets `OLLAMA_URL=http://localhost:11434`, so the code is the same as for a local install.
3. I'll install PyTorch with the CUDA wheel (cu126, which supports Py3.13) in the project venv.

## LLM on a CPU server: design for slow inference
A 4-core ARM CPU runs a 7B q4 model at roughly a few tokens/s, so each call takes tens of seconds to a few minutes. `pipeline/llm.py` handles this:
- **Two models by task:** `qwen2.5:3b-instruct` for narrative naming (short outputs, many calls) and `qwen2.5:7b-instruct` for the single brief call. Both are configurable in `.env`.
- **Compact prompts:** at most ~8 headlines per narrative for naming. For the brief, at most ~5 evidence items per narrative with short evidence sentences, and `num_predict` caps on output length.
- **Calls run one at a time**, with a 600 s timeout and one retry. The run-status stage shows "naming narrative 3/9", so the UI shows progress through the slow step.
- **Cache keyed by prompt hash** (in a DB table), so re-running or re-rendering never repeats an LLM call.
- **Health check:** `GET /health` reports whether Ollama is reachable. If the tunnel is down, the run stops before the LLM stages with a clear message ("start the SSH tunnel"). The deterministic results (clusters, stats, evidence) are still saved, and naming falls back to keyword labels.

## GPU: no fine-tuning needed
V1 uses **only pretrained models for inference**, with no training. With the LLM on Oracle, the local 6 GB GPU runs only the NLP models (bge-m3 fp16 ~1.2 GB, XLM-R sentiment ~0.6 GB, IndicNER ~0.7 GB, ~2.5 GB total). A few thousand articles take a few minutes.

Fallbacks, each a single config switch in `.env`:
- **Embeddings:** `intfloat/multilingual-e5-base` (smaller), or run bge-m3 on CPU (slower but fine for under 2k docs).
- **Fine-tuning** (spec §16 optional extension, *not planned*): if it's attempted later, run the LoRA/PEFT job on a free **Kaggle or Colab T4** using the labelled CSV from `evaluation/`, not locally. Only the document scaffolding (dataset format, split script, a note in `docs/methodology.md`) will be added.

## Repository layout (spec §20, at the repo root)
```
backend/   main.py, api/, models/ (SQLAlchemy), schemas/ (Pydantic), services/ (runner, retrieval), db.py, config.py
pipeline/  ingestion/ cleaning/ language/ entities/ sentiment/ embeddings/ clustering/ narratives/ temporal/ evidence/ generation/ llm.py
frontend/  React + Vite + TS
evaluation/ datasets/ metrics/ results/ run_eval.py
docs/      architecture.md methodology.md evaluation.md
alembic/, tests/, docker-compose.yml, .env.example, pyproject.toml (uv/pip), README.md
```

## Pipeline design (each stage is a pure module; `backend/services/runner.py` runs them in order)

| Stage | Implementation |
|---|---|
| **Ingestion** `pipeline/ingestion/gdelt.py` | GDELT DOC 2.0 API (`mode=artlist&format=json&maxrecords=250`). The monitor period is split into sub-windows (e.g. 6×4h for 24h) × `sourcelang:english` / `sourcelang:hindi` to get past the 250-record cap and cover the full period. Requests are throttled to 1 per 5 s, with retry/backoff via `httpx`. GDELT matches non-English articles against its English machine translation, so English keywords also find Hindi coverage, and the monitor also accepts optional Hindi keywords. Raw responses are cached under `data/cache/` so runs can be reproduced offline. Article bodies are fetched asynchronously (10 at a time, 10 s timeout) and extracted with **trafilatura**. If that fails, the item falls back to title only. |
| **Cleaning** `pipeline/cleaning/` | Strip HTML (selectolax), apply Unicode NFC, normalize whitespace, drop malformed or very short text. URL normalization: lowercase the host, remove `www`/`amp`, `utm_*` parameters and fragments. |
| **Dedup** `pipeline/cleaning/dedup.py` | (1) exact normalized URL → (2) normalized-headline hash → (3) embedding cosine ≥ 0.93 within the same language (runs after the embedding stage). Duplicates keep `duplicate_of`, so syndication is still visible, but they are left out of narrative counts. |
| **Language** `pipeline/language/` | **lingua** restricted to EN/HI, cross-checked against GDELT's language field. |
| **Embeddings** | `BAAI/bge-m3` via sentence-transformers, fp16 on CUDA, 1024-d dense vectors from title + lead (~400 tokens). Stored in pgvector. |
| **Sentiment** | `cardiffnlp/twitter-xlm-roberta-base-sentiment` (multilingual, including Hindi) on title + lead. The domain shift from tweets to news is measured in evaluation. |
| **Entities** | English uses spaCy `en_core_web_sm` (PERSON/ORG/GPE/NORP/LAW/EVENT); Hindi uses `ai4bharat/IndicNER`. A YAML gazetteer adds political parties and policy terms (tariffs, exports, भाजपा…). A YAML alias map canonicalizes names across languages (अमेरिका → United States). The top unmapped Hindi entities are sent to the LLM in one batch for transliteration and translation. |
| **Clustering** | UMAP (5-d, cosine) → `sklearn.cluster.HDBSCAN` (min_cluster_size ≈ max(5, n/40)); outliers stay unclustered. Because the embeddings are multilingual, English and Hindi articles about the same story land in the same narrative, which is what enables the per-narrative EN/HI comparison. Per-narrative keywords come from c-TF-IDF. |
| **Narrative naming** `pipeline/narratives/` | For each cluster, ~8 representative headlines are chosen (closest to the centroid, MMR-diversified across languages and sources) and sent to Ollama together with the top entities, keywords and date span. Ollama returns `{label, summary}` via a `format` JSON schema, and the output is validated with Pydantic. On failure it retries once, then falls back to a label built from the keywords. |
| **Temporal** `pipeline/temporal/` | Items are binned by publication hour. Growth = (current half − previous half) / max(prev, 1). The stage also computes the change in negative-sentiment share, language and source distribution, a `new` flag (prev = 0 and cur ≥ threshold), and spike bins (z > 2 against the rolling mean). **These are all deterministic numbers, stored apart from anything the LLM writes.** |
| **Evidence** `pipeline/evidence/` | For each narrative: representative articles with a similarity score, plus an `evidence_text` (the body sentence closest to the narrative centroid, found by embedding the sentences). These are stored in `article_narratives`. A "related narratives" list comes from pgvector cosine similarity between centroids. |
| **Brief** `pipeline/generation/` | A context builder numbers each evidence item `[E12]` and sends it with the stats. The LLM returns JSON `{executive_summary, key_developments:[{claim, evidence_ids}], narratives:[{narrative_id, assessment, evidence_ids}], narrative_shift, key_entities}`. Validation drops claims whose evidence IDs don't exist or that cite nothing, and marks them in the output. The rendered brief keeps the **Observed metrics** section (filled from stats, never generated) separate from the **Assessment** section (LLM, cited). The brief can be exported as Markdown. |

`pipeline/llm.py` is a thin Ollama client (httpx → `OLLAMA_URL/api/chat`, `format=<schema>`, temperature 0.2, prompt-hash cache, long timeout), used for both naming and briefs. It talks to the Oracle VM through the SSH tunnel.

## Database strategy (updated 2026-09-24)
Docker Desktop fails to start on this machine, so V1 runs on **SQLite** (`DATABASE_URL=sqlite:///data/nazar.db`).
- Models use portable types: `JSON` (not JSONB), and an `Embedding` TypeDecorator that maps to pgvector `Vector(1024)` on Postgres and float32 `LargeBinary` on SQLite.
- Similarity search (related narratives, near-dup) goes through `backend/services/vector_search.py`: numpy cosine on SQLite, pgvector `<=>` on Postgres.
- Tables are created with `Base.metadata.create_all` for now. Alembic is added when switching to Postgres.
- Switching later means `docker compose up -d db` plus changing `DATABASE_URL`, with no code changes.

## Data model (SQLAlchemy 2; psycopg3 + pgvector-python once on Postgres)
The spec's tables plus `monitors`: `monitors`, `monitoring_runs` (status, stage, progress, error), `sources`, `articles` (url, normalized_url, title, body, lang, published_at, source_id, duplicate_of, run_id), `embeddings` (Vector(1024)), `sentiment_scores`, `entities`, `article_entities`, `narratives` (label, summary, centroid Vector, stats JSONB, keywords), `article_narratives` (similarity, is_representative, evidence_text), `briefs` (json, markdown).

## API (FastAPI; the pipeline runs as a background task and the UI polls run status)
`POST /monitors` · `GET /monitors` · `GET /monitors/{id}` · `POST /monitors/{id}/run` · `GET /runs/{id}` (stage/progress) · `GET /monitors/{id}/narratives` · `GET /monitors/{id}/timeline` · `GET /narratives/{id}` · `GET /narratives/{id}/evidence` · `GET /narratives/{id}/related` · `POST /monitors/{id}/brief` · `GET /briefs/{id}`

## Frontend (React + Vite + TS, react-router, TanStack Query, Recharts, plain CSS)
1. **Monitor creation**: topic, optional Hindi keywords, time range (6h/24h/72h/7d), EN/HI checkboxes, then Start. A progress screen shows the current pipeline stage.
2. **Narrative Command Center**: overall totals (items, unique sources, EN/HI split), narrative cards (label, item count, growth ↑/↓ %, sentiment bar, top entities, NEW/SPIKE badges, Investigate button), and a stacked-area timeline of coverage per narrative.
3. **Narrative Investigation**: summary, growth, sentiment and language splits, entity chips, a timeline (first detected → source sequence → spikes), an evidence panel (headline, source, time, language, evidence sentence, link), and related narratives.
4. **Intelligence Brief**: executive summary, observed metrics, assessment with clickable `[E#]` citations that jump to evidence, the list of sources, and export to Markdown.

## Evaluation (`evaluation/`)
- `make_dataset.py` exports ~150 stratified EN/HI articles from a real run to CSV for **manual labelling by the user** (sentiment + entity spans, about 1 hour). I can't produce labels that count as gold.
- Sentiment: accuracy and macro-F1 per language, against a majority-class baseline.
- NER: span-level P/R/F1 per language.
- Clustering: silhouette score (UMAP space), compared with a KMeans(k = #HDBSCAN clusters) baseline, plus a coherence/distinctness sheet for manual scoring.
- Brief: *evidence coverage* (share of claims with ≥ 1 valid citation, computed automatically), *faithfulness* (an LLM judge checks each claim against its cited evidence, plus claim–evidence embedding similarity, then a manual spot-check), and relevance (manual).
- Results go to `evaluation/results/*.json`, with a write-up in `docs/evaluation.md` that includes failure analysis.

## Build order (each milestone ends working and committed)
0. Copy this plan to `docs/PLAN.md` in the repo and save a project memory that points to it, so the plan survives terminal restarts.
1. Scaffold: pyproject + venv, config/.env, DB models on SQLite (portable to Postgres), FastAPI health check, Vite app. `docker-compose.yml` is written but not required yet.
2. GDELT ingestion + cleaning + URL/headline dedup + language, tested with a CLI: `python -m pipeline.run --topic "India-US trade negotiations" --hours 24`.
3. NLP enrichment: embeddings, near-dup dedup, sentiment, entities.
4. Clustering + naming + temporal stats + evidence.
5. Brief generation + validation.
6. API endpoints + background runner.
7. Frontend, all four views.
8. End-to-end integration on the demo topic.
9. Evaluation harness + docs (architecture diagram as Mermaid in README/docs) + README with setup, screenshots and limitations (spec §23).

## Verification
- **Unit tests** (`pytest`): URL normalization, dedup tiers, temporal growth/spike math, brief citation validation, Ollama JSON-schema parsing (mocked), and GDELT response parsing (from a cached fixture).
- **Pipeline smoke test**: the CLI run on "India-US trade negotiations", last 24h. Checks that EN and HI articles are both present, that there are more than 3 clusters, and that every narrative has a label, stats and ≥ 3 evidence items.
- **API**: `uvicorn backend.main:app`, then go through the endpoints with httpx/`/docs`.
- **End to end in the browser**: create a monitor → watch progress → dashboard → investigate a narrative → generate a brief → confirm every `[E#]` resolves to a real article link.
- **Evaluation**: `python -m evaluation.run_eval` produces the metrics JSON once the labels are filled in.
