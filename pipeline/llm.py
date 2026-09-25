"""Minimal Ollama client for structured (JSON-schema) generation.

Ollama runs on a remote CPU server reached through an SSH tunnel, so calls are
slow (tens of seconds to minutes). Every response is cached by a hash of the
full request, so re-running a stage never repeats a call.
"""

import hashlib
import json
import logging
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


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = 600.0, cache: ResponseCache | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache = cache

    def available(self) -> bool:
        # A short connect timeout: the tunnel answers instantly when it is up, while
        # Windows retries a refused local port for ~2 s before reporting failure.
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=httpx.Timeout(5.0, connect=0.5))
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

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
        """Ask for JSON matching `output`'s schema; validate it, retrying once on failure."""
        schema = output.model_json_schema()
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "format": schema,
            "stream": False,
            "keep_alive": "15m",
            "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": num_ctx},
        }
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

        if self.cache and (hit := self.cache.get(key)) is not None:
            try:
                return output.model_validate_json(hit)
            except ValidationError:
                log.warning("discarding invalid cached LLM response %s", key[:12])

        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
                resp.raise_for_status()
                content = resp.json()["message"]["content"]
                result = output.model_validate_json(content)
            except httpx.ConnectError as exc:
                raise LLMUnavailable(f"Ollama unreachable at {self.base_url}; is the SSH tunnel running?") from exc
            except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
                last_error = exc
                log.warning("LLM call failed (attempt %d): %s", attempt, exc)
                continue
            if self.cache:
                self.cache.put(key, model, content)
            return result
        raise LLMError(f"LLM output invalid after retry: {last_error}")
