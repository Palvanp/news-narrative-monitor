"""Evidence-backed intelligence brief.

The LLM writes only the assessment, citing evidence IDs like [E3]. Every number
in the brief comes from the observed metrics, which are rendered deterministically
and never generated. Validation drops citations to evidence that doesn't exist
and flags claims left without support.
"""

import re
from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field

from pipeline.llm import OllamaClient

MAX_NARRATIVES = 8
EVIDENCE_PER_NARRATIVE = 5
_CITATION = re.compile(r"\[(E\d+)\]")

SYSTEM = """You are an intelligence analyst writing a brief about news coverage of a political event.
Rules:
- Use only the narratives, metrics and evidence provided. No outside knowledge, no speculation, no predictions or recommendations.
- Every claim must cite supporting evidence IDs exactly as given, e.g. [E3]. Put the IDs in the claim's evidence_ids list too.
- Do not invent numbers; the metrics are shown to the reader separately. You may refer to growth or sentiment qualitatively.
- Distinguish what the coverage says from what is true: write "coverage reports..." rather than asserting events as fact.
- Write in English, concisely."""


@dataclass
class Evidence:
    id: str
    article_id: int
    narrative_id: int
    title: str
    source: str | None
    language: str | None
    published_at: str
    url: str
    excerpt: str | None


@dataclass
class NarrativeContext:
    id: int
    label: str
    summary: str | None
    stats: dict
    evidence: list[Evidence]


class Claim(BaseModel):
    claim: str = Field(max_length=500)
    evidence_ids: list[str]


class NarrativeAssessment(BaseModel):
    narrative_id: int
    assessment: str = Field(max_length=700)
    evidence_ids: list[str]


class BriefDraft(BaseModel):
    executive_summary: str = Field(max_length=1500)
    key_developments: list[Claim] = Field(max_length=6)
    narratives: list[NarrativeAssessment]
    narrative_shift: Claim
    key_entities: list[str] = Field(max_length=10)


def _fmt_growth(stats: dict) -> str:
    if stats.get("is_new"):
        return "new in the second half of the window"
    if stats.get("growth_pct") is None:
        return "n/a"
    return f"{stats['growth_pct']:+.0f}% (second half vs first half)"


def build_prompt(topic: str, window: str, narratives: list[NarrativeContext]) -> str:
    parts = [f"Monitored event: {topic}", f"Monitoring window: {window}", ""]
    for n in narratives:
        s = n.stats
        entities = ", ".join(e["name"] for e in s.get("top_entities", [])[:6])
        parts += [
            f"## Narrative {n.id}: {n.label}",
            f"Summary: {n.summary or 'n/a'}",
            f"Observed: {s.get('volume')} articles; growth {_fmt_growth(s)}; sentiment {s.get('sentiment')}; "
            f"languages {s.get('languages')}; {s.get('unique_sources')} sources",
            f"Entities: {entities or 'n/a'}",
            "Evidence:",
        ]
        for e in n.evidence:
            excerpt = f' "{e.excerpt}"' if e.excerpt else ""
            parts.append(f"[{e.id}] ({e.language}, {e.source}, {e.published_at[:16]}) {e.title}.{excerpt}")
        parts.append("")
    parts.append(
        "Write the brief: an executive summary (3-5 sentences, with citations), up to 5 key developments, "
        "one assessment per narrative (use the narrative numbers above), the most notable shift in coverage "
        "during the window, and the key entities."
    )
    return "\n".join(parts)


def validate(draft: BriefDraft, evidence: dict[str, Evidence], narrative_ids: set[int]) -> dict:
    """Keep only citations to real evidence; claims left with no citation are
    moved to `unsupported` rather than shown as findings."""
    unsupported: list[str] = []

    def clean_ids(ids: list[str]) -> list[str]:
        seen = []
        for eid in ids:
            eid = eid.strip().strip("[]")
            if eid in evidence and eid not in seen:
                seen.append(eid)
        return seen

    def clean_text(text: str) -> tuple[str, list[str]]:
        cited = [m for m in _CITATION.findall(text) if m in evidence]
        text = _CITATION.sub(lambda m: m.group(0) if m.group(1) in evidence else "", text)
        return " ".join(text.split()), cited

    def claim(c: Claim) -> dict | None:
        text, inline = clean_text(c.claim)
        ids = clean_ids(c.evidence_ids + inline)
        if not ids:
            unsupported.append(text)
            return None
        return {"claim": text, "evidence_ids": ids}

    summary, summary_ids = clean_text(draft.executive_summary)
    developments = [d for d in (claim(c) for c in draft.key_developments) if d]
    shift = claim(draft.narrative_shift)

    assessments = []
    for a in draft.narratives:
        if a.narrative_id not in narrative_ids:
            continue
        text, inline = clean_text(a.assessment)
        ids = clean_ids(a.evidence_ids + inline)
        if ids:
            assessments.append({"narrative_id": a.narrative_id, "assessment": text, "evidence_ids": ids})
        else:
            unsupported.append(text)

    total = len(draft.key_developments) + len(draft.narratives) + 1
    supported = len(developments) + len(assessments) + (1 if shift else 0)
    return {
        "executive_summary": summary,
        "executive_summary_evidence": summary_ids,
        "key_developments": developments,
        "narratives": assessments,
        "narrative_shift": shift,
        "key_entities": draft.key_entities,
        "unsupported_claims": unsupported,
        "metrics": {
            "claims": total,
            "supported_claims": supported,
            "evidence_coverage": round(supported / total, 3) if total else None,
        },
    }


def render_markdown(topic: str, window: str, narratives: list[NarrativeContext], assessment: dict, evidence: dict[str, Evidence]) -> str:
    labels = {n.id: n.label for n in narratives}
    out = [f"# Intelligence brief: {topic}", f"_Window: {window}_", "", "## Executive summary", assessment["executive_summary"], ""]

    out += ["## Observed metrics", "| Narrative | Articles | Growth | Negative | Languages |", "|---|---|---|---|---|"]
    for n in narratives:
        s = n.stats
        neg = s.get("sentiment", {}).get("negative")
        langs = ", ".join(f"{k} {v:.0%}" for k, v in s.get("languages", {}).items())
        out.append(f"| {n.label} | {s.get('volume')} | {_fmt_growth(s)} | {'n/a' if neg is None else f'{neg:.0%}'} | {langs} |")
    out.append("")

    def cite(ids: list[str]) -> str:
        return " " + " ".join(f"[{i}]" for i in ids) if ids else ""

    if assessment["key_developments"]:
        out.append("## Key developments")
        out += [f"- {d['claim']}{cite(d['evidence_ids'])}" for d in assessment["key_developments"]]
        out.append("")
    if assessment["narratives"]:
        out.append("## Narrative assessments")
        for a in assessment["narratives"]:
            out += [f"### {labels.get(a['narrative_id'], a['narrative_id'])}", f"{a['assessment']}{cite(a['evidence_ids'])}", ""]
    if assessment["narrative_shift"]:
        s = assessment["narrative_shift"]
        out += ["## Narrative shift", f"{s['claim']}{cite(s['evidence_ids'])}", ""]
    if assessment["key_entities"]:
        out += ["## Key entities", ", ".join(assessment["key_entities"]), ""]
    if assessment["unsupported_claims"]:
        out.append("## Unsupported statements (removed from findings)")
        out += [f"- _{c}_" for c in assessment["unsupported_claims"]]
        out.append("")

    out.append("## Evidence")
    for eid, e in evidence.items():
        out.append(f"- **[{eid}]** [{e.title}]({e.url}) ({e.source}, {e.language}, {e.published_at[:16]})")
    return "\n".join(out) + "\n"


def generate(client: OllamaClient, model: str, topic: str, window: str, narratives: list[NarrativeContext]) -> dict:
    narratives = narratives[:MAX_NARRATIVES]
    evidence = {e.id: e for n in narratives for e in n.evidence}
    draft = client.generate(model, SYSTEM, build_prompt(topic, window, narratives), BriefDraft, num_predict=1500)
    assessment = validate(draft, evidence, {n.id for n in narratives})
    return {
        "assessment": assessment,
        "evidence": {eid: asdict(e) for eid, e in evidence.items()},
        "markdown": render_markdown(topic, window, narratives, assessment, evidence),
    }
