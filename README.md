# Nazar: Multilingual Political Narrative Intelligence

Nazar monitors a fast-moving political event across English and Hindi news, groups the coverage into narratives, tracks how they grow and shift, and produces an evidence-backed intelligence brief.

> Status: in development. See [docs/PLAN.md](docs/PLAN.md) for the build plan and milestones.

## Setup

Requirements: Python 3.11+ with [uv](https://docs.astral.sh/uv/), and Node 20+.

```bash
cp .env.example .env
uv sync                                  # backend dependencies
uv run uvicorn backend.main:app --reload # API on http://localhost:8000
cd frontend && npm install && npm run dev # UI on http://localhost:5173
```

The database defaults to SQLite (`data/nazar.db`, created automatically). To use Postgres + pgvector instead, point `DATABASE_URL` at it. That can be a local `docker compose up -d db`, or a hosted Postgres with pgvector such as Neon or Supabase. Then run `uv sync --extra postgres`.

### LLM (Ollama on a remote server)
Narrative naming and brief generation use [Ollama](https://ollama.com) on a remote VM (an Oracle Cloud Always Free instance), reached through an SSH tunnel:

```bash
ssh -i key.pem -N -L 11434:localhost:11434 ubuntu@<vm-ip>
```

`GET /health` (and the status line in the UI) shows whether the database and the LLM are reachable.

## Tests

```bash
uv run pytest
```
