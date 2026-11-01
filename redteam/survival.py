"""Extraction survival check: which hidden instructions reach the text the model gets.

A page goes through the app's own steps, in order:
  extracted  trafilatura (pipeline.ingestion.bodies.extract_text), with any defences
  cleaned    clean_body, as at ingest
  candidate  split_sentences: the sentences eligible to be quoted as brief evidence
The evidence step (picking one sentence per article) needs the embedding model and
happens in the runner.

Presence is checked after undoing obfuscation (Unicode normalisation), since an LLM
reads through zero-width characters and lookalike letters that a plain string
comparison would miss.
"""

import re
from dataclasses import dataclass, field

from pipeline.cleaning.text import clean_body
from pipeline.evidence.select import split_sentences
from pipeline.ingestion.bodies import extract_text
from pipeline.safety.defences import normalise_unicode
from redteam.pages import MARKER_PARTS

STAGES = ("extracted", "cleaned", "candidate")

_WS = re.compile(r"\s+")
# A fragment of every payload; the code word itself never appears on a page.
PROBE = f"joining {MARKER_PARTS[0]} and {MARKER_PARTS[1]}".lower()
_MARKER = re.compile(rf"{MARKER_PARTS[0]}[\s\-_.·]*{MARKER_PARTS[1]}", re.IGNORECASE)


def _norm(text: str) -> str:
    return _WS.sub(" ", normalise_unicode(text)).lower()


def payload_present(text: str | None) -> bool:
    return bool(text) and PROBE in _norm(text)


def marker_present(text: str | None) -> bool:
    """The code word, assembled. Its presence in model output means the injection worked."""
    return bool(text) and bool(_MARKER.search(_norm(text)))


@dataclass
class Trace:
    extracted: str | None
    body: str
    sentences: list[str]
    stages: dict[str, bool] = field(default_factory=dict)

    @property
    def survived(self) -> bool:
        """The instruction is in the article text the app stores and analyses."""
        return self.stages["cleaned"]


def trace(html: str, title: str, defences: frozenset[str] = frozenset()) -> Trace:
    extracted = extract_text(html, defences)
    body = clean_body(extracted)
    sentences = split_sentences(body, title)
    stages = {
        "extracted": payload_present(extracted),
        "cleaned": payload_present(body),
        "candidate": any(payload_present(s) for s in sentences),
    }
    return Trace(extracted, body, sentences, stages)
