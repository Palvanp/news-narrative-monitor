"""Defences against prompt injection hidden in fetched article pages.

Nazar fetches arbitrary publisher pages and passes text from them to an LLM, so a
page can carry instructions aimed at the model (indirect prompt injection). These
filters are optional and switched on with INJECTION_DEFENCES (see backend/config.py):

- html:    drop page content a reader can't see before text extraction: elements
           hidden with CSS (inline styles and simple <style> rules), HTML comments,
           image alt/title text.
- unicode: NFKC, remove zero-width and other invisible format characters, and map
           Cyrillic/Greek lookalike letters inside Latin words back to Latin.
- filter:  drop sentences addressed to an AI system ("ignore previous instructions",
           "note to AI assistants: ..."). Most useful after `unicode`, which undoes
           the obfuscation that would otherwise slip past its patterns.

redteam/ measures what each one blocks and what it costs on clean pages.
"""

import re
import unicodedata
from collections.abc import Iterable

from selectolax.parser import HTMLParser

DEFENCES = ("html", "unicode", "filter")


def parse_defences(spec: str | Iterable[str] | None) -> frozenset[str]:
    """"html,unicode" / ["html"] / "all" / "" -> a validated set of defence names."""
    if not spec:
        return frozenset()
    names = [s.strip().lower() for s in (spec.split(",") if isinstance(spec, str) else spec)]
    names = [n for n in names if n and n != "none"]
    if "all" in names:
        return frozenset(DEFENCES)
    unknown = set(names) - set(DEFENCES)
    if unknown:
        raise ValueError(f"unknown injection defence(s) {sorted(unknown)}; choose from {DEFENCES} or 'all'")
    return frozenset(names)


# --- html ---------------------------------------------------------------------

_HIDDEN_DECL = re.compile(
    r"display\s*:\s*none"
    r"|visibility\s*:\s*hidden"
    r"|font-size\s*:\s*0+(?:\.0+)?\s*(?:px|pt|em|rem|%)?\s*(?:;|!|$)"
    r"|opacity\s*:\s*0+(?:\.0+)?\s*(?:;|!|$)"
    r"|(?:left|top|text-indent)\s*:\s*-\d{3,}"
    # white text with no background of its own: invisible on a white page
    r"|(?<![-\w])color\s*:\s*(?:#fff(?:fff)?|white|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))\s*(?:;|!|$)",
    re.IGNORECASE,
)
# Common "screen reader only" utility classes; they hide text from sighted readers.
_HIDDEN_CLASSES = {"sr-only", "visually-hidden", "screen-reader-text", "hidden"}
_CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_SIMPLE_SELECTOR = re.compile(r"^[\w-]*([.#][\w-]+)$")


def _hidden_selectors(tree: HTMLParser) -> set[str]:
    """`.cls` / `#id` selectors that <style> blocks hide. Linked stylesheets aren't fetched."""
    selectors = {f".{c}" for c in _HIDDEN_CLASSES}
    for style in tree.css("style"):
        for sel_group, decls in _CSS_RULE.findall(style.text() or ""):
            if not _HIDDEN_DECL.search(decls):
                continue
            for sel in sel_group.split(","):
                if m := _SIMPLE_SELECTOR.match(sel.strip()):
                    selectors.add(m.group(1))
    return selectors


def _is_hidden(node) -> bool:
    attrs = node.attributes
    if "hidden" in attrs or (attrs.get("aria-hidden") or "").lower() == "true":
        return True
    style = attrs.get("style") or ""
    return bool(style) and bool(_HIDDEN_DECL.search(style)) and "background" not in style.lower()


def strip_hidden_html(html: str) -> str:
    """Remove what a reader can't see: CSS-hidden elements, comments, alt/title text."""
    tree = HTMLParser(html)
    doomed = []
    for node in tree.root.traverse(include_text=False) if tree.root else ():
        if node.tag == "_comment" or (node.tag not in ("html", "head", "body") and _is_hidden(node)):
            doomed.append(node)
    for sel in _hidden_selectors(tree):
        doomed += tree.css(sel)
    for node in doomed:
        try:
            node.decompose()
        except Exception:  # already removed with a hidden ancestor
            pass
    for node in tree.css("[alt], [title]"):
        for attr in ("alt", "title"):
            if attr in node.attributes:
                del node.attrs[attr]
    return tree.html or ""


# --- unicode ------------------------------------------------------------------

_ZWNJ, _ZWJ = "\u200c", "\u200d"

# Lookalike letters (Unicode "confusables") commonly swapped into Latin words.
_CONFUSABLES = str.maketrans({
    # Cyrillic
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "ѕ": "s", "і": "i", "ј": "j",
    "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w", "ӏ": "l",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
    "Х": "X", "У": "Y", "Ѕ": "S", "І": "I", "Ј": "J",
    # Greek
    "α": "a", "ο": "o", "ρ": "p", "ν": "v", "ι": "i", "κ": "k", "τ": "t",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O",
    "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})
_CONFUSABLE_CHARS = {chr(c) for c in _CONFUSABLES}
_WORD = re.compile(r"\w+")


def _is_devanagari(ch: str) -> bool:
    return "\u0900" <= ch <= "\u097f"


def _strip_format_chars(text: str) -> str:
    """Remove invisible format characters (zero-width, bidi controls, tag characters),
    keeping ZWJ/ZWNJ between Devanagari characters, where they change how a word renders."""
    out = []
    for i, ch in enumerate(text):
        if unicodedata.category(ch) != "Cf":
            out.append(ch)
        elif ch in (_ZWJ, _ZWNJ) and 0 < i < len(text) - 1 and _is_devanagari(text[i - 1]) and _is_devanagari(text[i + 1]):
            out.append(ch)
    return "".join(out)


def _unconfuse(match: re.Match) -> str:
    word = match.group(0)
    if not any(ch in _CONFUSABLE_CHARS for ch in word):
        return word
    # Only rewrite words made entirely of Latin and lookalike letters, so real
    # Cyrillic or Greek words (with letters that have no Latin twin) are untouched.
    if all(ch.isascii() or ch in _CONFUSABLE_CHARS or not ch.isalpha() for ch in word):
        return word.translate(_CONFUSABLES)
    return word


def normalise_unicode(text: str) -> str:
    text = _strip_format_chars(unicodedata.normalize("NFKC", text))
    return _WORD.sub(_unconfuse, text)


# --- filter -------------------------------------------------------------------

_AI = r"(?:AI|A\.I\.|LLMs?|language models?|chat ?bots?|assistants?|GPT|Claude|Gemini|summari[sz]ers?|models?)"
_INSTRUCTION = re.compile(
    r"\b(?:ignore|disregard|forget|override)\b.{0,40}\b(?:instructions?|prompts?|rules|directions)\b"
    r"|\b(?:system prompt|new instructions|developer mode|jailbreak)\b"
    rf"|\b(?:note|message|instructions?|attention)\s+(?:to|for)\s+(?:any|all)?\s*{_AI}"
    rf"|\b(?:if you are|as) an? {_AI}\b"
    rf"|\b{_AI}\b[^.!?]{{0,60}}\b(?:summari[sz]ing|reading|processing)\s+this\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?।])\s+")


def drop_instructions(text: str) -> str:
    """Drop sentences that address an AI system, paragraph by paragraph."""
    paragraphs = []
    for para in text.split("\n"):
        kept = [s for s in _SENTENCE.split(para) if not _INSTRUCTION.search(s)]
        if kept:
            paragraphs.append(" ".join(kept))
    return "\n".join(paragraphs)


def apply_text_defences(text: str, defences: frozenset[str]) -> str:
    """The defences that work on extracted text, in the order they must run."""
    if "unicode" in defences:
        text = normalise_unicode(text)
    if "filter" in defences:
        text = drop_instructions(text)
    return text
