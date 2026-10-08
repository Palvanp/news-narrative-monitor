# Nazar: Multilingual Political Narrative Intelligence

Nazar monitors a fast-moving political event across English and Hindi news, groups the coverage into narratives, tracks how they grow and shift, and produces an evidence-backed intelligence brief.

> Status: in development. See [docs/PLAN.md](docs/PLAN.md) for the build plan and [docs/JOURNAL.md](docs/JOURNAL.md) for what we learned along the way.

## Setup

Requirements: Python 3.11+ with [uv](https://docs.astral.sh/uv/), and Node 20+.

```bash
cp .env.example .env
uv sync                                  # backend dependencies
uv run uvicorn backend.main:app --reload # API on http://localhost:8000
cd frontend && npm install && npm run dev # UI on http://localhost:5173
```

The database defaults to SQLite (`data/nazar.db`, created automatically). To use Postgres + pgvector instead, point `DATABASE_URL` at it. That can be a local `docker compose up -d db`, or a hosted Postgres with pgvector such as Neon or Supabase. Then run `uv sync --extra postgres`.

### LLM
Narrative naming and brief generation use [Groq](https://console.groq.com) by default. Create a free API key at https://console.groq.com/keys and put it in `.env`:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=your-key
```

To use a self-hosted [Ollama](https://ollama.com) server instead (e.g. a cloud VM reached through an SSH tunnel; see [docs/ORACLE_SETUP.md](docs/ORACLE_SETUP.md)), set `LLM_PROVIDER=ollama` and `OLLAMA_URL`.

`GET /health` (and the status line in the UI) shows whether the database and the LLM are reachable.

### Logs
Each run logs its stages, timings and a summary of where the articles went, both in the terminal running the API and in `data/logs/nazar.log`:

```powershell
Get-Content data\logs\nazar.log -Wait     # PowerShell
tail -f data/logs/nazar.log                 # bash
```

A run can also be started from the command line, without the UI:

```bash
uv run python -m pipeline.run --topic "Election Commission CEC Gyanesh Kumar SIR controversy" --hours 72
```

### Speed
The API server keeps the NLP models loaded between runs (`KEEP_MODELS_LOADED=true`, about 2.5 GB of GPU memory). The first run after starting the server loads them; later runs reuse them. Set it to `false` to free that memory after every run.

## Tests

```bash
uv run pytest
```
