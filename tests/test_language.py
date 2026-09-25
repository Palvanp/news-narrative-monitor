from pipeline.language.detect import resolve_language


def test_detects_english_and_hindi():
    assert resolve_language("India and the United States resume trade negotiations in Washington", None, None) == "en"
    assert resolve_language("भारत और अमेरिका के बीच व्यापार वार्ता फिर से शुरू हुई", None, None) == "hi"


def test_gdelt_label_wins_on_short_disagreeing_text():
    assert resolve_language("GST", None, "Hindi") == "hi"
