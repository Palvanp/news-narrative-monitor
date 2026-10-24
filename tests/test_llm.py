import httpx
import pytest
from pydantic import BaseModel

from backend.config import Settings
from pipeline.llm import GroqClient, LLMUnavailable, estimate_tokens


class Answer(BaseModel):
    label: str


class Recorder:
    """Stands in for httpx.post, replaying canned responses in order."""

    def __init__(self, *responses: httpx.Response):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


def ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_groq_sends_schema_and_reasoning_budget(monkeypatch):
    post = Recorder(ok('{"label": "Tariff talks"}'))
    monkeypatch.setattr(httpx, "post", post)
    result = GroqClient("key").generate("openai/gpt-oss-20b", "sys", "prompt", Answer, num_predict=200)
    assert result.label == "Tariff talks"
    sent = post.calls[0]
    assert sent["url"].endswith("/chat/completions") and sent["headers"]["Authorization"] == "Bearer key"
    assert sent["json"]["response_format"]["json_schema"]["schema"]["properties"] == {"label": {"title": "Label", "type": "string"}}
    assert sent["json"]["max_completion_tokens"] == 200 + GroqClient.REASONING_TOKENS


def test_groq_waits_out_rate_limits(monkeypatch):
    post = Recorder(httpx.Response(429, headers={"retry-after": "2"}), ok('{"label": "x"}'))
    waits = []
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr("pipeline.llm.time.sleep", waits.append)
    assert GroqClient("key").generate("m", "s", "p", Answer).label == "x"
    assert waits == [2.0]


def test_groq_retries_invalid_json_once_with_more_freedom(monkeypatch):
    post = Recorder(httpx.Response(400, json={"error": {"code": "json_validate_failed"}}), ok('{"label": "y"}'))
    monkeypatch.setattr(httpx, "post", post)
    assert GroqClient("key").generate("m", "s", "p", Answer, temperature=0.0).label == "y"
    assert [c["json"]["temperature"] for c in post.calls] == [0.0, 0.5]


def test_groq_bad_key_is_unavailable(monkeypatch):
    monkeypatch.setattr(httpx, "post", Recorder(httpx.Response(401)))
    with pytest.raises(LLMUnavailable):
        GroqClient("bad").generate("m", "s", "p", Answer)
    with pytest.raises(LLMUnavailable):
        GroqClient("").generate("m", "s", "p", Answer)
    assert GroqClient("").available() is False


def test_models_default_per_provider():
    groq = Settings(_env_file=None, llm_provider="groq")
    assert (groq.llm_naming_model, groq.llm_brief_model) == ("openai/gpt-oss-120b", "openai/gpt-oss-120b")
    custom = Settings(_env_file=None, llm_provider="Groq", llm_brief_model="custom")
    assert (custom.llm_naming_model, custom.llm_brief_model) == ("openai/gpt-oss-120b", "custom")
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_provider="openai")


def test_estimate_tokens_counts_devanagari_more_densely():
    assert estimate_tokens("a" * 400) < estimate_tokens("क" * 400)
