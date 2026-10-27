"""Step 6b: run the LLM extractor on in-scope evidence with both models and write the accuracy evaluation.

Run from the repo root:  PYTHONPATH=src .venv/bin/python scripts/run_extraction.py [--from-cache]
(--from-cache: rebuild outputs from data/raw/llm/ only, with no API call; a missing cache file is an error.)
Inputs:  data/processed/evidence.json, data/raw/articles/, data/cases/gold_signals.json, prompts/extract_v1.md,
         ANTHROPIC_API_KEY from .env (never printed or logged).
Outputs: data/processed/llm_signals_{haiku,sonnet}.json, docs/extraction_eval.md,
         raw responses cached in data/raw/llm/extract_v1/<model>/ (git-ignored; reused on re-runs).
"""

import json
import sys
from collections import Counter
from pathlib import Path

import anthropic
from dotenv import dotenv_values

from deal_radar.cases import load_cases
from deal_radar.features import apply_prd_rules
from deal_radar.extract import PROMPT_VERSION, ModelUnavailable, check_models, extract_document, match, norm
from deal_radar.rules import is_usable
from deal_radar.schemas import Evidence

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "cases"
ARTICLES = ROOT / "data" / "raw" / "articles"
LLM_CACHE = ROOT / "data" / "raw" / "llm" / PROMPT_VERSION
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
# Planned temperature 0 is not possible: anthropic SDK 1.5.0 has no `temperature` parameter, and the API returns
# 400 "`temperature` is deprecated for this model" for both models (checked 2026-10-27, request ids
# req_011CgTBqjUpeW24NKpDqnNKU and req_011CgTBqqmr51D6nFzRpP7HG). API defaults are used, identical for both models.
TEMPERATURE = None
# USD per million tokens (input, output). Provisional: Claude API list prices as cached in the claude-api
# reference on 2026-10-06, not verified against an invoice.
PRICING = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}
# One-line notes on each disagreement, written after reading the results. Key: (kind, evidence_id, signal_type),
# optionally prefixed by the model's short name for a model-specific note.
NOTES = {
    ("FP", "ev-cytora-65c38c74db", "governance_change"): "advisory board, not the company board (gold borderline 3); both models labelled it",
    ("FP", "ev-xeinadin-1678c55951", "pe_holding_period"): "names the sponsor but states no investment event or date; gold labels sponsor entry from dated announcements only",
    ("FP", "ev-xeinadin-1678c55951", "peer_deals_in_sector"): "another company's deal (sector context); gold excludes external_context (rule 1)",
    ("FP", "ev-xeinadin-776e274fc5", "sector_consolidation"): "sector context sentence; gold excludes external_context (rule 1)",
    ("FP", "ev-artificial_labs-bc9a862bce", "governance_change"): "chair appointment typed as governance_change instead of new_cfo_or_chair (also counted as a miss)",
    ("FP", "ev-peak_ai-a644f27c4f", "pe_holding_period"): "SoftBank VC stake typed as pe_holding_period; gold types VC rounds as large_recent_fundraise",
    ("FP", "ev-artificial_labs-bc9a862bce", "pe_holding_period"): "VC round lead (Augmentum) typed as pe_holding_period; same VC/PE confusion",
    ("FP", "ev-ptsg-2276fbd570", "recently_acquired"): "sponsor acquisition double-labelled; gold rule 2 labels it pe_holding_period only (Step 7 derives recency)",
    ("FP", "ev-ptsg-a027db6cd8", "recently_acquired"): "sponsor acquisition double-labelled; gold rule 2 labels it pe_holding_period only (Step 7 derives recency)",
    ("FP", "ev-xeinadin-c34d355840", "advisers_appointed"): "advisers on the completed 2022 Exponent deal: the deliberate trap (gold rule 5, prompt rule 5); a false direct-intent signal",
    ("missed", "ev-artificial_labs-bc9a862bce", "new_cfo_or_chair"): "chair appointment typed as governance_change instead",
    ("sonnet", "missed", "ev-oxford_ionics-543ab30517", "large_recent_fundraise"): "the only candidate was rejected by the 25-word quote check (see below); the safeguard rejected rather than truncated",
    ("duplicate", "ev-aab-8a6861f66c", "governance_change"): "second item for the same CEO succession (outgoing CEO's new role); not counted",
    ("duplicate", "ev-artificial_labs-bc9a862bce", "governance_change"): "COO / Head of Portfolio Strategy hires; executive roles, not board changes",
    ("rejected", "ev-oxford_ionics-543ab30517", "large_recent_fundraise"): "quote of 28 words exceeds the 25-word limit",
}
STEP7_NOTES = [
    "Gate 6 decision: `claude-sonnet-5-5` is the extraction model for Step 7; `claude-haiku-5-5` stays as the cost "
    "benchmark for the scale design.",
    "Post-extraction rules are allowed ONLY if they follow directly from PRD definitions. No rule may be designed from "
    "individual gold disagreements. Report metrics before and after any such rule, separately.",
    "Scoring must ensure sector-context mentions, undated sponsor references and advisers on completed past deals can "
    "never create direct-intent points.",
    "Model comparison is illustrative (16 articles, 18 gold signals), not statistically conclusive.",
    "Design note for slides: at scale, route only documents with possible intent language to the stronger model; "
    "Haiku made the costliest error (a false advisers_appointed signal).",
]
RECOMMENDATION = (
    "**Use `claude-sonnet-5-5` for Step 7.** On this sample it had higher precision (73% vs 65%) at slightly lower "
    "recall (89% vs 94%), no duplicates, and, most importantly, **no false direct-intent signal**: Haiku labelled "
    "advisers on a completed 2022 deal as `advisers_appointed`, exactly the error that would most inflate a "
    "company's score. Sonnet's two misses are a type confusion shared with Haiku (chair → governance_change) and one "
    "quote correctly rejected by the 25-word check. Both models share the remaining false positives "
    "(`recently_acquired` double-labels of sponsor deals, sector-context sentences, an advisory board), which are "
    "consistent and can be handled deterministically in Step 7. Cost is not a deciding factor at pilot scale "
    "(~$0.13 vs ~$0.01 for 16 documents); Haiku (~13× cheaper per run here) is the candidate to re-test at 100k-company "
    "scale with a stricter prompt. With 16 documents these differences are a handful of signals each: illustrative, "
    "not significant."
)


def main() -> None:
    if "--from-cache" in sys.argv:
        client = None  # no API call at all; a missing cache file is an error (extract.extract_document)
    else:
        key = dotenv_values(ROOT / ".env").get("ANTHROPIC_API_KEY")
        if not key:
            sys.exit("ANTHROPIC_API_KEY is missing or empty in .env; nothing was sent.")
        client = anthropic.Anthropic(api_key=key)
        try:
            check_models(client, list(MODELS.values()), key, TEMPERATURE)
        except ModelUnavailable as exc:
            sys.exit(f"STOP: model unavailable, no substitution: {exc}")

    companies = {c["company_id"]: c for c in json.loads((CASES / "companies.json").read_text())}
    aliases = {cid: v["aliases"] for cid, v in json.loads((CASES / "evidence_queries.json").read_text())["companies"].items()}
    _, _, pairs = load_cases(CASES)
    anchor = {}
    for p in pairs:
        anchor[p.deal_company_id] = anchor[p.control_company_id] = p.anchor_date
    evidence = [Evidence.model_validate(e) for e in json.loads((ROOT / "data" / "processed" / "evidence.json").read_text())]
    scope = [e for e in evidence if is_usable(e, anchor[e.company_id])]
    gold = json.loads((CASES / "gold_signals.json").read_text())["signals"]
    if {e.evidence_id for e in scope} != set(gold):
        sys.exit("STOP: in-scope evidence and gold ids differ")
    system = (ROOT / "prompts" / f"{PROMPT_VERSION}.md").read_text()

    texts = {e.evidence_id: (ARTICLES / f"{e.evidence_id}.txt").read_text() for e in scope}
    results = {}
    for short, model in MODELS.items():
        per_doc = {}
        for e in scope:
            per_doc[e.evidence_id] = extract_document(
                client, model, system, e, anchor[e.company_id], texts[e.evidence_id],
                aliases[e.company_id][0], aliases[e.company_id], LLM_CACHE / model, TEMPERATURE)
        signals = [s for r in per_doc.values() for s in r["signals"]]
        (ROOT / "data" / "processed" / f"llm_signals_{short}.json").write_text(
            json.dumps([s.model_dump(mode="json") for s in signals], indent=1, ensure_ascii=False) + "\n")
        results[short] = per_doc
        print(f"{model}: {len(signals)} signals, "
              f"{sum(len(r['rejections']) for r in per_doc.values())} rejected, "
              f"{sum(r['failure'] is not None for r in per_doc.values())} failures")

    (ROOT / "docs" / "extraction_eval.md").write_text(render(scope, companies, gold, texts, results))


def model_stats(model, per_doc, gold, texts):
    signals = [s for r in per_doc.values() for s in r["signals"]]
    m = match(gold, signals)
    rejections = [x for r in per_doc.values() for x in r["rejections"]]
    returned = len(signals) + len(rejections)
    quote_ok = returned - sum(x["reason"] == "quote_not_in_text" for x in rejections)
    attempts = [a for r in per_doc.values() for a in r["attempts"]]
    tin, tout = sum(a["input_tokens"] for a in attempts), sum(a["output_tokens"] for a in attempts)
    pin, pout = PRICING[model]
    return {"m": m, "signals": signals, "rejections": rejections, "returned": returned,
            "quote_validity": quote_ok / returned if returned else None,
            "failures": [eid for eid, r in per_doc.items() if r["failure"]], "calls": len(attempts),
            "tokens_in": tin, "tokens_out": tout, "cost": tin / 1e6 * pin + tout / 1e6 * pout}


def pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def render(scope, companies, gold, texts, results) -> str:
    stats = {short: model_stats(MODELS[short], results[short], gold, texts) for short in MODELS}
    L = ["# Extraction accuracy (Step 6b)", "",
         "Generated by `scripts/run_extraction.py`. Do not edit by hand.", "",
         "**Caveat:** illustrative only. "
         f"{len(scope)} documents and {sum(map(len, gold.values()))} gold signals; the gold labels were written by an AI "
         "model (Claude) before any prompt or extraction existed and were reviewed and approved by the user before "
         "extraction (`docs/gold_review.md`).", "",
         "## Setup",
         f"- Prompt: `prompts/{PROMPT_VERSION}.md`, identical for both models. Input = target company name + article text.",
         f"- Models: {', '.join(f'`{m}`' for m in MODELS.values())}; identical request parameters (system prompt, "
         "max_tokens 4000, no other settings).",
         "- **Deviation from plan: temperature 0 was not used.** anthropic SDK 1.5.0 has no `temperature` parameter, and "
         "the API rejects it for both models (HTTP 400 \"`temperature` is deprecated for this model\", request ids "
         "req_011CgTBqjUpeW24NKpDqnNKU and req_011CgTBqqmr51D6nFzRpP7HG, 2026-10-27). API default settings were used, "
         "identical for both models. Consequences: outputs are not guaranteed deterministic (re-runs reuse the cached "
         "raw responses in `data/raw/llm/`, so this report is reproducible from the cache), and the API's default "
         "reasoning effort differs by model (per the Claude API reference: medium for Haiku 5.5, high for Sonnet 5.5).",
         "- Scope: Evidence usable at the pair anchor after the content_leak exclusion. Undated, post-anchor and "
         "excluded items are never sent (enforced in `extract.extract_document`).",
         "- Post-checks (deterministic, each rejection logged below): quote is a whitespace-normalised substring of the "
         "article text; subject_company names the target; signal_type belongs to signal_class; quote ≤ 25 words.",
         "- publication_date and source_url always come from the Evidence record, never from the LLM.",
         "- Matching: one-to-one on (evidence_id, signal_type). Further predictions of the same type in the same "
         "document are duplicates: reported separately, counted as neither TP nor FP.",
         "- Pricing used for cost (USD per million tokens, input/output), **provisional** (list prices as cached in "
         "the Claude API reference on 2026-10-06, not invoice-verified): "
         + "; ".join(f"`{m}` ${p[0]:.2f}/${p[1]:.2f}" for m, p in PRICING.items()) + ".", "",
         "## Headline", "",
         "| Metric | " + " | ".join(MODELS) + " |", "|---|" + "---|" * len(MODELS)]
    rows = [
        ("True positives", lambda s: s["m"]["tp"]),
        ("False positives", lambda s: len(s["m"]["fp"])),
        ("False negatives (missed gold)", lambda s: len(s["m"]["fn"])),
        ("Precision", lambda s: pct(s["m"]["precision"])),
        ("Recall", lambda s: pct(s["m"]["recall"])),
        ("Duplicates (not TP)", lambda s: len(s["m"]["duplicates"])),
        ("Quote-validity rate (returned items whose quote is in the text)", lambda s: pct(s["quote_validity"])),
        ("Status agreement on matched signals", lambda s: pct(s["m"]["status_agreement"])),
        ("Post-check rejections", lambda s: len(s["rejections"])),
        ("Extraction failures (invalid output after retry)", lambda s: len(s["failures"])),
        ("API calls (incl. retries)", lambda s: s["calls"]),
        ("Input / output tokens", lambda s: f"{s['tokens_in']:,} / {s['tokens_out']:,}"),
        ("Cost estimate (USD, provisional)", lambda s: f"${s['cost']:.4f}"),
    ]
    L += [f"| {name} | " + " | ".join(str(f(stats[short])) for short in MODELS) + " |" for name, f in rows]
    L += ["", f"Total estimated API cost for this run: ${sum(s['cost'] for s in stats.values()):.4f} (excludes the two "
          "minimal model-check calls).", ""]

    L += ["## Per document (signal types; gold vs models)", "",
          "| evidence_id | company | gold | " + " | ".join(MODELS) + " |", "|---|---|---|" + "---|" * len(MODELS)]

    def types(items):
        c = Counter(items)
        return ", ".join(f"{t}×{n}" if n > 1 else t for t, n in sorted(c.items())) or "—"
    for e in scope:
        eid = e.evidence_id
        cells = []
        for short in MODELS:
            r = results[short][eid]
            cell = types(s.signal_type for s in r["signals"])
            if r["failure"]:
                cell = f"FAILURE ({r['failure']})"
            cells.append(cell)
        L.append(f"| {eid} | {e.company_id} | {types(g['signal_type'] for g in gold[eid])} | " + " | ".join(cells) + " |")

    L += ["", "## Disagreements", ""]
    for short in MODELS:
        s = stats[short]
        L += [f"### {short} (`{MODELS[short]}`)", ""]
        def note(kind, eid, stype):
            text = NOTES.get((short, kind, eid, stype)) or NOTES.get((kind, eid, stype))
            return f" — {text}" if text else ""
        lines = []
        lines += [f"- FP · {p.evidence_id} · {p.signal_type} ({p.status}) · \"{p.evidence_quote}\"{note('FP', p.evidence_id, p.signal_type)}" for p in s["m"]["fp"]]
        lines += [f"- missed · {eid} · {g['signal_type']} ({g['status']}) · gold quote \"{g['evidence_quote']}\"{note('missed', eid, g['signal_type'])}" for eid, g in s["m"]["fn"]]
        lines += [f"- duplicate · {p.evidence_id} · {p.signal_type} · \"{p.evidence_quote}\"{note('duplicate', p.evidence_id, p.signal_type)}" for p in s["m"]["duplicates"]]
        lines += [f"- status · {p.evidence_id} · {p.signal_type} · gold {g['status']} vs {p.status}"
                  for g, p in s["m"]["pairs"] if g["status"] != p.status]
        lines += [f"- rejected ({x['reason']}) · {x['evidence_id']} · {x['item']['signal_type']} · subject "
                  f"\"{x['item']['subject_company']}\" · \"{x['item']['evidence_quote']}\"{note('rejected', x['evidence_id'], x['item']['signal_type'])}" for x in s["rejections"]]
        lines += [f"- failure · {eid}" for eid in s["failures"]]
        L += lines or ["- none"]
        L.append("")
    L += ["## Audit: every prediction and every gold signal", "",
          "Recompute by hand: precision = correct / (correct + wrong); recall = matched / (matched + missed). "
          "Matching is one-to-one on (evidence_id, signal_type). `duplicate` and `rejected-by-check` predictions are "
          "counted as neither correct nor wrong.", ""]
    for short in MODELS:
        s, m = stats[short], stats[short]["m"]
        outcome = {p.signal_id: "correct" for _, p in m["pairs"]}
        outcome |= {p.signal_id: "wrong" for p in m["fp"]} | {p.signal_id: "duplicate" for p in m["duplicates"]}
        matched = {id(g) for g, _ in m["pairs"]}
        L += [f"### {short} (`{MODELS[short]}`): predictions", "",
              "| # | evidence_id | signal_type | status | outcome | quote |", "|---|---|---|---|---|---|"]
        rows = [(p.evidence_id, p.signal_type, p.status, outcome[p.signal_id], p.evidence_quote) for p in s["signals"]]
        rows += [(x["evidence_id"], x["item"]["signal_type"], x["item"]["status"], f"rejected-by-check ({x['reason']})",
                  x["item"]["evidence_quote"]) for x in s["rejections"]]
        L += [f"| {i} | {eid} | {t} | {st} | {o} | \"{q}\" |" for i, (eid, t, st, o, q) in enumerate(rows, 1)]
        count = Counter(o.split(" ")[0] for *_, o, _ in rows)
        L += ["", f"### {short} (`{MODELS[short]}`): gold signals", "",
              "| # | evidence_id | signal_type | gold status | outcome |", "|---|---|---|---|---|"]
        gold_rows = [(eid, g["signal_type"], g["status"], "matched" if id(g) in matched else "missed")
                     for eid, items in gold.items() for g in items]
        L += [f"| {i} | {eid} | {t} | {st} | {o} |" for i, (eid, t, st, o) in enumerate(gold_rows, 1)]
        gcount = Counter(o for *_, o in gold_rows)
        totals = (count["correct"], count["wrong"], gcount["missed"])
        if totals != (m["tp"], len(m["fp"]), len(m["fn"])) or gcount["matched"] != m["tp"]:
            sys.exit(f"STOP: audit totals {totals} do not reproduce the headline for {short}")
        L += ["", f"Totals ({short}): correct {count['correct']}, wrong {count['wrong']}, duplicate {count['duplicate']}, "
              f"rejected-by-check {count['rejected-by-check']}; gold matched {gcount['matched']}, missed {gcount['missed']}. "
              f"Precision {count['correct']}/{count['correct'] + count['wrong']} = {pct(m['precision'])}; recall "
              f"{gcount['matched']}/{gcount['matched'] + gcount['missed']} = {pct(m['recall'])}.", ""]
    sonnet = stats["sonnet"]
    after = match(gold, apply_prd_rules(sonnet["signals"]))
    removed = len(sonnet["signals"]) - len(apply_prd_rules(sonnet["signals"]))
    L += ["## Metrics after PRD-derived rules (Step 7, `claude-sonnet-5-5`)", "",
          "Exactly the Step 6 matching (`extract.match`: one-to-one on (evidence_id, signal_type); duplicates and "
          "rejected-by-check predictions count as neither correct nor wrong). Only two rules are applied, both as "
          "filters on the predicted signals before matching, and both follow from PRD §8 definitions (not from gold "
          "disagreements): (1) drop `external_context` signals (PRD §8: context only); (2) drop LLM "
          "`recently_acquired` signals (the counter-signal is derived from the sponsor entry date). "
          "Implemented in `features.apply_prd_rules`, the same function the features use.", "",
          "| | Before rules | After rules |", "|---|---|---|",
          f"| Predictions considered | {len(sonnet['signals'])} | {len(sonnet['signals']) - removed} |",
          f"| Correct (TP) | {sonnet['m']['tp']} | {after['tp']} |",
          f"| Wrong (FP) | {len(sonnet['m']['fp'])} | {len(after['fp'])} |",
          f"| Missed (FN) | {len(sonnet['m']['fn'])} | {len(after['fn'])} |",
          f"| Duplicates | {len(sonnet['m']['duplicates'])} | {len(after['duplicates'])} |",
          f"| Rejected by check | {len(sonnet['rejections'])} | {len(sonnet['rejections'])} |",
          f"| Precision | {pct(sonnet['m']['precision'])} | {pct(after['precision'])} |",
          f"| Recall | {pct(sonnet['m']['recall'])} | {pct(after['recall'])} |", "",
          "Removed by the rules: " + ("; ".join(f"{s.evidence_id} · {s.signal_type}" for s in sonnet["signals"]
                                                if s not in apply_prd_rules(sonnet["signals"])) or "none") + ".", ""]
    if RECOMMENDATION:
        L += ["## Recommendation for Step 7", "", RECOMMENDATION, ""]
    L += ["## Notes for Step 7", "", *[f"- {n}" for n in STEP7_NOTES], ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
