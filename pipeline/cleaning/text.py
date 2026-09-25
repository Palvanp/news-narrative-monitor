import re
import unicodedata

from selectolax.parser import HTMLParser

# Zero-width space and BOM are noise. ZWJ/ZWNJ (U+200C/D) are kept: they matter in Devanagari.
_INVISIBLE = dict.fromkeys(map(ord, "​﻿­"), None)
_WS = re.compile(r"\s+")
_TAG = re.compile(r"<[a-zA-Z/!][^>]*>")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    if _TAG.search(value):
        value = HTMLParser(value).text(separator=" ")
    value = unicodedata.normalize("NFC", value).translate(_INVISIBLE)
    return _WS.sub(" ", value).strip()


def clean_body(value: str | None) -> str:
    """Like clean_text, but keeps paragraph breaks so sentences can be split later."""
    if not value:
        return ""
    if _TAG.search(value):
        value = HTMLParser(value).text(separator="\n")
    value = unicodedata.normalize("NFC", value).translate(_INVISIBLE)
    paragraphs = (_WS.sub(" ", p).strip() for p in value.split("\n"))
    return "\n".join(p for p in paragraphs if p)


def _is_letter(ch: str) -> bool:
    # Devanagari vowel signs and viramas are combining marks (M*), not alphabetic,
    # but they are as much a part of a Hindi word as letters are.
    return unicodedata.category(ch)[0] in "LM"


def is_malformed(text: str, min_letters: int = 15) -> bool:
    """Too short, mojibake-heavy, or mostly non-letters (spaces don't count against it)."""
    if not text:
        return True
    letters = sum(_is_letter(ch) for ch in text)
    if letters < min_letters:
        return True
    if text.count("�") / len(text) > 0.01:
        return True
    visible = sum(not ch.isspace() for ch in text)
    return letters / visible < 0.6
