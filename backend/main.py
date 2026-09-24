from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.config import get_settings
from backend.db import engine, init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Nazar", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    settings = get_settings()

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = {"ok": True, "dialect": engine.dialect.name}
    except Exception as exc:  # report, don't crash the health check
        db = {"ok": False, "error": str(exc)}

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.ollama_url}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
        llm = {"ok": True, "url": settings.ollama_url, "models": models}
    except Exception:
        llm = {
            "ok": False,
            "url": settings.ollama_url,
            "hint": "Ollama is unreachable. Start the SSH tunnel to the Oracle VM.",
        }

    return {"status": "ok" if db["ok"] else "degraded", "db": db, "llm": llm}
