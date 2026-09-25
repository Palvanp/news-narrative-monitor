"""Named-entity extraction for English (spaCy) and Hindi (IndicNER), plus a gazetteer.

NER finds people, organisations and places. The gazetteer does two things NER
can't: it maps surface forms in both languages onto one canonical entity
(अमेरिका / US / America -> United States), and it finds parties, government
bodies and policy terms by direct matching.
"""

import re
from collections import Counter
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import yaml

from pipeline import nlp_env

GAZETTEER_PATH = Path(__file__).with_name("gazetteer.yaml")

SPACY_TYPES = {"PERSON": "PERSON", "ORG": "ORG", "GPE": "LOC", "LOC": "LOC", "FAC": "LOC", "EVENT": "EVENT", "LAW": "POLICY"}
INDICNER_TYPES = {"PER": "PERSON", "ORG": "ORG", "LOC": "LOC"}
# NORP ("Indian", "American") only counts when the gazetteer maps it to a country.
GAZETTEER_ONLY = {"NORP"}

MIN_NER_SCORE = 0.6
HINDI_CHUNK_CHARS = 400
HINDI_BODY_CHARS = 2000
ENGLISH_BODY_CHARS = 3000

# Devanagari vowel signs aren't \w in Python's re, so word boundaries are explicit.
_WORD = "[\\wऀ-ॿ]"
# Danda (।) ends a sentence even without a following space; "." needs one (U.S., Rs.).
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=।)\s*")
_EDGE_PUNCT = re.compile(r"^[\W_]+|[\W_]+$")


@dataclass(frozen=True)
class Mention:
    canonical: str
    type: str
    surface: str


def _alias_key(alias: str) -> str:
    return " ".join(alias.casefold().replace("’", "'").split())


def _case_sensitive(alias: str) -> bool:
    # Short acronyms (US, BTA, GST) must not match ordinary words ("us").
    letters = [c for c in alias if c.isalpha()]
    return bool(letters) and len(alias) <= 5 and all(c.isupper() for c in letters)


class Gazetteer:
    def __init__(self, path: Path = GAZETTEER_PATH):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.aliases: dict[str, tuple[str, str]] = {}
        patterns: list[tuple[re.Pattern, str, str]] = []
        for canonical, spec in data.items():
            etype = spec["type"]
            for alias in spec["aliases"]:
                alias = str(alias)
                self.aliases[_alias_key(alias)] = (canonical, etype)
                if spec.get("match"):
                    flags = 0 if _case_sensitive(alias) else re.IGNORECASE
                    pattern = re.compile(rf"(?<!{_WORD}){re.escape(alias)}(?!{_WORD})", flags)
                    patterns.append((pattern, canonical, etype))
        self.patterns = patterns

    def canonicalize(self, surface: str) -> tuple[str, str] | None:
        return self.aliases.get(_alias_key(surface))

    def scan(self, text: str) -> list[Mention]:
        return [
            Mention(canonical, etype, m.group(0))
            for pattern, canonical, etype in self.patterns
            for m in pattern.finditer(text)
        ]


def clean_surface(surface: str) -> str | None:
    surface = " ".join(surface.split())
    surface = re.sub(r"^(the|The)\s+", "", surface)
    surface = re.sub(r"['’]s$", "", surface)
    surface = _EDGE_PUNCT.sub("", surface)
    if len(surface) < 2 or len(surface) > 60 or not any(c.isalpha() for c in surface):
        return None
    return surface


def resolve(gazetteer: Gazetteer, surface: str, ner_label: str, type_map: dict[str, str]) -> Mention | None:
    surface = clean_surface(surface)
    if surface is None:
        return None
    known = gazetteer.canonicalize(surface)
    if known:
        return Mention(known[0], known[1], surface)
    if ner_label in GAZETTEER_ONLY or ner_label not in type_map:
        return None
    return Mention(surface, type_map[ner_label], surface)


def hindi_chunks(title: str, body: str | None) -> list[str]:
    """Sentence-aligned chunks short enough for a 512-token encoder."""
    sentences = [title] + (_SENTENCE_END.split(body[:HINDI_BODY_CHARS].replace("\n", " ")) if body else [])
    pieces = []
    for sentence in sentences:
        pieces.extend(sentence[i : i + HINDI_CHUNK_CHARS] for i in range(0, len(sentence), HINDI_CHUNK_CHARS))
    chunks, current = [], ""
    for sentence in pieces:
        if current and len(current) + len(sentence) > HINDI_CHUNK_CHARS:
            chunks.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


class EntityExtractor:
    def __init__(self, hindi_model: str, device: str | None = None, gazetteer: Gazetteer | None = None):
        self.hindi_model = hindi_model
        self.device = device or nlp_env.resolve_device()
        self.gazetteer = gazetteer or Gazetteer()

    @cached_property
    def _spacy(self):
        import spacy

        return spacy.load("en_core_web_sm", disable=["parser", "lemmatizer", "tagger", "attribute_ruler"])

    @cached_property
    def _indic(self):
        from transformers import pipeline

        return pipeline(
            "token-classification",
            model=self.hindi_model,
            aggregation_strategy="simple",
            device=0 if self.device == "cuda" else -1,
        )

    def extract_many(self, items: list[tuple[str, str | None, str]]) -> list[Counter]:
        """items: (title, body, language). Returns a Counter of Mentions per item."""
        results: list[Counter] = [Counter() for _ in items]

        english = [i for i, (_, _, lang) in enumerate(items) if lang == "en"]
        texts = [f"{items[i][0]}\n{(items[i][1] or '')[:ENGLISH_BODY_CHARS]}" for i in english]
        for i, doc in zip(english, self._spacy.pipe(texts, batch_size=32)):
            for ent in doc.ents:
                mention = resolve(self.gazetteer, ent.text, ent.label_, SPACY_TYPES)
                if mention:
                    results[i][mention] += 1

        hindi = [i for i, (_, _, lang) in enumerate(items) if lang == "hi"]
        chunk_owner, chunks = [], []
        for i in hindi:
            for chunk in hindi_chunks(items[i][0], items[i][1]):
                chunk_owner.append(i)
                chunks.append(chunk)
        if chunks:
            for i, ents in zip(chunk_owner, self._indic(chunks, batch_size=16)):
                for ent in ents:
                    if ent["score"] < MIN_NER_SCORE:
                        continue
                    mention = resolve(self.gazetteer, ent["word"], ent["entity_group"], INDICNER_TYPES)
                    if mention:
                        results[i][mention] += 1

        # Gazetteer terms (parties, government bodies, policy) in either language.
        # Entities NER already found keep their NER counts; the scan only adds new ones.
        for i, (title, body, _) in enumerate(items):
            text = f"{title}\n{body or ''}"
            scanned = Counter(self.gazetteer.scan(text))
            found = {(m.canonical, m.type) for m in results[i]}
            for mention, count in scanned.items():
                if (mention.canonical, mention.type) not in found:
                    results[i][mention] += count
        return results

    def close(self) -> None:
        self.__dict__.pop("_indic", None)
        self.__dict__.pop("_spacy", None)
        nlp_env.release_gpu()
