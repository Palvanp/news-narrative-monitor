from pipeline.ingestion.topic import build_matcher

M = build_matcher("India-US trade negotiations")


def test_concepts_expand_across_languages():
    names = [c.name for c in M.concepts]
    assert names == ["India", "United States", "trade", "negotiation"]
    us = next(c for c in M.concepts if c.name == "United States")
    assert "अमेरिका" in us.terms


def test_india_does_not_count_when_other_concepts_exist():
    assert not M.matches("India trade figures released")  # India + trade = only one counted concept
    assert M.matches("India, US trade talks enter final round")
    assert M.matches("Negotiators meet as tariff trade dispute deepens")  # trade + negotiation (stem)


def test_hindi_headlines_match():
    assert M.matches("भारत-अमेरिका व्यापार वार्ता अंतिम दौर में")
    assert M.matches("अमेरिकी टैरिफ के बीच व्यापारिक बातचीत तेज")
    assert not M.matches("भारत में मानसून की बारिश जारी")


def test_acronyms_are_case_sensitive():
    assert not M.matches("Let us trade places")  # "us" is not the US; only 'trade' matches
    assert M.matches("US trade team lands in Delhi")


def test_native_keywords_add_terms_and_single_concept_topics_need_one_match():
    m = build_matcher("farm protests", native_keywords="किसान आंदोलन")
    assert m.matches("किसान आंदोलन दिल्ली की सीमा पर")
    solo = build_matcher("Budget")
    assert solo.required == 1 and solo.matches("बजट 2027 पेश")


def test_base_words_do_not_match_derived_words_and_capitals_are_not_countries():
    assert not M.matches("Oil slips as traders hope for truce in talks")  # traders != trade
    assert not M.matches("वाशिंगटन में ट्रंप और जिनपिंग की वार्ता")  # Washington dateline != United States


def test_multi_word_names_become_one_bilingual_concept():
    m = build_matcher("Election Commission CEC Gyanesh Kumar SIR controversy")
    # "CEC Gyanesh Kumar" is itself an alias, so the longest match makes it one concept
    assert [c.name for c in m.concepts] == [
        "Election Commission of India", "Gyanesh Kumar", "Special Intensive Revision", "controversy",
    ]
    assert m.matches("Rahul Gandhi attacks CEC Gyanesh Kumar over voter list")
    assert m.matches("चुनाव आयोग ने एसआईआर पर दी सफाई")
    assert not m.matches("Akshay Kumar film breaks records")


def test_trending_keeps_bilingual_specific_topics_and_drops_broad_ones():
    from pipeline.ingestion.trending import score_topics

    story = [("en", f"Rahul Gandhi rally speech part {i}", "") for i in range(20)]
    story += [("hi", f"राहुल गांधी की रैली भाग {i}", "") for i in range(10)]
    english_only = [("en", f"Tiger Shroff film news {i}", "") for i in range(30)]
    broad = [("en", f"BJP statement on issue {i}", "") for i in range(60)]
    filler = [("en", f"weather report {i}", "") for i in range(800)]
    topics = {s.topic: s for s in score_topics(story + english_only + broad + filler)}
    assert set(topics) == {"Rahul Gandhi"}
    assert (topics["Rahul Gandhi"].en, topics["Rahul Gandhi"].hi) == (20, 10)
