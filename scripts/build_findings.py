"""Step 9: generate docs/findings.md and the chart data in data/processed/charts/ from committed data files.

Run from the repo root:  PYTHONPATH=src .venv/bin/python scripts/build_findings.py   (or via scripts/run_all.py)
Every number in docs/findings.md is computed here from the data files; nothing is typed by hand.
Inputs: features.json, scores.json, charts/extraction_compare.json, evidence.json, registry_events.json,
        llm_signals_sonnet.json, registry_signals.json, data/cases/*, docs/scoring.md (config), docs/evidence_log.md.
Outputs: docs/findings.md; charts/pairs_scores.json, evidence_funnel.json, signal_timeline.json.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_scoring import PE_PAIRS, confirmed_signal_ids  # noqa: E402

from deal_radar.cases import load_cases  # noqa: E402
from deal_radar.features import late_clues, load_json_list  # noqa: E402
from deal_radar.rules import is_usable  # noqa: E402
from deal_radar.schemas import Evidence, RegistryEvent, Signal  # noqa: E402
from deal_radar.score import VARIANTS, compare_pairs, contributions, hypothesis_verdicts, load_config  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
CASES = ROOT / "data" / "cases"
CHARTS = PROCESSED / "charts"
FINDINGS = ROOT / "docs" / "findings.md"
PROXY = ("ptsg", "xeinadin")
USABLE_RULE = ("**Usable** (one rule for news and registry events alike): an item is usable if it has a publication "
               "date strictly before its pair's anchor (deal announcement) date (`rules.is_usable`).")


def usable_at_anchor(items: list, anchor: dict) -> list:
    """The shared usability rule for news evidence and registry events: rules.is_usable at the pair's anchor."""
    return [x for x in items if is_usable(x, anchor[x.company_id])]


def load_all() -> dict:
    """Everything the findings and charts need, from committed files only."""
    _, _, pairs = load_cases(CASES)
    config = load_config((ROOT / "docs" / "scoring.md").read_text())
    rows = json.loads((PROCESSED / "features.json").read_text())
    confirmed = confirmed_signal_ids()
    sonnet = load_json_list(PROCESSED / "llm_signals_sonnet.json", Signal)
    registry_signals = load_json_list(PROCESSED / "registry_signals.json", Signal)
    raw_events = json.loads((PROCESSED / "registry_events.json").read_text())
    return {
        "pairs": pairs, "config": config, "rows": rows, "confirmed": confirmed,
        "scores": json.loads((PROCESSED / "scores.json").read_text()),
        "comparisons": {v: compare_pairs(rows, config, confirmed, v) for v in VARIANTS},
        "extraction": json.loads((CHARTS / "extraction_compare.json").read_text()),
        "evidence": load_json_list(PROCESSED / "evidence.json", Evidence),
        "events": [RegistryEvent.model_validate(e) for e in raw_events["events"]],
        "queries": json.loads((CASES / "evidence_queries.json").read_text())["queries"],
        "log": (ROOT / "docs" / "evidence_log.md").read_text(),
        "clues": {p.pair_id: late_clues(p, sonnet + registry_signals) for p in pairs},
    }


def wtl(comparisons: list[dict]) -> tuple[int, int, int]:
    c = Counter(x["outcome"] for x in comparisons)
    return c["win"], c["tie"], c["loss"]


def funnel(d: dict) -> dict:
    """Evidence and registry counts. Opened pages split exactly into blocked + discarded + kept (evidence_log.md)."""
    log = d["log"]
    stage = Counter()
    for part in (log.split("# Pass 1 detail")[1].split("# Pass 2 detail")[0], log.split("# Pass 2 detail")[1]):
        for m in re.finditer(r"opened (\d+), kept (\d+), discarded (\d+), blocked (\d+)\.", part):
            for k, v in zip(("opened", "kept", "discarded", "blocked"), map(int, m.groups())):
                stage[k] += v
    exceptions_kept = log.split("## Logged exceptions")[1].split("\n## ")[0].count("· kept (exception)")
    anchor = {}
    for p in d["pairs"]:
        anchor[p.deal_company_id] = anchor[p.control_company_id] = p.anchor_date
    usable = usable_at_anchor(d["evidence"], anchor)
    events = d["events"]
    out = {
        "search_results": sum(q["result_count"] for q in d["queries"]),
        "queries": len(d["queries"]),
        "unique_urls": len({r["url"] for q in d["queries"] for r in q["results"]}),
        "pages_opened": stage["opened"] + exceptions_kept,
        "blocked_or_paywalled": stage["blocked"],
        "discarded": stage["discarded"],
        "kept": len(d["evidence"]),
        "usable_dated": len(usable),
        "registry_events": len(events),
        "registry_with_publication_date": sum(e.publication_date is not None for e in events),
        "registry_without_usable_publication_date": sum(e.publication_date is None for e in events),
        "registry_usable_before_anchor": len(usable_at_anchor(events, anchor)),
        "usable_dated_by_company": {cid: sum(e.company_id == cid for e in usable) for cid in anchor},
        "officer_events": sum(e.event_type.startswith("officer") for e in events),
        "officer_events_with_occupation": sum(e.event_type.startswith("officer") and bool(e.details.get("occupation"))
                                              for e in events),
        "modified_after_anchor": log.count("**discarded: modified_after_anchor**"),
        "after_anchor": log.count("**discarded: after_anchor**"),
        "content_leak": len([ln for ln in log.split("## Excluded as content_leak")[1].split("\n## ")[0].splitlines()
                             if ln.startswith("- ev-")]),
    }
    if stage["kept"] + exceptions_kept != out["kept"] or \
            out["pages_opened"] != out["blocked_or_paywalled"] + out["discarded"] + out["kept"]:
        raise SystemExit("evidence_log.md counts do not reconcile with evidence.json")
    return out


def chart_pairs_scores(d: dict) -> list[dict]:
    full = {(c["pair_id"], c["horizon"]): c for c in d["comparisons"]["full"]}
    hold = {(c["pair_id"], c["horizon"]): c for c in d["comparisons"]["holding_only"]}
    return [{"pair_id": k[0], "horizon": k[1], "deal": c["deal"], "control": c["control"],
             "full": {"deal": c["deal_score"], "control": c["control_score"], "outcome": c["outcome"]},
             "holding_only": {"deal": hold[k]["deal_score"], "control": hold[k]["control_score"],
                              "outcome": hold[k]["outcome"]}}
            for k, c in full.items()]


def chart_funnel(f: dict) -> dict:
    return {
        "note": ("Search-level counts (search_results, unique_urls) are not a subset chain. Pages were opened "
                 "mechanically from the search results; every opened page ends in exactly one of blocked_or_paywalled, "
                 "discarded or kept (evidence_log.md); usable_dated is a subset of kept."),
        "search": [{"label": f"Search results ({f['queries']} queries; with repeats)", "count": f["search_results"]},
                   {"label": "Unique URLs in search results", "count": f["unique_urls"]}],
        "opened": {"label": "Pages opened (pass 1 + pass 2 + 1 logged exception)", "count": f["pages_opened"],
                   "split": [{"label": "Blocked or paywalled", "count": f["blocked_or_paywalled"]},
                             {"label": "Discarded (other company, dates, duplicates, leakage, cap)", "count": f["discarded"]},
                             {"label": "Kept as evidence", "count": f["kept"]}]},
        "usable_dated": {"label": "Kept and dated before the pair anchor (usable)", "count": f["usable_dated"]},
        "registry": [{"label": "Companies House events", "count": f["registry_events"]},
                     {"label": "With a publication date", "count": f["registry_with_publication_date"]},
                     {"label": "Without a usable publication date (no unique matching filing)",
                      "count": f["registry_without_usable_publication_date"]},
                     {"label": "Published before the pair anchor (usable)", "count": f["registry_usable_before_anchor"]}],
    }


def chart_timeline(d: dict) -> list[dict]:
    out = []
    for p in d["pairs"]:
        companies = []
        for cid, role in ((p.deal_company_id, "deal"), (p.control_company_id, "control")):
            horizons = {}
            for r in (r for r in d["rows"] if r["company_id"] == cid and r["pair_id"] == p.pair_id):
                f = r["features"]
                visible = [k for k in ("intent_present", "readiness_18m", "debt_event_12m", "recently_acquired",
                                       "fundraise_12m") if f[k]]
                if f["pe_holding_years"] is not None:
                    visible.insert(0, f"pe_holding_clock ({f['holding_basis']})")
                horizons[r["horizon"]] = visible
            late = sorted({s.signal_type for s in d["clues"][p.pair_id] if s.company_id == cid})
            companies.append({"company_id": cid, "role": role, "horizons": horizons, "late_window": late})
        out.append({"pair_id": p.pair_id, "anchor": p.anchor_date.isoformat(), "companies": companies})
    return out


def render(d: dict, f: dict) -> str:
    comps, ex = d["comparisons"], d["extraction"]
    W = {v: wtl(comps[v]) for v in VARIANTS}
    v = hypothesis_verdicts(d["rows"], comps, [p.pair_id for p in d["pairs"]], PE_PAIRS)
    h2, h3 = v["H2"], v["H3"]
    row_of = {(r["pair_id"], r["horizon"], r["role"]): r for r in d["rows"]}
    cmp_of = {var: {(c["pair_id"], c["horizon"]): c for c in comps[var]} for var in VARIANTS}

    def diffs(c):
        dc = {x["term"]: x["value"] for x in contributions(row_of[(c["pair_id"], c["horizon"], "deal")], d["config"], d["confirmed"])}
        kc = {x["term"]: x["value"] for x in contributions(row_of[(c["pair_id"], c["horizon"], "control")], d["config"], d["confirmed"])}
        return {t: dc.get(t, 0) - kc.get(t, 0) for t in set(dc) | set(kc) if abs(dc.get(t, 0) - kc.get(t, 0)) > 1e-9}
    losses = [c for c in comps["full"] if c["outcome"] == "loss"]
    debt_losses = [c for c in losses if [t for t, x in diffs(c).items() if x < 0] == ["debt_event_12m"]]
    flips = [c for c in comps["full"] if c["outcome"] != cmp_of["holding_only"][(c["pair_id"], c["horizon"])]["outcome"]
             and cmp_of["holding_only"][(c["pair_id"], c["horizon"])]["outcome"] == "win"]
    debt_only_wins = [c for c in comps["full"] if c["outcome"] == "win" and c["category"] == "weak (debt-only)"]
    pe_cats = h2["categories"]["PE"]
    intent_rows = v["H1"]["intent_rows"]
    intent_clues = [(pid, s) for pid, ss in d["clues"].items() for s in ss
                    if s.signal_class == "direct_intent"]
    role = {}
    for p in d["pairs"]:
        role[p.deal_company_id], role[p.control_company_id] = "deal", "control"
    unconfirmed_wins = [c for c in comps["full"] if c["outcome"] == "win"
                        and cmp_of["verified_only"][(c["pair_id"], c["horizon"])]["outcome"] != "win"]
    sens_same = sum(c["outcome"] == cmp_of["sensitivity"][(c["pair_id"], c["horizon"])]["outcome"] for c in comps["full"])
    hk, sn = ex["models"]["haiku"], ex["models"]["sonnet"]
    ratio = sn["cost_usd_provisional"] / hk["cost_usd_provisional"]
    zero_news = [c for c, n in f["usable_dated_by_company"].items() if n == 0]
    n_comp, n_pairs = len(comps["full"]), len(d["pairs"])
    leak_line = next(ln for ln in d["log"].split("## Excluded as content_leak")[1].splitlines() if "oxford_ionics" in ln)
    oxford_hit = re.search(r'hit "([^"]+)"', leak_line).group(1)
    fmtw = lambda t: f"{t[0]} wins / {t[1]} ties / {t[2]} losses"  # noqa: E731

    L = ["# Findings (Step 9)", "",
         "Generated by `scripts/build_findings.py` from the data files; every number below is computed, not typed. "
         "Do not edit by hand. Rebuild with `PYTHONPATH=src .venv/bin/python scripts/run_all.py`.", "",
         "All results are **hypothesis-generating, not validation**: "
         f"{n_pairs} matched pairs, {n_comp} correlated deal-vs-control comparisons. Scores are ranking aids, never "
         "probabilities, and nothing here claims predictive performance. PTSG and Xeinadin holding periods are an "
         "**announcement-based proxy** (sponsor entry = announcement; completion not confirmed).", "",
         USABLE_RULE, "",
         "## Headline", "",
         f"1. **Tested:** a transparent, pre-registered score on {n_pairs} matched UK pairs (one company that announced "
         "a change of control in Jan–Sep 2025, one similar company with no publicly observed transaction), at 12, 6 "
         "and 3 months before each deal, using only public information published before each date.",
         f"2. **Found:** the PE holding clock was the only consistent separator (holding-only: {fmtw(W['holding_only'])}); "
         f"the full score's extra wins came from weak signals that also caused all {len(losses)} losses; no intent "
         f"signal was visible before the 3-month mark; and free public news was thin ({f['usable_dated']} usable dated "
         f"articles vs {f['registry_usable_before_anchor']} usable registry events).",
         "3. **Means for the product:** lead with registry-based clocks for PE-backed companies, license news to "
         "capture intent, route only intent-language documents to the stronger model, and keep the leakage guards as "
         "standard.", "",
         "## Findings", ""]

    def finding(n, title, claim, evidence, implication, caveat):
        return [f"### {n}. {title}", "", f"- **Claim:** {claim}", f"- **Evidence:** {evidence}",
                f"- **Design implication:** {implication}", f"- **Caveat:** {caveat}", ""]

    L += finding(1, "The PE holding clock was the only consistent separator",
                 "Where a PE sponsor's holding clock existed, the deal company had held longer than its control at every "
                 "horizon in both PE pairs, and nothing else separated pairs consistently.",
                 f"Holding-only benchmark: {fmtw(W['holding_only'])} over {n_comp} comparisons (non-PE pairs tie by "
                 f"construction). Full score: {fmtw(W['full'])}. Every PE-pair win under the full score is clock-driven "
                 f"({pe_cats.get('clock-driven', 0)} of {h2['wins']['PE']}). Sources: `docs/scoring_results.md`, "
                 "`data/processed/scores.json`.",
                 "Lead the score with the holding clock for PE-backed companies; keep it transparent and dated.",
                 "Two PE pairs are anecdotal. PTSG and Xeinadin holding periods are an announcement-based proxy. "
                 "The 5-year cap is an assumption about a typical hold, not a fact.")
    L += finding(2, "Weak signals added noise",
                 "Debt (charge) events produced extra wins and also every loss.",
                 f"{len(debt_only_wins)} full-score wins rest on debt events alone (labelled weak); in {len(debt_losses)} of "
                 f"{len(losses)} losses the control's debt event was the only term against the deal. "
                 + "; ".join(f"{c['pair_id']} at {c['horizon']}: a correct holding-only call became a full-score "
                             f"{c['outcome']} ({c['deal_score']:.2f} vs {c['control_score']:.2f})" for c in flips)
                 + ". Source: `docs/scoring_results.md` (disagreements with holding-only).",
                 "Treat debt events as context, or require them to co-occur with a clock or intent before they score.",
                 "Debt events are frequent at controls in this sample (e.g. Cognism); the pattern may differ for "
                 "leveraged PE groups at scale.")
    L += finding(3, "Intent never appeared before the 3-month mark",
                 "No snapshot at 12, 6 or 3 months had a direct-intent signal; the only intent found was at a control, "
                 "in the last 3 months before its pair's deal date.",
                 f"`intent_present` is true in {intent_rows} of {len(d['rows'])} rows. Late-window intent: "
                 + "; ".join(f"{s.company_id} ({role[s.company_id]}, {pid}) {s.signal_type} ({s.status}, published "
                             f"{s.publication_date})" for pid, s in intent_clues)
                 + ". Sources: `docs/features.md`, `docs/scoring_results.md`.",
                 "Intent needs fresher, broader news than free sources give; show late clues separately as alerts, "
                 "not as score inputs, until lead time is demonstrated.",
                 "H1 is untestable on this sample. One intent case is anecdotal; the control did not transact in its "
                 "check period, so this is also a false-positive warning.")
    L += finding(4, "Free public news was thin compared with the registry",
                 "Most of what we know comes from Companies House; free, dated news was scarce and often blocked.",
                 f"{f['search_results']} search results ({f['unique_urls']} unique URLs) from {f['queries']} queries; "
                 f"{f['pages_opened']} pages opened, of which {f['blocked_or_paywalled']} blocked or paywalled, "
                 f"{f['discarded']} discarded and {f['kept']} kept; {f['usable_dated']} kept items are dated before "
                 f"their pair's deal date (usable). {len(zero_news)} of {len(f['usable_dated_by_company'])} companies have no usable "
                 f"dated news ({', '.join(zero_news)}). Registry: {f['registry_events']} events, "
                 f"{f['registry_usable_before_anchor']} usable before the deal dates. Sources: `docs/evidence_log.md`, "
                 "`data/processed/charts/evidence_funnel.json`.",
                 "The product's main running cost is licensed news access, not the LLM; budget for a news licence "
                 "first.",
                 "Search coverage depends on one search tool and grouped queries; missing evidence is never treated "
                 "as absence of a signal.")
    L += finding(5, "Leakage traps were real and were caught",
                 "Pages that look old can carry information from after the deal date.",
                 f"Discard reasons recorded in `docs/evidence_log.md`: {f['modified_after_anchor']} pages "
                 "`modified_after_anchor` (metadata shows an edit on or after the pair's deal date; this guard runs "
                 "before date filtering, so the count includes pages that date filtering would also have removed) and "
                 f"{f['content_leak']} pages `content_leak` (stored text names the buyer or the outcome). The documented "
                 "case is the LDC page on HSL Compliance: published before the deal, but its current text already shows "
                 "the exit. Content-leak example: an Oxford Ionics article whose page furniture names the buyer (hit "
                 f"\"{oxford_hit}\"). Separately, as ordinary date filtering, {f['after_anchor']} pages were discarded "
                 "as published on or after the deal date (`after_anchor`).",
                 "Make publication-date gating, the modified-after check and the content-leak check standard in every "
                 "pipeline stage.",
                 "The checks are conservative and may exclude some clean pages; they cannot catch edits that leave no "
                 "trace in metadata or text.")
    L += finding(6, "The registry has gaps",
                 "Companies House cannot show who a new officer is in role terms, and PSC records can miss deals made "
                 "above the company.",
                 f"{f['officer_events_with_occupation']} of {f['officer_events']} officer events carry an occupation, so "
                 "a new CFO or chair cannot be detected from the registry. PSC can miss holding-company-level deals: "
                 "the Dains case in `docs/case_selection.md` (a majority stake changed hands while the operating "
                 "company's own PSC did not change).",
                 "Take readiness signals (new CFO or chair) from news, and check ownership at group level, not only "
                 "the operating company.",
                 "Based on the companies in this sample.")
    L += finding(7, "Extraction: quotes were verbatim; model choice is about error type, not cost",
                 "Both models quoted their evidence word for word; the cheaper model made the most damaging error.",
                 f"Verbatim-quote rate: Haiku {hk['verbatim_quote_rate']:.0%}, Sonnet {sn['verbatim_quote_rate']:.0%}. "
                 f"Precision / recall: Haiku {hk['precision']:.0%} / {hk['recall']:.0%}, Sonnet {sn['precision']:.0%} / "
                 f"{sn['recall']:.0%}; Sonnet after the two PRD-derived rules {ex['sonnet_after_prd_rules']['precision']:.0%} / "
                 f"{ex['sonnet_after_prd_rules']['recall']:.0%}. False direct-intent signals: Haiku "
                 f"{hk['false_direct_intent']}, Sonnet {sn['false_direct_intent']}. Cost (provisional estimate): Haiku "
                 f"${hk['cost_usd_provisional']:.4f}, Sonnet ${sn['cost_usd_provisional']:.4f}, a ratio of {ratio:.0f}×. "
                 f"One extraction error (Cytora's advisory board read as a governance change) produced "
                 f"{len(unconfirmed_wins)} ranking wins ("
                 + ", ".join(f"{c['pair_id']} {c['horizon']}" for c in unconfirmed_wins)
                 + ") that the verified-only diagnostic removes. Sources: `docs/extraction_eval.md`, "
                 "`data/processed/charts/extraction_compare.json`, `docs/scoring_results.md`.",
                 "Sonnet was chosen. At scale, use the cheap model for bulk documents and the stronger model only for "
                 "documents with possible intent language; keep the verbatim-quote check.",
                 f"Small sample ({ex['n_documents']} articles, {ex['n_gold_signals']} gold signals); gold labels were "
                 "AI-written and user-reviewed; costs are a provisional estimate.")
    L += finding(8, "Weight magnitudes did not matter on this sample",
                 "Setting every weight to plus or minus 1 changed no outcome.",
                 f"Sensitivity outcomes equal the full score's in {sens_same} of {n_comp} comparisons "
                 f"({fmtw(W['sensitivity'])}). Source: `docs/scoring_results.md`.",
                 "Do not tune weights on a sample like this; revisit once intent signals are present.",
                 "This is because intent, the heaviest term, never appeared; with intent present, weights would matter.")

    counts = h3["counts"]
    L += ["## Hypotheses (pre-registered in `docs/scoring.md`)", "",
          "- **H1 (a clock plus intent beats either alone and beats holding-only): untestable** on this sample.",
          f"- **H2 (PE-backed companies are the most predictable segment):** (a) simple verdict: **{h2['simple']}** "
          f"(full-score wins: PE {h2['wins']['PE']} of {h2['n']['PE']} comparisons, VC {h2['wins']['VC']} of "
          f"{h2['n']['VC']}). (b) labelled breakdown: PE wins {cats_text(h2['categories']['PE'])}; VC wins "
          f"{cats_text(h2['categories']['VC'])}; "
          f"clock-driven or other wins only: PE {h2['supportive']['PE']}/{h2['n']['PE']}, VC "
          f"{h2['supportive']['VC']}/{h2['n']['VC']}. Carve-outs: untestable (none in the sample).",
          f"- **H3 (useful signals at least 6 months early):** (a) simple verdict: **{h3['n_simple']} of {n_pairs} pairs** "
          f"support it. (b) labelled breakdown: clock-driven {counts['clock-driven']}, other {counts['other']}, weak "
          f"(debt-only) {counts['weak (debt-only)']}, no support {counts['no support']}."
          + (f" (a) and (b) differ for {', '.join(h3['disagree'])}, whose early win is debt-only." if h3["disagree"] else "")]
    for pid, x in h3["per_pair"].items():
        if x["fragile"]:
            other_early = [c for c in comps["full"] if c["pair_id"] == pid and c["horizon"] in ("12m", "6m")
                           and c["outcome"] == "win" and c["category"] == "unconfirmed-only"]
            L.append(f"  - **{pid}: technically supported, fragile.** Its {x['best']['horizon']} win meets the "
                     "pre-registered rule but is not a win under verified-only."
                     + "".join(f" Its {c['horizon']} win rests only on an unconfirmed extraction and is not counted."
                               for c in other_early))
    L += ["", "## What we'd build next (v1 recommendation)", "",
          "- **Clock-led scoring for PE-backed companies**, using registry ownership dates and sponsor announcements.",
          "- **Licensed news for intent**: free sources gave no intent signal before the last 3 months.",
          "- **Model routing**: a cheap model for bulk extraction, a stronger model only for documents with possible "
          "intent language, with deterministic quote, subject and taxonomy checks on every output.",
          "- **Leakage guards as standard**: publication-date gating, the modified-after check and the content-leak check.",
          "- **Validate on the 100-company pilot** and against Third Bridge's own request logs (evaluation only, never "
          "a model input).", "",
          "## Limitations", "",
          f"- {n_pairs} matched pairs ({len(PE_PAIRS)} PE-backed, {n_pairs - len(PE_PAIRS)} VC-backed); no carve-out; "
          "rough size matching.",
          "- Sparse evidence; missing evidence is never treated as absence of a signal.",
          "- \"No publicly observed transaction\" does not mean no deal happened.",
          "- PTSG and Xeinadin holding periods are an announcement-based proxy.",
          "- Correlated snapshots: results are per pair and hypothesis-generating, not validation; no claim of "
          "predictive performance."]
    return "\n".join(L) + "\n"


def cats_text(c: dict) -> str:
    return ", ".join(f"{k} {n}" for k, n in sorted(c.items())) or "none"


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def main() -> None:
    d = load_all()
    f = funnel(d)
    CHARTS.mkdir(parents=True, exist_ok=True)
    write_json(CHARTS / "pairs_scores.json", chart_pairs_scores(d))
    write_json(CHARTS / "evidence_funnel.json", chart_funnel(f))
    write_json(CHARTS / "signal_timeline.json", chart_timeline(d))
    FINDINGS.write_text(render(d, f))
    print(f"findings.md and {len(list(CHARTS.glob('*.json')))} chart files written")


if __name__ == "__main__":
    main()
