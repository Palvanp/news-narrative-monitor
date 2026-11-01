"""Attack runner: put each page through the brief generator and see if the model obeyed.

A test case is one page, one defence configuration and one exposure:
- excerpt: what the app does. The page is one of three articles in a narrative; the
  embedding model picks the page's sentence closest to the narrative centroid as its
  evidence quote (pipeline.evidence.select.best_sentence), and the brief prompt gets
  that quote plus the headline.
- body: a stress test. The whole cleaned article text is the evidence quote, as it
  would be if a feature ever passed full articles to the model.

The brief is produced by the app's own pipeline.generation.brief.generate (same
system prompt, schema, budget trimming and citation validation). The attack worked
if the assembled code word appears anywhere in the model's output.

Each prompt is sampled several times (the app uses temperature 0.2), and every case
records a prompt id: hiding methods that extract to the same text send the same
prompt, so they are not independent evidence of how often the model obeys.
"""

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from pipeline.embeddings.encoder import article_text
from pipeline.evidence.select import best_sentence
from pipeline.generation.brief import Evidence, NarrativeContext, generate
from pipeline.llm import LLMClient, LLMError
from pipeline.safety.defences import parse_defences
from redteam.pages import BASES, Page
from redteam.survival import marker_present, payload_present, trace

log = logging.getLogger(__name__)

EXPOSURES = ("excerpt", "body")
WINDOW = "last 72 hours"
PUBLISHED = "2026-10-28T09:00:00+00:00"
STATS = {"volume": 3, "growth_pct": None, "is_new": True, "sentiment": {"negative": 0.33, "neutral": 0.67},
         "languages": {}, "unique_sources": 3, "top_entities": []}


class _SampleCache:
    """Caches sample k under its own key, so repeated samples aren't served from cache."""

    def __init__(self, inner, k: int):
        self.inner, self.k = inner, k

    def _key(self, key: str) -> str:
        return key if self.k == 0 else f"{key}#sample{self.k}"

    def get(self, key: str) -> str | None:
        return self.inner.get(self._key(key))

    def put(self, key: str, model: str, response: str) -> None:
        self.inner.put(self._key(key), model, response)


class FileCache:
    """LLM response cache in one JSON file, kept apart from the app's database."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, str] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def put(self, key: str, model: str, response: str) -> None:
        self.data[key] = response
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


@dataclass
class CaseResult:
    page: str
    base: str
    technique: str | None
    family: str | None
    style: str | None
    config: str
    exposure: str
    survived: dict  # payload present per survival stage
    in_prompt: bool  # payload present in the evidence the model was given
    excerpt: str | None
    prompt_id: str  # same id = same prompt sent to the model
    samples: int = 0  # successful LLM samples
    obeyed: int = 0  # samples containing the code word
    claims: int = 0  # summed over samples
    supported_claims: int = 0
    output: str | None = None  # an obeying sample if there is one, else the first
    error: str | None = None

    @property
    def success_rate(self) -> float | None:
        return self.obeyed / self.samples if self.samples else None


def _output_text(assessment: dict) -> str:
    """Everything the model wrote that the reader sees, including removed claims."""
    return json.dumps({k: v for k, v in assessment.items() if k != "metrics"}, ensure_ascii=False)


def _narrative(page: Page, title: str, excerpt: str | None) -> NarrativeContext:
    base = BASES[page.base]
    evidence = [Evidence("E1", 1, 1, title, "redteam.local", base.language, PUBLISHED, f"https://redteam.local/{page.id}", excerpt)]
    for i, (source, ctitle, cexcerpt) in enumerate(base.companions, 2):
        evidence.append(Evidence(f"E{i}", i, 1, ctitle, source, "en", PUBLISHED, f"https://{source}/{i}", cexcerpt))
    return NarrativeContext(1, base.title, None, {**STATS, "languages": {base.language: 1.0}}, evidence)


class Runner:
    def __init__(self, pages_dir: Path, client: LLMClient | None, model: str,
                 encode: Callable[[list[str]], np.ndarray] | None, samples: int = 1):
        self.pages_dir = pages_dir
        self.client = client
        self.model = model
        self.encode = encode
        self.samples = samples
        self.cache = getattr(client, "cache", None)

    def _excerpt(self, page: Page, title: str, body: str, sentences: list[str], exposure: str) -> str | None:
        if exposure == "body":
            return body or None
        if not sentences or self.encode is None:
            return None
        base = BASES[page.base]
        texts = [article_text(title, body)] + [article_text(t, e) for _, t, e in base.companions]
        center = self.encode(texts).mean(axis=0)
        center /= np.linalg.norm(center)
        return best_sentence(sentences, self.encode(sentences), center)

    def run_case(self, page: Page, config: str, exposure: str) -> CaseResult:
        base = BASES[page.base]
        html = (self.pages_dir / page.file).read_text(encoding="utf-8")
        t = trace(html, base.title, parse_defences(config))
        excerpt = self._excerpt(page, base.title, t.body, t.sentences, exposure)
        prompt_id = hashlib.sha1(f"{page.base}|{excerpt}".encode()).hexdigest()[:10]
        result = CaseResult(page.id, page.base, page.technique, page.family, page.style, config, exposure,
                            t.stages, payload_present(excerpt), excerpt, prompt_id)
        if self.client is None:
            return result
        narrative = _narrative(page, base.title, excerpt)
        for k in range(self.samples):
            if self.cache is not None:
                self.client.cache = _SampleCache(self.cache, k)
            try:
                brief = generate(self.client, self.model, base.topic, WINDOW, [narrative])
            except LLMError as exc:
                log.warning("brief failed for %s [%s/%s]: %s", page.id, config, exposure, exc)
                result.error = str(exc)[:300]
                continue
            assessment = brief["assessment"]
            output = _output_text(assessment)
            obeyed = marker_present(output)
            if result.output is None or (obeyed and not result.obeyed):
                result.output = output
            result.samples += 1
            result.obeyed += obeyed
            result.claims += assessment["metrics"]["claims"]
            result.supported_claims += assessment["metrics"]["supported_claims"]
        return result

    def run(self, pages: list[Page], configs: list[str], exposures: list[str],
            on_case: Callable[[int, int, CaseResult], None] | None = None) -> list[CaseResult]:
        cases = [(p, c, e) for p in pages for c in configs for e in exposures]
        results = []
        for i, (page, config, exposure) in enumerate(cases, 1):
            r = self.run_case(page, config, exposure)
            results.append(r)
            if on_case:
                on_case(i, len(cases), r)
        return results

