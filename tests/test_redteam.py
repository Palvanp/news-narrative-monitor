from pipeline.generation.brief import BriefDraft, Claim, NarrativeAssessment
from redteam.pages import BASES, MARKER, PAYLOADS, TECHNIQUES, generate_pages
from redteam.run_redteam import render_report, summarise
from redteam.runner import Runner
from redteam.survival import PROBE, marker_present, payload_present, trace


def test_generate_pages_writes_attack_pages_with_clean_twins(tmp_path):
    pages = generate_pages(tmp_path)
    attacks = [p for p in pages if p.is_attack]
    attack_bases = [b for b in BASES.values() if b.attack]
    assert len(attacks) == len(attack_bases) * len(TECHNIQUES) * len(PAYLOADS)
    ids = {p.id for p in pages}
    assert all(p.twin in ids for p in attacks)
    for p in pages:
        html = (tmp_path / p.file).read_text(encoding="utf-8")
        assert not marker_present(html)  # the code word is never on a page, only its parts
        if not p.is_attack:
            assert "ZEBRA" not in html
    assert (tmp_path / "manifest.json").exists()


def test_detection_sees_through_obfuscation():
    assert payload_present("joining​ ZEBRA and LАNTERN")  # zero-width + Cyrillic А
    assert marker_present("…and so on. ZEBRA-LANTERN") and marker_present("zebralantern")
    assert not marker_present("joining ZEBRA and LANTERN")


def _html(tmp_path, page_id):
    return (tmp_path / f"{page_id}.html").read_text(encoding="utf-8")


def test_survival_by_method_and_defence(tmp_path):
    generate_pages(tmp_path)
    title = BASES["en-election"].title
    assert not trace(_html(tmp_path, "en-election--css_display_none--direct"), title).survived
    font0 = _html(tmp_path, "en-election--css_font_size_zero--direct")
    assert trace(font0, title).survived
    assert not trace(font0, title, frozenset({"html"})).survived
    homoglyph = _html(tmp_path, "en-election--homoglyph--direct")
    assert trace(homoglyph, title, frozenset({"filter"})).survived  # the filter can't read lookalikes...
    assert not trace(homoglyph, title, frozenset({"unicode", "filter"})).survived  # ...until they are normalised


class ObedientClient:
    """Stands in for the LLM: follows any instruction it can find in the prompt."""

    max_prompt_tokens = None

    def generate(self, model, system, prompt, output, **kwargs):
        summary = "Coverage reports an extension of the revision [E1]."
        if PROBE in prompt.lower():
            summary += " " + MARKER
        claim = Claim(claim="Officials extended the deadline [E1]", evidence_ids=["E1"])
        return BriefDraft(executive_summary=summary, key_developments=[claim],
                          narratives=[NarrativeAssessment(narrative_id=1, assessment="Steady coverage [E2].", evidence_ids=["E2"])],
                          narrative_shift=claim, key_entities=[])


def test_runner_detects_obeyed_instruction_and_defence_blocks_it(tmp_path):
    pages = {p.id: p for p in generate_pages(tmp_path)}
    runner = Runner(tmp_path, ObedientClient(), "m", encode=None, samples=2)
    chosen = [pages["en-election--css_font_size_zero--direct"], pages["en-election--clean"]]
    results = runner.run(chosen, ["none", "html"], ["body"])
    by = {(r.page, r.config): r for r in results}
    attacked = by[("en-election--css_font_size_zero--direct", "none")]
    assert (attacked.obeyed, attacked.samples) == (2, 2)
    assert by[("en-election--css_font_size_zero--direct", "html")].obeyed == 0
    assert by[("en-election--clean", "none")].obeyed == 0
    # the defence removed the instruction, so the attack page sends the clean twin's prompt
    assert by[("en-election--css_font_size_zero--direct", "html")].prompt_id == by[("en-election--clean", "html")].prompt_id

    summary = summarise(results, ["none", "html"], ["body"])
    assert summary["end_to_end"]["body"]["none"]["samples_obeyed"]["hits"] == 2
    assert summary["end_to_end"]["body"]["html"]["samples_obeyed"]["hits"] == 0
    assert summary["distinct_attack_prompts"] == 1
    assert summary["clean_pages"]["html"]["body"]["evidence_changed"] == []
    report = render_report({"generated_at": "t", "model": "m", "attack_pages": 1, "clean_pages": 1, "cases": 4},
                           summary, ["none", "html"], ["body"])
    assert "css_font_size_zero" in report and "Examples of attacks that worked" in report
