from fastapi.testclient import TestClient

from backend.main import app


def test_health_reports_db_and_llm():
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["db"]["ok"] is True
    assert "ok" in body["llm"]  # Ollama may or may not be reachable in tests
