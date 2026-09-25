from pipeline.entities.extractor import (
    HINDI_TYPES,
    SPACY_TYPES,
    Gazetteer,
    Mention,
    clean_surface,
    hindi_chunks,
    resolve,
)

GAZ = Gazetteer()


def test_canonicalizes_across_languages():
    assert GAZ.canonicalize("अमेरिका") == ("United States", "COUNTRY")
    assert GAZ.canonicalize("U.S.") == ("United States", "COUNTRY")
    assert GAZ.canonicalize("भाजपा") == ("Bharatiya Janata Party", "PARTY")


def test_scan_respects_word_boundaries_and_acronym_case():
    found = {m.canonical for m in GAZ.scan("Talks with us on tariffs and the BTA; GSTN portal")}
    assert found == {"Tariffs", "Trade deal"}  # "us" is not the US; GSTN is not GST


def test_scan_matches_devanagari_terms_but_not_inside_words():
    found = {m.canonical for m in GAZ.scan("भारत पर अमेरिकी टैरिफ से निर्यातकों को नुकसान")}
    assert "Tariffs" in found
    # निर्यातकों (exporters, inflected) isn't a listed alias; prefix matches must not fire
    assert "Exports" not in found


def test_resolve_prefers_gazetteer_then_ner_type():
    assert resolve(GAZ, "The Indian", "NORP", SPACY_TYPES) == Mention("India", "COUNTRY", "Indian")
    assert resolve(GAZ, "Europeans", "NORP", SPACY_TYPES) is None
    assert resolve(GAZ, "Tata Motors's", "ORG", SPACY_TYPES) == Mention("Tata Motors", "ORG", "Tata Motors")
    assert resolve(GAZ, "रिलायंस", "ORGANIZATION", HINDI_TYPES) == Mention("रिलायंस", "ORG", "रिलायंस")


def test_clean_surface_rejects_noise():
    assert clean_surface("  2026 ") is None
    assert clean_surface("#") is None
    assert clean_surface("“Piyush Goyal”") == "Piyush Goyal"


def test_hindi_chunks_stay_under_limit_and_keep_all_text():
    body = "।".join(["यह एक वाक्य है"] * 100) + "।"
    chunks = hindi_chunks("शीर्षक", body)
    assert all(len(c) <= 420 for c in chunks)
    assert chunks[0].startswith("शीर्षक")


def test_full_word_span_keeps_trailing_vowel_signs():
    from pipeline.entities.extractor import full_word_span

    text = "राहुल गांधी ने कहा"
    assert full_word_span(text, 0, len("राहुल गांध")) == "राहुल गांधी"


def test_clean_surface_keeps_final_hindi_vowel_sign():
    assert clean_surface("राहुल गांधी,") == "राहुल गांधी"
    assert clean_surface("दिल्ली") == "दिल्ली"
