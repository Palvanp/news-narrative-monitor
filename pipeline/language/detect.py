"""Language identification with lingua, cross-checked against the feed's declared language.

The detector includes other Indic languages as "confusers": a Marathi article
in Devanagari must not be forced into Hindi just because Hindi is the only
Devanagari option.
"""

from functools import lru_cache

from lingua import Language, LanguageDetectorBuilder

CANDIDATES = [
    Language.ENGLISH,
    Language.HINDI,
    Language.MARATHI,
    Language.BENGALI,
    Language.URDU,
    Language.GUJARATI,
    Language.PUNJABI,
    Language.TAMIL,
    Language.TELUGU,
]

# Sources declare language as a code ("hi") or a name ("Hindi").
HINT_TO_CODE = {"english": "en", "hindi": "hi", "marathi": "mr", "bengali": "bn", "urdu": "ur"}

# Below this much text, lingua is unreliable and the source's declared language wins on disagreement.
MIN_CHARS_FOR_OVERRIDE = 200


@lru_cache(maxsize=1)
def _detector():
    return LanguageDetectorBuilder.from_languages(*CANDIDATES).with_preloaded_language_models().build()


def _code(language: Language) -> str:
    return language.iso_code_639_1.name.lower()


def detect(text: str) -> str | None:
    if not text or not text.strip():
        return None
    lang = _detector().detect_language_of(text)
    return _code(lang) if lang else None


def resolve_language(title: str, body: str | None, hint: str | None) -> str | None:
    hint = (hint or "").lower()
    hint_code = hint if hint in HINT_TO_CODE.values() else HINT_TO_CODE.get(hint)
    text = f"{title}\n{body[:2000]}" if body else title
    detected = detect(text)
    if detected is None:
        return hint_code
    if hint_code is None or detected == hint_code:
        return detected
    return detected if len(text) >= MIN_CHARS_FOR_OVERRIDE else hint_code

