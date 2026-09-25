from datetime import datetime, timezone

from pipeline.cleaning.dedup import dedup_urls, headline_duplicates, normalize_headline
from pipeline.cleaning.text import clean_body, clean_text, is_malformed
from pipeline.cleaning.urls import normalize_url
from pipeline.ingestion.types import RawArticle


def art(url, title, hour, body_status="failed"):
    return RawArticle(url=url, title=title, domain="x", seen_at=datetime(2026, 9, 23, hour, tzinfo=timezone.utc), body_status=body_status)


def test_normalize_url_strips_tracking_amp_and_www():
    a = normalize_url("https://www.Example.in/news/story/amp/?utm_source=tw&id=5#top")
    b = normalize_url("http://m.example.in/news/story?id=5&fbclid=abc")
    assert a == b == "example.in/news/story?id=5"


def test_clean_text_strips_html_and_keeps_devanagari_joiners():
    assert clean_text("<p>Trade\u200b  talks</p>\n<b>resume</b>") == "Trade talks resume"
    assert "\u200d" in clean_text("क्\u200dष")


def test_clean_body_keeps_paragraphs():
    assert clean_body("First  para.\n\n\nSecond para.") == "First para.\nSecond para."


def test_is_malformed():
    assert is_malformed("")
    assert is_malformed("12:30 | 45 | ##")
    assert not is_malformed("India and US resume trade negotiations")


def test_normalize_headline_drops_site_suffix_and_punctuation():
    assert normalize_headline("India, US trade talks enter final round - Example News") == "india us trade talks enter final round"
    assert normalize_headline("भारत-अमेरिका व्यापार वार्ता अंतिम दौर में | दैनिक") == "भारत अमेरिका व्यापार वार्ता अंतिम दौर में"


def test_dedup_urls_keeps_earliest():
    items = [art("https://a.in/x?utm_source=1", "t", 5), art("https://www.a.in/x", "t", 3), art("https://a.in/y", "t", 4)]
    unique, dropped = dedup_urls(items)
    assert dropped == 1
    assert {a.seen_at.hour for a in unique} == {3, 4}


def test_headline_duplicates_point_to_earliest_and_ignore_short_titles():
    items = [
        art("u1", "India US trade talks enter final round - Site A", 5),
        art("u2", "India, US trade talks enter final round | Site B", 2),
        art("u3", "Live updates", 1),
        art("u4", "Live updates", 2),
    ]
    assert headline_duplicates(items) == [1, None, None, None]


def test_near_duplicates_same_language_only_and_collapse_chains():
    import numpy as np

    from pipeline.cleaning.dedup import near_duplicates

    base = np.array([1.0, 0.0, 0.0])
    close = np.array([0.98, 0.2, 0.0])
    close /= np.linalg.norm(close)
    other = np.array([0.0, 1.0, 0.0])
    vectors = np.stack([base, close, base, other, base])
    langs = ["en", "en", "hi", "en", "en"]
    # item 1 near-dups item 0; item 2 is Hindi so stays; item 4 matches 0 (canonical), not 1
    assert near_duplicates(vectors, langs) == [None, 0, None, None, 0]


def test_hindi_headlines_are_not_malformed():
    assert not is_malformed("बंगाल में कांग्रेस का EC के खिलाफ प्रदर्शन, ज्ञानेश कुमार की गिरफ्तारी की मांग")
    assert not is_malformed("क्‍या है विशेष गहन पुनरीक्षण?")
