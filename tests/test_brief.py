from dataclasses import replace

from pipeline.llm import estimate_tokens

from pipeline.generation.brief import (
    BriefDraft,
    Claim,
    Evidence,
    NarrativeAssessment,
    NarrativeContext,
    SYSTEM,
    build_prompt,
    fit_to_budget,
    generate,
    validate,
)


def ev(i, narrative=1):
    return Evidence(f"E{i}", article_id=i, narrative_id=narrative, title=f"Headline {i}", source="a.in", language="en", published_at="2026-09-23T10:00:00+00:00", url=f"https://a.in/{i}", excerpt=None)


EVIDENCE = {e.id: e for e in [ev(1), ev(2), ev(3, narrative=2)]}
STATS = {"volume": 10, "growth_pct": 50.0, "is_new": False, "sentiment": {"negative": 0.6}, "languages": {"en": 0.7, "hi": 0.3}, "unique_sources": 4, "top_entities": [{"name": "India"}]}
NARRATIVES = [
    NarrativeContext(1, "Tariff concerns", None, STATS, [EVIDENCE["E1"], EVIDENCE["E2"]]),
    NarrativeContext(2, "Talks progress", None, STATS, [EVIDENCE["E3"]]),
]


def draft(**overrides):
    base = dict(
        executive_summary="Coverage focuses on tariffs [E1] and a fake source [E99].",
        key_developments=[
            Claim(claim="Exporters worry about tariffs [E2]", evidence_ids=[]),
            Claim(claim="An uncited claim", evidence_ids=["E42"]),
        ],
        narratives=[
            NarrativeAssessment(narrative_id=1, assessment="Concern is rising.", evidence_ids=["E1", "E1", "[E2]"]),
            NarrativeAssessment(narrative_id=7, assessment="Unknown narrative.", evidence_ids=["E1"]),
        ],
        narrative_shift=Claim(claim="Tone turned negative.", evidence_ids=["E3"]),
        key_entities=["India"],
    )
    base.update(overrides)
    return BriefDraft(**base)


def test_validate_strips_fake_citations_and_flags_unsupported_claims():
    out = validate(draft(), EVIDENCE, {1, 2})
    assert "[E99]" not in out["executive_summary"] and "[E1]" in out["executive_summary"]
    assert out["executive_summary_evidence"] == ["E1"]
    assert out["key_developments"] == [{"claim": "Exporters worry about tariffs [E2]", "evidence_ids": ["E2"]}]
    assert out["unsupported_claims"] == ["An uncited claim"]
    assert out["narratives"] == [{"narrative_id": 1, "assessment": "Concern is rising.", "evidence_ids": ["E1", "E2"]}]
    assert out["narrative_shift"]["evidence_ids"] == ["E3"]
    # 2 developments + 2 assessments + 1 shift = 5 claims; unknown narrative 7 counts as unsupported-by-design
    assert out["metrics"]["claims"] == 5 and out["metrics"]["supported_claims"] == 3


class FakeClient:
    max_prompt_tokens = None

    def generate(self, model, system, prompt, output, **kwargs):
        assert "[E1]" in prompt and "Narrative 2: Talks progress" in prompt
        return draft()


def test_generate_renders_markdown_with_metrics_and_evidence_links():
    result = generate(FakeClient(), "m", "India-US trade", "24h", NARRATIVES)
    md = result["markdown"]
    assert "## Observed metrics" in md and "| Tariff concerns | 10 | +50% (second half vs first half) | 60% | en 70%, hi 30% |" in md
    assert "[Headline 1](https://a.in/1)" in md
    assert "Unsupported statements" in md
    assert set(result["evidence"]) == {"E1", "E2", "E3"}


def test_fit_to_budget_keeps_everything_without_a_limit():
    assert fit_to_budget("t", "w", NARRATIVES, None) is NARRATIVES


def test_fit_to_budget_trims_excerpts_before_dropping_narratives():
    long = [replace(n, evidence=[replace(e, excerpt="word " * 200) for e in n.evidence]) for n in NARRATIVES]
    full = estimate_tokens(SYSTEM + build_prompt("t", "w", long))
    trimmed = fit_to_budget("t", "w", long, full - 200)
    assert [n.id for n in trimmed] == [1, 2]  # both narratives kept
    assert all(len(e.excerpt) < 1000 for n in trimmed for e in n.evidence)
    assert estimate_tokens(SYSTEM + build_prompt("t", "w", trimmed)) <= full - 200


def test_fit_to_budget_drops_smallest_narratives_last():
    trimmed = fit_to_budget("t", "w", NARRATIVES, estimate_tokens(SYSTEM + build_prompt("t", "w", NARRATIVES[:1])))
    assert [n.id for n in trimmed] == [1]

