"""Brief quality.

- evidence coverage: share of the brief's claims that cite at least one real
  source (computed during generation, aggregated here)
- faithfulness: for every cited claim, an LLM judge reads only the cited
  evidence and says whether it supports the claim. An LLM judging an LLM is a
  known weak spot, so these verdicts are exported for a human spot-check.
"""

from typing import Literal

from pydantic import BaseModel

from pipeline.llm import OllamaClient

JUDGE_SYSTEM = """You check whether evidence supports a claim.
Use only the evidence given. Answer "supported" if the evidence clearly states or directly implies the claim,
"partial" if it supports only part of it, and "unsupported" if it does not support it or contradicts it."""


class Verdict(BaseModel):
    verdict: Literal["supported", "partial", "unsupported"]
    reason: str


def claims_with_evidence(content: dict) -> list[tuple[str, list[dict]]]:
    assessment, evidence = content["assessment"], content["evidence"]
    items = [(d["claim"], d["evidence_ids"]) for d in assessment.get("key_developments", [])]
    items += [(n["assessment"], n["evidence_ids"]) for n in assessment.get("narratives", [])]
    if assessment.get("narrative_shift"):
        items.append((assessment["narrative_shift"]["claim"], assessment["narrative_shift"]["evidence_ids"]))
    return [(claim, [evidence[i] for i in ids if i in evidence]) for claim, ids in items]


def judge(client: OllamaClient, model: str, claim: str, evidence: list[dict]) -> Verdict:
    lines = [f"- {e['title']}" + (f': "{e["excerpt"]}"' if e.get("excerpt") else "") for e in evidence]
    prompt = f"Claim: {claim}\n\nEvidence:\n" + "\n".join(lines)
    return client.generate(model, JUDGE_SYSTEM, prompt, Verdict, num_predict=120, temperature=0.0)


def evaluate_brief(content: dict, client: OllamaClient | None, model: str) -> dict:
    metrics = content["assessment"]["metrics"]
    result = {"evidence_coverage": metrics.get("evidence_coverage"), "claims": metrics.get("claims")}
    if client is None:
        result["faithfulness"] = None
        return result
    verdicts = []
    for claim, evidence in claims_with_evidence(content):
        v = judge(client, model, claim, evidence)
        verdicts.append({"claim": claim, "verdict": v.verdict, "reason": v.reason, "evidence": [e["id"] for e in evidence]})
    counts = {k: sum(v["verdict"] == k for v in verdicts) for k in ("supported", "partial", "unsupported")}
    result["faithfulness"] = {
        **counts,
        "supported_share": round(counts["supported"] / len(verdicts), 3) if verdicts else None,
        "verdicts": verdicts,
    }
    return result
