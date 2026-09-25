from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import routes
from backend.db import get_session, init_db
from backend.main import app
from backend.models import Article, ArticleNarrative, Monitor, MonitoringRun, Narrative, SentimentScore, Source

END = datetime(2026, 9, 24, tzinfo=timezone.utc)


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    padded = np.zeros(1024, dtype=np.float32)
    padded[: len(v)] = v
    return padded / np.linalg.norm(padded)


def stats(volume, growth):
    return {
        "volume": volume, "growth_pct": growth, "is_new": False,
        "sentiment": {"negative": 0.6, "neutral": 0.4}, "languages": {"en": 0.5, "hi": 0.5},
        "unique_sources": 2, "spikes": [], "top_entities": [{"id": 1, "name": "India", "type": "COUNTRY", "articles": 3}],
        "timeline": {"edges": ["a", "b", "c"], "counts": [1, volume - 1]},
    }


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    with Session() as s:
        monitor = Monitor(topic="India-US trade negotiations", languages=["en", "hi"], time_range_hours=24)
        run = MonitoringRun(monitor=monitor, status="completed", window_start=END - timedelta(hours=24), window_end=END, stats={})
        src = Source(domain="a.in")
        s.add_all([monitor, run, src])
        s.flush()
        arts = [
            Article(run_id=run.id, source_id=src.id, url=f"https://a.in/{i}", normalized_url=f"a.in/{i}", title=f"Story {i}", language="en", published_at=END - timedelta(hours=i))
            for i in range(1, 4)
        ]
        s.add_all(arts)
        s.flush()
        dup = Article(run_id=run.id, url="https://b.in/1", normalized_url="b.in/1", title="Story 1", language="en", published_at=END, duplicate_of=arts[0].id, dedup_reason="headline")
        arts[0].sentiment = SentimentScore(model="m", label="negative", positive=0.1, neutral=0.2, negative=0.7)
        n1 = Narrative(run_id=run.id, cluster_label=0, label="Tariff concerns", keywords=["tariff"], centroid=unit([1, 0]), stats=stats(3, 50.0))
        n2 = Narrative(run_id=run.id, cluster_label=1, label="Talks progress", keywords=["talks"], centroid=unit([1, 1]), stats=stats(2, None))
        n1.articles = [
            ArticleNarrative(article_id=arts[0].id, similarity=0.9, is_representative=True, evidence_text="Exporters fear tariffs."),
            ArticleNarrative(article_id=arts[1].id, similarity=0.95, is_representative=False),
        ]
        s.add_all([dup, n1, n2])
        s.commit()

    def override():
        with Session() as s:
            yield s

    started = []
    monkeypatch.setattr(routes, "_start_run", lambda run_id: started.append(run_id))
    monkeypatch.setattr(routes, "_start_brief", lambda brief_id: started.append(("brief", brief_id)))
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        c.started = started
        yield c
    app.dependency_overrides.clear()


def test_create_monitor_starts_a_run(client):
    resp = client.post("/monitors", json={"topic": "Farm bill protests", "languages": ["hi", "en"], "time_range_hours": 48})
    assert resp.status_code == 201
    body = resp.json()
    assert body["languages"] == ["en", "hi"]
    assert body["latest_run"]["status"] == "pending"
    assert client.started == [body["latest_run"]["id"]]


def test_create_monitor_rejects_unsupported_language(client):
    assert client.post("/monitors", json={"topic": "x topic", "languages": ["fr"]}).status_code == 422


def test_narratives_sorted_by_volume_with_card_fields(client):
    cards = client.get("/monitors/1/narratives").json()
    assert [c["label"] for c in cards] == ["Tariff concerns", "Talks progress"]
    assert cards[0]["growth_pct"] == 50.0 and cards[0]["top_entities"][0]["name"] == "India"


def test_evidence_lists_representatives_first_with_syndication(client):
    items = client.get("/narratives/1/evidence").json()
    assert items[0]["is_representative"] and items[0]["evidence_text"] == "Exporters fear tariffs."
    assert items[0]["syndicated_copies"] == 1 and items[0]["sentiment"] == "negative"


def test_related_and_timeline(client):
    related = client.get("/narratives/1/related").json()
    assert related[0]["label"] == "Talks progress" and 0.7 < related[0]["similarity"] < 0.71
    timeline = client.get("/monitors/1/timeline").json()
    assert [s["label"] for s in timeline["series"]] == ["Tariff concerns", "Talks progress"]


def test_brief_lifecycle_endpoints(client):
    assert client.get("/monitors/1/brief").status_code == 404
    brief = client.post("/monitors/1/brief").json()
    assert brief["status"] == "pending" and ("brief", brief["id"]) in client.started
    assert client.get("/monitors/1/brief").json()["id"] == brief["id"]


def test_rerun_blocked_while_run_is_active(client):
    run = client.post("/monitors/1/run").json()
    assert run["status"] == "pending"
    assert client.post("/monitors/1/run").status_code == 409
    assert client.get("/monitors/404").status_code == 404
