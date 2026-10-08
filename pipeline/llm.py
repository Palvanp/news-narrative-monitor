"""LLM clients for structured (JSON-schema) generation.

Two interchangeable providers:
- GroqClient: Groq's hosted API (default). Fast, but the free tier allows only
  ~8K tokens per minute, so rate-limit replies are waited out and retried.
- OllamaClient: a self-hosted Ollama server (e.g. on a VM reached through an
  SSH tunnel). Slow on CPU, no rate limits.

Both expose the same `generate()`. Every response is cached by a hash of the
full request, so re-running a stage never repeats a call.
"""

import hashlib
import json
import logging
import time
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMUnavailable(LLMError):
    pass


class ResponseCache(Protocol):
    def get(self, key: str) -> str | None: ...

    def put(self, key: str, model: str, response: str) -> None: ...


class LLMClient:
    """Shared caching, validation and retry; subclasses implement one request."""

    provider = "llm"
    # Shown to the user when the provider can't be reached.
    unavailable_hint = "The LLM is unreachable."
    # Largest prompt the provider accepts comfortably (None: no limit worth managing).
    max_prompt_tokens: int | None = None

    def __init__(self, timeout: float = 600.0, cache: ResponseCache | None = None):
        self.timeout = timeout
        self.cache = cache

    def available(self) -> bool:
        raise NotImplementedError

    def _payload(self, model: str, system: str, prompt: str, output: type[BaseModel], num_predict: int, temperature: float, num_ctx: int) -> dict:
        raise NotImplementedError

    def _send(self, payload: dict) -> str:
        """Send one request and return the raw JSON text the model produced."""
        raise NotImplementedError

    def generate(
        self,
        model: str,
        system: str,
        prompt: str,
        output: type[T],
        num_predict: int = 400,
        temperature: float = 0.2,
        num_ctx: int = 8192,
    ) -> T:
        """Ask for JSON matching `output`'s schema; validate it, retrying once on failure.

        The retry samples more freely: at temperature 0 the same request tends to
        fail the same way again (e.g. Groq rejecting malformed JSON with a 400)."""
        payload = self._payload(model, system, prompt, output, num_predict, temperature, num_ctx)
        retry_payload = self._payload(model, system, prompt, output, num_predict, max(temperature, 0.5), num_ctx)
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

        if self.cache and (hit := self.cache.get(key)) is not None:
            try:
                return output.model_validate_json(hit)
            except ValidationError:
                log.warning("discarding invalid cached LLM response %s", key[:12])

        last_error: Exception | None = None
        for attempt, request in ((1, payload), (2, retry_payload)):
            try:
                content = self._send(request)
                result = output.model_validate_json(content)
            except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
                last_error = exc
                log.warning("LLM call failed (attempt %d): %s", attempt, exc)
                continue
            if self.cache:
                self.cache.put(key, model, content)
            return result
        raise LLMError(f"LLM output invalid after retry: {last_error}")


class OllamaClient(LLMClient):
    provider = "ollama"

    def __init__(self, base_url: str, timeout: float = 600.0, cache: ResponseCache | None = None):
        super().__init__(timeout, cache)
        self.base_url = base_url.rstrip("/")
        self.unavailable_hint = f"Ollama is unreachable at {self.base_url}. Is the server (or SSH tunnel) running?"

    def available(self) -> bool:
        # A short connect timeout: the tunnel answers instantly when it is up, while
        # Windows retries a refused local port for ~2 s before reporting failure.
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=httpx.Timeout(5.0, connect=0.5))
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def _payload(self, model, system, prompt, output, num_predict, temperature, num_ctx) -> dict:
        return {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "format": output.model_json_schema(),
            "stream": False,
            "keep_alive": "15m",
            "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": num_ctx},
        }

    def _send(self, payload: dict) -> str:
        try:
            resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        except httpx.ConnectError as exc:
            raise LLMUnavailable(self.unavailable_hint) from exc
        resp.raise_for_status()
        return resp.json()["message"]["content"]


class GroqClient(LLMClient):
    """Groq's OpenAI-compatible chat API with JSON-schema output.

    The gpt-oss models reason before answering, and those reasoning tokens count
    against the completion budget, so a fixed allowance is added on top of the
    answer's `num_predict`. Free-tier limits are per minute and count the prompt
    plus the completion budget, which is why prompts are kept under
    `max_prompt_tokens`.
    """

    provider = "groq"
    REASONING_TOKENS = 1024
    MAX_RATE_LIMIT_WAITS = 4
    MAX_WAIT_SECONDS = 65.0

    def __init__(self, api_key: str, base_url: str = "https://api.groq.com/openai/v1", timeout: float = 120.0,
                 cache: ResponseCache | None = None, max_prompt_tokens: int | None = 4500):
        super().__init__(timeout, cache)
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.max_prompt_tokens = max_prompt_tokens
        self.unavailable_hint = (
            "Groq is unreachable or GROQ_API_KEY is missing/invalid. Set it in .env (key from console.groq.com)."
        )

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def available(self) -> bool:
        if not self.api_key:
            return False
        # Listing models costs no tokens and checks both the network and the key.
        try:
            resp = httpx.get(f"{self.base_url}/models", headers=self._headers, timeout=httpx.Timeout(10.0, connect=3.0))
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def _payload(self, model, system, prompt, output, num_predict, temperature, num_ctx) -> dict:
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            # Best-effort schema mode: strict mode rejects schemas with optional fields
            # or length limits. The reply is validated against the Pydantic model anyway.
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": output.__name__, "schema": output.model_json_schema(), "strict": False},
            },
            "temperature": temperature,
            "max_completion_tokens": num_predict,
        }
        if model.startswith("openai/gpt-oss"):
            payload["max_completion_tokens"] = num_predict + self.REASONING_TOKENS
            payload["reasoning_effort"] = "low"
            payload["include_reasoning"] = False
        return payload

    def _send(self, payload: dict) -> str:
        if not self.api_key:
            raise LLMUnavailable(self.unavailable_hint)
        for wait in range(self.MAX_RATE_LIMIT_WAITS + 1):
            try:
                resp = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=self._headers, timeout=self.timeout)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise LLMUnavailable(self.unavailable_hint) from exc
            if resp.status_code in (401, 403):
                raise LLMUnavailable(f"Groq rejected the API key ({resp.status_code}). Check GROQ_API_KEY in .env.")
            if resp.status_code == 413:
                raise LLMError(f"Prompt too large for this Groq plan: {resp.text[:300]}")
            if resp.status_code == 429 and wait < self.MAX_RATE_LIMIT_WAITS:
                delay = min(_retry_after(resp), self.MAX_WAIT_SECONDS)
                log.info("Groq rate limit reached; waiting %.0f s", delay)
                time.sleep(delay)
                continue
            if resp.is_error:  # keep Groq's explanation, e.g. "json_validate_failed"
                raise httpx.HTTPStatusError(f"Groq {resp.status_code}: {resp.text[:400]}", request=resp.request, response=resp)
            return resp.json()["choices"][0]["message"]["content"]
        raise LLMError("Groq rate limit persisted after several waits")


def _retry_after(resp: httpx.Response) -> float:
    try:
        return max(1.0, float(resp.headers.get("retry-after", "10")))
    except ValueError:
        return 10.0


def estimate_tokens(text: str) -> int:
    """Rough, deliberately generous token count: ~4 characters per token for
    Latin script, ~2 for Devanagari and other non-ASCII text."""
    ascii_chars = sum(ch.isascii() for ch in text)
    return int(ascii_chars / 4 + (len(text) - ascii_chars) / 2) + 1
