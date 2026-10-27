"""Step 9: findings, chart data, one-command rerun (determinism, no network, fresh-clone mode)."""

import hashlib
import json
import socket
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_findings  # noqa: E402
import run_all  # noqa: E402
import run_extraction  # noqa: E402

from deal_radar.extract import match  # noqa: E402
from deal_radar.schemas import Signal  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
CHARTS = PROCESSED / "charts"
FINDINGS = (ROOT / "docs" / "findings.md")
STEP8_FINAL = "a7ed826"  # gate-8-approved scoring_results.md


def read_json(path):
    return json.loads(Path(path).read_text())


def outcomes_from_scores(variant: str) -> Counter:
    """W/T/L re-derived directly from scores.json (independent of the comparison code)."""
    rows = read_json(PROCESSED / "scores.json")
    val = {(r["pair_id"], r["horizon"], r["role"]): (r["score"] if variant == "full" else r["variant_scores"][variant])
           for r in rows}
    c = Counter()
    for (pid, h, role), d in val.items():
        if role == "deal":
            diff = d - val[(pid, h, "control")]
            c["tie" if abs(diff) <= 1e-9 else "win" if diff > 0 else "loss"] += 1
    return c


# --- key figures -------------------------------------------------------------------------------------------

def test_findings_contain_rederived_scoring_figures():
    text = FINDINGS.read_text()
    expected = {"full": (11, 4, 3), "holding_only": (6, 12, 0), "verified_only": (9, 6, 3)}
    for variant, (w, t, l) in expected.items():
        c = outcomes_from_scores(variant)
        assert (c["win"], c["tie"], c["loss"]) == (w, t, l)
    assert "Full score: 11 wins / 4 ties / 3 losses" in text
    assert "Holding-only benchmark: 6 wins / 12 ties / 0 losses" in text
    assert "produced 2 ranking wins (P4 12m, P4 6m) that the verified-only diagnostic removes" in text  # 11 -> 9


def test_findings_extraction_figures_match_independent_recompute():
    gold = read_json(ROOT / "data" / "cases" / "gold_signals.json")["signals"]
    ex = read_json(CHARTS / "extraction_compare.json")
    for short, (tp, fp, fn) in {"haiku": (17, 9, 1), "sonnet": (16, 6, 2)}.items():
        m = match(gold, [Signal.model_validate(s) for s in read_json(PROCESSED / f"llm_signals_{short}.json")])
        assert (m["tp"], len(m["fp"]), len(m["fn"])) == (tp, fp, fn)
        assert (ex["models"][short]["tp"], ex["models"][short]["fp"], ex["models"][short]["fn"]) == (tp, fp, fn)
        assert ex["models"][short]["verbatim_quote_rate"] == 1.0
    text = FINDINGS.read_text()
    assert "Verbatim-quote rate: Haiku 100%, Sonnet 100%" in text
    assert "Haiku 65% / 94%, Sonnet 73% / 89%" in text and "84% / 89%" in text
    ratio = ex["models"]["sonnet"]["cost_usd_provisional"] / ex["models"]["haiku"]["cost_usd_provisional"]
    assert f"a ratio of {ratio:.0f}×" in text
    assert "False direct-intent signals: Haiku 1, Sonnet 0" in text
    assert "provisional estimate" in text and "Small sample (16 articles" in text


def test_findings_evidence_counts_match_sources():
    evidence = read_json(PROCESSED / "evidence.json")
    queries = read_json(ROOT / "data" / "cases" / "evidence_queries.json")["queries"]
    events = read_json(PROCESSED / "registry_events.json")["events"]
    text = FINDINGS.read_text()
    assert f"{sum(q['result_count'] for q in queries)} search results" in text
    assert f"({len({r['url'] for q in queries for r in q['results']})} unique URLs)" in text
    assert f"{len(evidence)} kept" in text
    funnel = read_json(CHARTS / "evidence_funnel.json")
    assert funnel["opened"]["split"][2]["count"] == len(evidence)
    assert sum(s["count"] for s in funnel["opened"]["split"]) == funnel["opened"]["count"]
    assert funnel["registry"][0]["count"] == len(events)
    assert funnel["registry"][2]["count"] == sum(e["publication_date"] is None for e in events)
    assert "no unique matching filing" in funnel["registry"][2]["label"]


def test_findings_hypotheses_wording():
    text = FINDINGS.read_text()
    assert "untestable** on this sample" in text and "H1" in text
    assert "(a) simple verdict" in text and "(b) labelled breakdown" in text
    assert "P4: technically supported, fragile." in text
    assert "Its 6m win rests only on an unconfirmed extraction and is not counted." in text
    assert text.count("announcement-based proxy") >= 2 and "hypothesis-generating, not validation" in text


def test_no_likelihood_probability_language():
    text = FINDINGS.read_text()
    lower = text.lower()
    for bad in ("probability of", "likely to", "chance of", "predicts", "accuracy of"):
        assert bad not in lower
    for line in text.splitlines():
        if "%" in line:
            assert "Precision" in line or "Verbatim-quote rate" in line, line


# --- generator round-trip and charts ---------------------------------------------------------------------------

def test_findings_md_is_reproduced_exactly_by_its_generator():
    d = build_findings.load_all()
    assert build_findings.render(d, build_findings.funnel(d)) == FINDINGS.read_text()


def test_chart_files_validate_and_match_sources():
    pairs = read_json(CHARTS / "pairs_scores.json")
    scores = {(r["pair_id"], r["horizon"], r["role"]): r for r in read_json(PROCESSED / "scores.json")}
    assert len(pairs) == 18
    for p in pairs:
        assert set(p) == {"pair_id", "horizon", "deal", "control", "full", "holding_only"}
        assert p["full"]["deal"] == scores[(p["pair_id"], p["horizon"], "deal")]["score"]
        assert p["full"]["control"] == scores[(p["pair_id"], p["horizon"], "control")]["score"]
        assert p["holding_only"]["deal"] == scores[(p["pair_id"], p["horizon"], "deal")]["variant_scores"]["holding_only"]
        assert p["full"]["outcome"] in ("win", "tie", "loss")
    timeline = read_json(CHARTS / "signal_timeline.json")
    assert len(timeline) == 6 and all(set(c["horizons"]) == {"12m", "6m", "3m"} for t in timeline for c in t["companies"])
    xein = next(c for t in timeline for c in t["companies"] if c["company_id"] == "xeinadin")
    assert {"exploring_options", "advisers_appointed"} <= set(xein["late_window"])
    assert not any("intent_present" in v for t in timeline for c in t["companies"] for v in c["horizons"].values())
    ex = read_json(CHARTS / "extraction_compare.json")
    assert set(ex["models"]) == {"haiku", "sonnet"}
    for m in ex["models"].values():
        assert {"precision", "recall", "verbatim_quote_rate", "cost_usd_provisional", "false_direct_intent"} <= set(m)


def test_step8_scoring_results_preserved_exactly():
    shown = subprocess.run(["git", "show", f"{STEP8_FINAL}:docs/scoring_results.md"], cwd=ROOT,
                           capture_output=True, text=True)
    if shown.returncode != 0:
        pytest.skip("git history unavailable")
    assert (ROOT / "docs" / "scoring_results.md").read_text() == shown.stdout
    d = build_findings.load_all()
    from deal_radar.score import hypothesis_verdicts
    v = hypothesis_verdicts(d["rows"], d["comparisons"], [p.pair_id for p in d["pairs"]], {"P1", "P6"})
    assert v["H1"]["testable"] is False
    assert v["H2"]["simple"] == "not contradicted" and v["H2"]["wins"] == {"PE": 5, "VC": 6}
    assert v["H3"]["n_simple"] == 4
    assert v["H3"]["counts"] == {"clock-driven": 2, "other": 1, "weak (debt-only)": 1, "no support": 2}
    assert [p for p, x in v["H3"]["per_pair"].items() if x["fragile"]] == ["P4"]


# --- one-command rerun ---------------------------------------------------------------------------------------------

def digest() -> dict:
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in run_all.OUTPUTS}


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted during run_all")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def test_run_all_committed_mode_is_deterministic_offline_and_reproduces_outputs(no_network, monkeypatch, tmp_path):
    """Fresh-clone simulation: no LLM cache and no raw articles. Never skipped."""
    monkeypatch.setattr(run_extraction, "LLM_CACHE", tmp_path / "no-llm-cache")
    monkeypatch.setattr(run_extraction, "ARTICLES", tmp_path / "no-articles")
    before = digest()
    assert run_all.main() == "committed"
    first = digest()
    assert run_all.main() == "committed"
    assert digest() == first == before


def test_run_all_cache_mode_equals_committed_mode(no_network):
    if not run_extraction.LLM_CACHE.exists():
        pytest.skip("no local LLM cache (committed mode is covered by the test above)")
    committed = digest()
    assert run_all.main() == "cache"
    assert digest() == committed


def test_usable_counts_use_one_rule_for_news_and_registry():
    from deal_radar.cases import load_cases
    from deal_radar.rules import is_usable
    from deal_radar.schemas import Evidence, RegistryEvent
    _, _, pairs = load_cases(ROOT / "data" / "cases")
    anchor = {}
    for p in pairs:
        anchor[p.deal_company_id] = anchor[p.control_company_id] = p.anchor_date
    evidence = [Evidence.model_validate(e) for e in read_json(PROCESSED / "evidence.json")]
    events = [RegistryEvent.model_validate(e) for e in read_json(PROCESSED / "registry_events.json")["events"]]
    news = sum(is_usable(e, anchor[e.company_id]) for e in evidence)
    registry = sum(is_usable(e, anchor[e.company_id]) for e in events)
    f = build_findings.funnel(build_findings.load_all())
    assert (f["usable_dated"], f["registry_usable_before_anchor"]) == (news, registry)
    text = FINDINGS.read_text()
    assert build_findings.USABLE_RULE in text
    assert f"({news} usable dated articles vs {registry} usable registry events)" in text


def test_leakage_counts_are_single_reasons_from_the_log():
    log = (ROOT / "docs" / "evidence_log.md").read_text()
    f = build_findings.funnel(build_findings.load_all())
    assert f["modified_after_anchor"] == log.count("**discarded: modified_after_anchor**")
    assert f["after_anchor"] == log.count("**discarded: after_anchor**")
    text = FINDINGS.read_text()
    assert f"{f['modified_after_anchor']} pages `modified_after_anchor`" in text
    assert f"{f['content_leak']} pages `content_leak`" in text
    assert f"{f['after_anchor']} pages were discarded as published on or after the deal date (`after_anchor`)" in text
