from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline.ingestion.gdelt import MAX_RECORDS, RawArticle, build_query, fetch_range, parse_response

FIXTURE = Path(__file__).parent / "fixtures" / "gdelt_artlist.json"


def test_build_query_splits_hyphens_and_drops_short_tokens():
    assert build_query("India-US trade negotiations", "hi") == "India trade negotiations sourcelang:hindi"


def test_build_query_passes_gdelt_syntax_through():
    assert build_query('"trade deal" (India OR US)', "en").startswith('"trade deal" (India OR US)')


def test_build_query_rejects_topics_without_usable_keywords():
    with pytest.raises(ValueError):
        build_query("US-EU", "en")


class FakeClient:
    """Pretends one article is published every `every_minutes`."""

    def __init__(self, every_minutes: int):
        self.every = timedelta(minutes=every_minutes)
        self.calls = []

    def fetch_window(self, query, start, end, query_language=None):
        self.calls.append((start, end))
        items, t = [], start
        while t < end and len(items) < MAX_RECORDS:
            items.append(RawArticle(url=f"https://x/{t.isoformat()}", title="t", domain="x", seen_at=t))
            t += self.every
        return items


END = datetime(2026, 9, 24, tzinfo=timezone.utc)


def test_fetch_range_uses_one_request_when_under_cap():
    client = FakeClient(every_minutes=30)  # 48 articles in 24h
    articles = fetch_range(client, "q", END - timedelta(hours=24), END)
    assert len(client.calls) == 1 and len(articles) == 48


def test_fetch_range_splits_until_under_cap_without_gaps_or_overlap():
    client = FakeClient(every_minutes=2)  # 720 articles in 24h
    articles = fetch_range(client, "q", END - timedelta(hours=24), END)
    assert len(articles) == 720
    assert len({a.url for a in articles}) == 720


def test_parse_response_reads_fixture_and_skips_untitled():
    articles = parse_response(FIXTURE.read_text(encoding="utf-8"), "en")
    assert [a.language_hint for a in articles] == ["English", "Hindi"]
    assert {a.origin for a in articles} == {"gdelt"}
    assert articles[0].seen_at == datetime(2026, 9, 23, 10, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize("text", ["", "{}", "  \n"])
def test_parse_response_handles_empty_results(text):
    assert parse_response(text) == []
