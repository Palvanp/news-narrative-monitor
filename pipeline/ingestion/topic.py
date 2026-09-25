"""Decide whether a headline is about the monitored topic, in English or Hindi.

The topic is split into concepts ("India-US trade negotiations" -> India, United
States, trade, negotiation). Each concept expands to its forms in both languages
(from the entity gazetteer and a small lexicon), so "US" also matches अमेरिका and
"trade" also matches व्यापार. A headline matches when it mentions at least two
concepts (a named person counts as two). This is deliberately loose; the embedding relevance score later
separates close matches from on-topic coverage.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from pipeline.entities.extractor import Gazetteer, _case_sensitive

LEXICON_PATH = Path(__file__).with_name("lexicon.yaml")
STOPWORDS = {"the", "and", "for", "with", "from", "into", "over", "about", "between", "amid", "of", "on", "in", "a", "an", "to", "at", "vs"}
# In Indian outlets "India" appears in nearly every story, so it only counts
# towards a match when the topic has fewer than two other concepts.
UBIQUITOUS = {"India"}
MIN_CONCEPTS = 2

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_WORD = "[\\wऀ-ॿ]"
_SUFFIXES = ("ations", "ation", "ions", "ing", "ers", "ed", "es", "s")


@dataclass
class Concept:
    name: str
    terms: list[str]
    patterns: list[re.Pattern]
    # A named person is specific enough to count as two concepts on its own:
    # "Rahul Gandhi attacks CEC Gyanesh Kumar" is on-topic for a Gyanesh Kumar monitor.
    weight: int = 1


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def term_pattern(term: str) -> re.Pattern:
    if _DEVANAGARI.search(term):
        # Hindi inflects by suffix (व्यापार -> व्यापारिक); allow suffixes on longer words only.
        right = "" if len(term) >= 4 else f"(?!{_WORD})"
        return re.compile(f"(?<!{_WORD}){re.escape(term)}{right}")
    if _case_sensitive(term):
        return re.compile(rf"(?<![\w.]){re.escape(term)}(?![\w])")
    words = term.lower().split()
    if len(words) > 1:
        return re.compile(r"\b" + r"\s+".join(map(re.escape, words)) + r"\b", re.IGNORECASE)
    word = words[0]
    stem = _stem(word)
    if stem == word or len(stem) <= 4:
        # base form: allow plain inflections only, so "trade" doesn't match "traders"
        return re.compile(rf"\b{re.escape(word)}(?:s|es|d|ed)?\b", re.IGNORECASE)
    # the word carried a suffix (negotiations -> negotiat): match the family
    return re.compile(rf"\b{re.escape(stem)}\w*", re.IGNORECASE)


@lru_cache(maxsize=1)
def _lexicon() -> dict[str, list[str]]:
    return {k: [str(t) for t in v] for k, v in yaml.safe_load(LEXICON_PATH.read_text(encoding="utf-8")).items()}


@lru_cache(maxsize=1)
def _gazetteer() -> Gazetteer:
    return Gazetteer()


def _concept_for(token: str) -> tuple[str, list[str]] | None:
    gaz = _gazetteer()
    known = gaz.canonicalize(token)
    if known:
        return known[0], gaz.members[known[0]]
    stem = _stem(token.lower())
    for name, forms in _lexicon().items():
        if any(_stem(f.lower()) == stem or f == token for f in forms):
            return name, forms
    return None


class TopicMatcher:
    def __init__(self, concepts: list[Concept]):
        self.concepts = concepts
        others = [c for c in concepts if c.name not in UBIQUITOUS]
        self.counted = others if len(others) >= MIN_CONCEPTS else concepts
        self.required = min(MIN_CONCEPTS, len(self.counted))

    def matched_concepts(self, text: str) -> list[str]:
        return [c.name for c in self.counted if any(p.search(text) for p in c.patterns)]

    def matched_terms(self, text: str) -> dict[str, str]:
        """For debugging: concept -> the first text span that matched it."""
        out = {}
        for c in self.counted:
            for p in c.patterns:
                if m := p.search(text):
                    out[c.name] = m.group(0)
                    break
        return out

    def matches(self, text: str) -> bool:
        score = sum(c.weight for c in self.counted if any(p.search(text) for p in c.patterns))
        return self.required > 0 and score >= self.required


def _next_concept(tokens: list[str], i: int) -> tuple[int, tuple[str, list[str]] | None]:
    """Longest multi-word name first ("Election Commission", "Gyanesh Kumar"), then single words."""
    for n in (4, 3, 2):
        if i + n <= len(tokens):
            known = _gazetteer().canonicalize(" ".join(tokens[i : i + n]))
            if known:
                return n, (known[0], _gazetteer().members[known[0]])
    token = tokens[i]
    if token.lower() in STOPWORDS:
        return 1, None
    found = _concept_for(token)
    if found:
        return 1, found
    return 1, (token.lower(), [token]) if len(token) >= 3 else None


def build_matcher(topic: str, native_keywords: str | None = None) -> TopicMatcher:
    tokens = [t for t in re.split(r"[\s\-–—/,]+", f"{topic} {native_keywords or ''}") if t]
    concepts: dict[str, list[str]] = {}
    i = 0
    while i < len(tokens):
        step, found = _next_concept(tokens, i)
        i += step
        if found is None:
            continue
        name, terms = found
        concepts.setdefault(name, [])
        for term in terms:
            if term not in concepts[name]:
                concepts[name].append(term)
    return TopicMatcher([Concept(n, ts, [term_pattern(t) for t in ts], _weight(n)) for n, ts in concepts.items()])


def _weight(name: str) -> int:
    known = _gazetteer().canonicalize(name)
    return 2 if known and known[1] == "PERSON" else 1
