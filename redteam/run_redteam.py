"""Run the prompt-injection red team and write redteam/results/{metrics.json,report.md,examples.json,cases.json}.

    uv run python -m redteam.run_redteam                 # full run (embedding model + LLM)
    uv run python -m redteam.run_redteam --no-llm        # survival check only, no API calls
    uv run python -m redteam.run_redteam --configs none,all --exposures body --samples 3

Pages are regenerated into data/redteam/pages/ on every run. LLM responses are cached
in data/redteam/llm_cache.json, so a re-run only pays for prompts it hasn't seen.
"""

import argparse
import json
import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from backend.config import get_settings
from backend.logging_setup import setup_logging
from pipeline.safety.defences import parse_defences
from redteam.pages import BASES, FAMILIES, MARKER, MARKER_PARTS, PAYLOADS, TECHNIQUES, generate_pages
from redteam.runner import EXPOSURES, CaseResult, FileCache, Runner
from redteam.survival import STAGES

log = logging.getLogger("redteam")
RESULTS = Path(__file__).parent / "results"
CONFIGS = ("none", "html", "unicode", "filter", "all")
MAX_EXAMPLES = 5


def _rate(hits: int, n: int) -> dict:
    return {"hits": hits, "n": n, "rate": round(hits / n, 3) if n else None}


def _form(r: CaseResult) -> str:
    """How the instruction reads once extracted: CSS and zero-width wrapping are gone
    by then, so only lookalike letters (unless normalised) change what the model sees."""
    return "lookalike letters" if r.technique == "homoglyph" and "unicode" not in parse_defences(r.config) else "plain text"


def summarise(results: list[CaseResult], configs: list[str], exposures: list[str]) -> dict:
    attacks = [r for r in results if r.technique]
    clean = [r for r in results if not r.technique]

    # Survival doesn't depend on the exposure: count each (page, config) once.
    survival: dict = defaultdict(dict)
    groups: dict = defaultdict(dict)
    for r in attacks:
        groups[(r.technique, r.config)][r.page] = r
    for (tech, cfg), by_page in groups.items():
        rs = list(by_page.values())
        survival[tech][cfg] = {stage: _rate(sum(r.survived[stage] for r in rs), len(rs)) for stage in STAGES}

    # Did the instruction reach the prompt, per method, exposure and defence (deterministic).
    in_prompt: dict = defaultdict(lambda: defaultdict(dict))
    cells: dict = defaultdict(list)
    for r in attacks:
        cells[(r.technique, r.exposure, r.config)].append(r)
    for (tech, exp, cfg), rs in cells.items():
        in_prompt[tech][exp][cfg] = _rate(sum(r.in_prompt for r in rs), len(rs))

    # How often the model obeys an instruction it was given, counting each distinct prompt once.
    obedience: dict = {}
    prompts: dict = {}
    for r in attacks:
        if r.in_prompt and r.samples:
            prompts.setdefault(r.prompt_id, r)
    for r in prompts.values():
        key = f"{r.style} | {BASES[r.base].language} | {_form(r)} | {r.exposure}"
        d = obedience.setdefault(key, {"style": r.style, "language": BASES[r.base].language, "form": _form(r),
                                       "exposure": r.exposure, "prompts": 0, "obeyed": 0, "samples": 0})
        d["prompts"] += 1
        d["obeyed"] += r.obeyed
        d["samples"] += r.samples

    # End to end: share of samples, over all attack pages, in which the model obeyed.
    end_to_end: dict = defaultdict(dict)
    by_style: dict = defaultdict(lambda: defaultdict(dict))
    for exp in exposures:
        for cfg in configs:
            rs = [r for r in attacks if r.exposure == exp and r.config == cfg]
            end_to_end[exp][cfg] = {
                "pages_exposed": _rate(sum(r.in_prompt for r in rs), len(rs)),
                "pages_obeyed": _rate(sum(r.obeyed > 0 for r in rs), sum(r.samples > 0 for r in rs)),
                "samples_obeyed": _rate(sum(r.obeyed for r in rs), sum(r.samples for r in rs)),
                "distinct_prompts_obeyed": len({r.prompt_id for r in rs if r.obeyed}),
            }
            for style in PAYLOADS:
                srs = [r for r in rs if r.style == style]
                by_style[style][exp][cfg] = {
                    "pages_exposed": _rate(sum(r.in_prompt for r in srs), len(srs)),
                    "samples_obeyed": _rate(sum(r.obeyed for r in srs), sum(r.samples for r in srs)),
                }

    # Clean pages: does a defence change the text, invent the marker, or weaken the brief?
    baseline = {(r.page, r.exposure): r for r in clean if r.config == "none"}
    clean_table: dict = {}
    for cfg in configs:
        for exp in exposures:
            rs = [r for r in clean if r.config == cfg and r.exposure == exp]
            changed = [r.page for r in rs if (b := baseline.get((r.page, exp))) and (r.excerpt or "") != (b.excerpt or "")]
            clean_table.setdefault(cfg, {})[exp] = {
                "pages": len(rs),
                "evidence_changed": changed,
                "false_marker_samples": sum(r.obeyed for r in rs),
                "samples": sum(r.samples for r in rs),
                "supported_claims": sum(r.supported_claims for r in rs),
                "claims": sum(r.claims for r in rs),
            }

    examples, shown = [], set()
    ranked = sorted((r for r in attacks if r.obeyed), key=lambda r: (r.exposure != "excerpt", r.config != "none", -r.obeyed))
    for r in ranked:
        if r.prompt_id in shown:
            continue
        shown.add(r.prompt_id)
        examples.append({**asdict(r), "same_prompt_as": sorted({f"{x.technique} [{x.config}]" for x in attacks if x.prompt_id == r.prompt_id})})
        if len(examples) == MAX_EXAMPLES:
            break

    return {
        "survival": survival,
        "in_prompt": in_prompt,
        "obedience": obedience,
        "end_to_end": end_to_end,
        "by_style": by_style,
        "clean_pages": clean_table,
        "distinct_attack_prompts": len({r.prompt_id for r in attacks if r.in_prompt}),
        "llm_errors": sum(r.error is not None for r in results),
        "examples": examples,
    }


def _cell(d: dict | None) -> str:
    if not d or not d["n"]:
        return "–"
    return f"{d['hits']}/{d['n']}"


def _pct(d: dict | None) -> str:
    if not d or not d["n"]:
        return "–"
    return f"{d['rate']:.0%} ({d['hits']}/{d['n']})"


EXPOSURE_TITLES = {"excerpt": "as the app runs (one evidence sentence per article)",
                   "body": "stress test (whole article text given to the model)"}


def render_report(meta: dict, s: dict, configs: list[str], exposures: list[str]) -> str:
    cols = " | ".join(configs)
    rule = "|---|" + "---|" * len(configs)
    out = [
        "# Prompt-injection red team: results",
        f"_Generated {meta['generated_at']} · model `{meta['model']}` · {meta['attack_pages']} attack pages, "
        f"{meta['clean_pages']} clean pages · {meta['cases']} cases · {meta.get('samples', 1)} LLM samples per prompt_",
        "",
        "Columns are defence settings. See docs/redteam.md for the method.",
        "",
        "## 1. Extraction survival",
        "",
        "Pages whose hidden instruction is still in the article text after trafilatura + `clean_body`.",
        "",
        f"| Hiding method | {cols} |", rule,
    ]
    for tech in TECHNIQUES:
        if tech in s["survival"]:
            out.append(f"| {tech} | " + " | ".join(_cell(s["survival"][tech].get(c, {}).get("cleaned")) for c in configs) + " |")
    out.append("")

    out += ["## 2. Exposure: is the instruction in the prompt?", "",
            "Pages whose instruction is in the evidence given to the model."]
    for exp in exposures:
        out += ["", f"**{exp}**: {EXPOSURE_TITLES[exp]}", "", f"| Hiding method | {cols} |", rule]
        for tech in TECHNIQUES:
            row = s["in_prompt"].get(tech, {}).get(exp)
            if row:
                out.append(f"| {tech} | " + " | ".join(_cell(row.get(c)) for c in configs) + " |")
    out.append("")

    out += ["## 3. Obedience: when the model sees the instruction, does it follow it?", "",
            f"Counted per distinct prompt ({s['distinct_attack_prompts']} in total): hiding methods that extract to the "
            "same text send the same prompt, so they are counted once.", "",
            "| Payload | Page language | Instruction reads as | Exposure | Distinct prompts | Samples obeyed |",
            "|---|---|---|---|---|---|"]
    for d in sorted(s["obedience"].values(), key=lambda d: (d["style"], d["language"], d["form"], d["exposure"])):
        out.append(f"| {d['style']} | {d['language']} | {d['form']} | {d['exposure']} | {d['prompts']} | "
                   f"{_pct(_rate(d['obeyed'], d['samples']))} |")
    out.append("")

    out += ["## 4. End to end: attack success by defence", "",
            "Over all attack pages. `exposed`: instruction in the prompt. `obeyed`: share of LLM samples containing "
            f"the code word {MARKER}.", ""]
    for exp in exposures:
        out += [f"**{exp}**: {EXPOSURE_TITLES[exp]}", "",
                "| Defence | Pages exposed | Samples obeyed | Distinct prompts obeyed | " +
                " | ".join(f"{st}: obeyed" for st in PAYLOADS) + " |",
                "|---|---|---|---|" + "---|" * len(PAYLOADS)]
        for cfg in configs:
            d = s["end_to_end"][exp][cfg]
            styles = " | ".join(_pct(s["by_style"][st][exp][cfg]["samples_obeyed"]) for st in PAYLOADS)
            out.append(f"| {cfg} | {_cell(d['pages_exposed'])} | {_pct(d['samples_obeyed'])} | "
                       f"{d['distinct_prompts_obeyed']} | {styles} |")
        out.append("")

    out += ["## 5. Cost on clean pages", "",
            "Clean twins and controls through the same path. `evidence changed`: the text given to the model differs "
            "from the no-defence run. `false marker`: samples with the code word and no attack.", "",
            "| Defence | Exposure | Evidence changed | False marker | Supported claims |", "|---|---|---|---|---|"]
    for cfg in configs:
        for exp in exposures:
            d = s["clean_pages"].get(cfg, {}).get(exp)
            if d:
                changed = ", ".join(d["evidence_changed"]) or "none"
                claims = f"{d['supported_claims']}/{d['claims']}" if d["claims"] else "–"
                false = f"{d['false_marker_samples']}/{d['samples']}" if d["samples"] else "–"
                out.append(f"| {cfg} | {exp} | {changed} | {false} | {claims} |")
    out.append("")

    out += ["## 6. Examples of attacks that worked", ""]
    if not s["examples"]:
        out.append("_None._")
    for e in s["examples"]:
        output = e["output"] or ""
        i = output.upper().find(MARKER_PARTS[0])
        snippet = output[max(0, i - 160): i + 60] if i >= 0 else output[:220]
        out += [f"**{e['style']} payload, {BASES[e['base']].language} page, defences `{e['config']}`, {e['exposure']} "
                f"exposure**: obeyed in {e['obeyed']}/{e['samples']} samples. Identical prompt from (method [defence]): "
                + ", ".join(f"`{p}`" for p in e["same_prompt_as"]),
                "", f"> Evidence given to the model: {(e['excerpt'] or '')[:400]}", "",
                f"> Model output: …{snippet}…", ""]
    if s["llm_errors"]:
        out.append(f"_{s['llm_errors']} cases had a failed LLM call; those samples are excluded._")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", default=",".join(CONFIGS), help=f"defence settings to compare (default {','.join(CONFIGS)})")
    parser.add_argument("--exposures", default=",".join(EXPOSURES), help="excerpt (as the app runs), body (stress test)")
    parser.add_argument("--samples", type=int, default=5, help="LLM samples per distinct prompt (default 5)")
    parser.add_argument("--no-llm", action="store_true", help="survival and evidence selection only; no API calls")
    parser.add_argument("--no-encoder", action="store_true", help="don't load the embedding model (skips the excerpt exposure)")
    parser.add_argument("--techniques", default=None, help="comma-separated subset of hiding methods")
    args = parser.parse_args()
    setup_logging()

    settings = get_settings()
    configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    exposures = [e.strip() for e in args.exposures.split(",") if e.strip()]
    if args.no_encoder:
        exposures = [e for e in exposures if e != "excerpt"]
    work = settings.data_dir / "redteam"
    pages = generate_pages(work / "pages")
    if args.techniques:
        wanted = set(args.techniques.split(","))
        pages = [p for p in pages if p.technique is None or p.technique in wanted]

    encode = None
    if "excerpt" in exposures:
        from pipeline import models

        encode = models.encoder().encode

    client = None
    if not args.no_llm:
        from backend.services.naming import make_client

        client = make_client(FileCache(work / "llm_cache.json"))
        if not client.available():
            raise SystemExit(f"{client.unavailable_hint} Use --no-llm for the survival check only.")

    runner = Runner(work / "pages", client, settings.llm_brief_model, encode, samples=args.samples)

    def progress(i: int, n: int, r: CaseResult) -> None:
        log.info("[%d/%d] %s [%s/%s] in_prompt=%s obeyed=%d/%d", i, n, r.page, r.config, r.exposure, r.in_prompt, r.obeyed, r.samples)

    results = runner.run(pages, configs, exposures, progress)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": settings.llm_brief_model if client else "none (--no-llm)",
        "samples": args.samples if client else 0,
        "attack_pages": sum(p.is_attack for p in pages),
        "clean_pages": sum(not p.is_attack for p in pages),
        "bases": {b.slug: b.language for b in BASES.values()},
        "families": FAMILIES,
        "configs": configs,
        "exposures": exposures,
        "cases": len(results),
    }
    summary = summarise(results, configs, exposures)

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "metrics.json").write_text(
        json.dumps({**meta, **{k: v for k, v in summary.items() if k != "examples"}}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (RESULTS / "examples.json").write_text(json.dumps(summary["examples"], ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS / "cases.json").write_text(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS / "report.md").write_text(render_report(meta, summary, configs, exposures), encoding="utf-8")
    log.info("wrote %s", RESULTS / "report.md")


if __name__ == "__main__":
    main()
