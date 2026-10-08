import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api.routes import router
from backend.config import get_settings
from backend.db import engine, init_db
from backend.logging_setup import setup_logging
from backend.services.naming import make_client

setup_logging()


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
app.include_router(router)


_llm_ok_at: float | None = None


async def llm_available(client) -> bool:
    """The UI polls /health every 15 s; once the LLM answers, re-check it at most
    once a minute. Failures are re-checked on every poll, so a fix shows up quickly."""
    global _llm_ok_at
    if _llm_ok_at is not None and time.monotonic() - _llm_ok_at < 60:
        return True
    ok = await run_in_threadpool(client.available)
    _llm_ok_at = time.monotonic() if ok else None
    return ok


@app.get("/health")
async def health() -> dict:
    settings = get_settings()

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = {"ok": True, "dialect": engine.dialect.name}
    except Exception as exc:  # report, don't crash the health check
        db = {"ok": False, "error": str(exc)}

    client = make_client()
    llm = {"ok": await llm_available(client), "provider": client.provider,
           "naming_model": settings.llm_naming_model, "brief_model": settings.llm_brief_model}
    if not llm["ok"]:
        llm["hint"] = client.unavailable_hint

    return {"status": "ok" if db["ok"] else "degraded", "db": db, "llm": llm}
