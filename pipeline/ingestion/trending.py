"""Suggest topics that are in the news right now, in both languages.

A run can only find narratives in what the feeds currently hold (roughly the
last 1-3 days), so a topic typed from memory often matches only a handful of
articles. This reads the same feeds, proposes candidate topics from names that
recur in the headlines, and scores every candidate with the real TopicMatcher,
so a suggestion's article counts are what a run would actually collect.

Candidates are names (multi-word proper nouns and acronyms in English
headlines, plus gazetteer entities found in either language) and pairs of names
that appear together. A candidate is kept when it has enough coverage in both
English and Hindi and isn't so broad that it covers a large share of all news
("BJP", "PM Modi"); candidates that would collect mostly the same articles are
merged, keeping the larger.
"""

import asyncio
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from itertools import combinations

from pipeline.ingestion.rss import _fetch_all, load_feeds, parse_feed
from pipeline.ingestion.topic import _gazetteer, build_matcher

WINDOW_HOURS = 72
MIN_PER_LANGUAGE = {"en": 8, "hi": 5}
MIN_TOTAL = 25  # below this, runs rarely find a storyline tight enough to be a narrative
MAX_SHARE = 0.05  # a topic matching more than this share of all headlines is too broad
MAX_OVERLAP = 0.3  # share of the smaller topic's articles that the larger already covers
MIN_NAME_COUNT = 4
MIN_PAIR_COUNT = 3
MAX_CANDIDATES = 120

_PROPER = re.compile(r"\b[A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+)+|\b[A-Z]{2,5}\b")
# Headline furniture and words too generic to be (part of) a topic.
NOISE = {
    "live", "updates", "update", "news", "highlights", "watch", "video", "photos", "today", "breaking",
    "exclusive", "explained", "opinion", "editorial", "morning", "brief", "top", "the", "india", "indian",
    "pm", "says", "new", "big", "key", "how", "why", "what", "who", "when", "after", "over", "day", "week",
}
# Names in so much of the news that alone they're a beat, not a storyline. They
# still take part in pairs ("Rahul Gandhi" + "Bharatiya Janata Party").
BROAD_TYPES = {"COUNTRY", "LOC"}
BROAD_NAMES = {"Bharatiya Janata Party", "Indian National Congress", "Narendra Modi", "AI"}


@dataclass
class Suggestion:
    topic: str
    en: int
    hi: int
    headlines: list[str] = field(default_factory=list)
    matched: set[int] = field(default_factory=set, repr=False)

    @property
    def total(self) -> int:
        return self.en + self.hi


def _clean_name(name: str) -> str | None:
    words = [w for w in name.replace("’", "'").split() if w.lower().strip("'") not in NOISE]
    name = " ".join(words).removesuffix("'s")
    return name if len(name) >= 2 else None


def _canonical(name: str) -> str:
    known = _gazetteer().canonicalize(name)
    return known[0] if known else name


def is_broad(name: str) -> bool:
    known = _gazetteer().canonicalize(name)
    return name in BROAD_NAMES or bool(known and (known[1] in BROAD_TYPES or known[0] in BROAD_NAMES))


def headline_names(title: str, language: str) -> set[str]:
    names = {m.canonical for m in _gazetteer().scan(title) if m.type != "POLICY"}
    if language == "en":
        names |= {_canonical(n) for m in _PROPER.findall(title) if (n := _clean_name(m))}
    return names


def candidate_topics(items: list[tuple[str, str]]) -> list[str]:
    """items: (language, headline). Frequent names, then frequent pairs of names."""
    names_per_item = [headline_names(title, lang) for lang, title in items]
    singles = Counter(n for names in names_per_item for n in names)
    frequent = {n for n, c in singles.items() if c >= MIN_NAME_COUNT}
    pairs = Counter(
        pair for names in names_per_item for pair in combinations(sorted(names & frequent), 2)
    )
    out = [n for n, _ in singles.most_common() if n in frequent and not is_broad(n)][: MAX_CANDIDATES // 2]
    out += [f"{a} {b}" for (a, b), c in pairs.most_common() if c >= MIN_PAIR_COUNT][: MAX_CANDIDATES // 2]
    return out


def score_topics(items: list[tuple[str, str, str]], limit: int = 6) -> list[Suggestion]:
    """items: (language, headline, summary) from the feeds within the window."""
    if not items:
        return []
    scored = []
    seen_sets: set[frozenset] = set()
    for topic in candidate_topics([(lang, title) for lang, title, _ in items]):
        matcher = build_matcher(topic)
        matched = {i for i, (_, title, summary) in enumerate(items) if matcher.matches(f"{title} {summary}")}
        langs = Counter(items[i][0] for i in matched)
        s = Suggestion(topic, langs["en"], langs["hi"], matched=matched)
        key = frozenset(matched)
        if (
            key in seen_sets
            or s.total < MIN_TOTAL
            or s.total > MAX_SHARE * len(items)
            or any(langs[lang] < n for lang, n in MIN_PER_LANGUAGE.items())
        ):
            continue
        seen_sets.add(key)
        scored.append(s)
    # Prefer topics with real coverage in both languages, then size.
    scored.sort(key=lambda s: (min(s.en, s.hi * 2), s.total), reverse=True)
    picked: list[Suggestion] = []
    for s in scored:
        if all(len(s.matched & p.matched) <= MAX_OVERLAP * min(len(s.matched), len(p.matched)) for p in picked):
            # sample headlines: ones whose title alone matches first (a summary match reads as off-topic)
            matcher = build_matcher(s.topic)
            ranked = sorted(s.matched, key=lambda i: (not matcher.matches(items[i][1]), i))
            s.headlines = [items[i][1] for i in ranked[:3]]
            picked.append(s)
        if len(picked) == limit:
            break
    return picked


def fetch_headlines(hours: int = WINDOW_HOURS) -> list[tuple[str, str, str]]:
    feeds = load_feeds(["en", "hi"])
    contents = asyncio.run(_fetch_all(feeds, None, None))
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    items, seen = [], set()
    for feed, content in zip(feeds, contents):
        if content is None:
            continue
        for item in parse_feed(content, feed):
            if start <= item.seen_at <= end and item.url not in seen:
                seen.add(item.url)
                items.append((feed.language, item.title, item.summary or ""))
    return items


def trending_topics(limit: int = 6) -> list[Suggestion]:
    return score_topics(fetch_headlines(), limit)
