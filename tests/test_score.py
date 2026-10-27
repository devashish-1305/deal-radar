"""Step 8: pre-registered score, bands, comparisons and real-data traceability."""

import json
import subprocess
from pathlib import Path

import pytest

from deal_radar.cases import load_cases
from deal_radar.features import late_clues, load_json_list
from deal_radar.schemas import Signal
from deal_radar.score import band, classify_win, compare_pairs, confidence, contributions, load_config, score

ROOT = Path(__file__).resolve().parents[1]
PHASE_A_COMMIT = "f9ce1fd"  # latest pre-registration commit ("step 8a.1"); 98865d2 had the same JSON block
CONFIG = load_config((ROOT / "docs" / "scoring.md").read_text())


def row(company="d", role="deal", pair="P1", horizon="12m", years=None, debt=False, intent=False, ready=False,
        acq=False, fund=False, coverage=20, news=True, prov=None):
    p = {"pe_holding_years": ["psc-1"] if years is not None else [], "recently_acquired": ["psc-1"] if acq else [],
         "debt_financings_12m": ["ch-1"] if debt else [], "intent_present": ["sig-intent"] if intent else [],
         "readiness_18m": ["sig-ready"] if ready else [], "fundraise_12m": ["sig-fund"] if fund else [],
         "coverage_items": (["ev-1"] if news else []) + ["re-1"]}
    p.update(prov or {})
    return {"company_id": company, "role": role, "pair_id": pair, "horizon": horizon, "prediction_date": "2024-01-01",
            "label": "positive",
            "features": {"pe_holding_years": years, "recently_acquired": acq, "debt_event_12m": debt,
                         "debt_financings_12m": int(debt), "intent_present": intent, "readiness_18m": ready,
                         "fundraise_12m": fund, "coverage_items": coverage},
            "provenance": p}


# --- pre-registration -----------------------------------------------------------------------------------

def test_weights_match_the_pre_registered_commit():
    shown = subprocess.run(["git", "show", f"{PHASE_A_COMMIT}:docs/scoring.md"], cwd=ROOT, capture_output=True, text=True)
    if shown.returncode != 0:
        pytest.skip("git history unavailable")
    assert load_config(shown.stdout) == CONFIG
    assert CONFIG["weights"] == {"intent_present": 3, "clock": 2, "debt_event_12m": 1, "readiness_18m": 1,
                                 "recently_acquired": -2, "fundraise_12m": -1}
    assert CONFIG["sensitivity_weights"] == {"intent_present": 1, "clock": 1, "debt_event_12m": 1, "readiness_18m": 1,
                                             "recently_acquired": -1, "fundraise_12m": -1}


# --- arithmetic -------------------------------------------------------------------------------------------

def test_score_arithmetic_and_clock_cap():
    assert score(row(years=2.5), CONFIG, set())[0] == 1.0
    assert score(row(years=7.0), CONFIG, set())[0] == 2.0  # capped at 5 years
    assert score(row(years=None), CONFIG, set())[0] == 0.0
    full = row(years=5, debt=True, intent=True, ready=True, acq=True, fund=True)
    assert score(full, CONFIG, set())[0] == 3 + 2 + 1 + 1 - 2 - 1
    assert score(full, CONFIG, set(), "sensitivity")[0] == 1 + 1 + 1 + 1 - 1 - 1
    assert score(full, CONFIG, set(), "holding_only")[0] == 2
    assert score(full, CONFIG, set(), "full_minus_clock")[0] == 3 + 1 + 1 - 2 - 1


def test_contributions_carry_provenance_and_gold_flags():
    c = {x["term"]: x for x in contributions(row(years=1, debt=True, ready=True, intent=True), CONFIG, {"sig-ready"})}
    assert c["clock"]["ids"] == ["psc-1"] and c["clock"]["gold_confirmed"] == "n/a"
    assert c["debt_event_12m"]["gold_confirmed"] == "n/a"
    assert c["readiness_18m"]["gold_confirmed"] is True and c["intent_present"]["gold_confirmed"] is False


def test_band_boundaries():
    assert band(3, CONFIG) == "High" and band(2.999, CONFIG) == "Medium"
    assert band(1.5, CONFIG) == "Medium" and band(1.499, CONFIG) == "Low"


def test_confidence_bands_and_zero_news_cap():
    assert confidence(row(coverage=50), CONFIG) == "High"
    assert confidence(row(coverage=49), CONFIG) == "Medium"
    assert confidence(row(coverage=15), CONFIG) == "Medium"
    assert confidence(row(coverage=14), CONFIG) == "Low"
    assert confidence(row(coverage=120, news=False), CONFIG) == "Medium"
    assert confidence(row(coverage=10, news=False), CONFIG) == "Low"


def test_ties_wins_losses():
    rows = [row("d", "deal", horizon="12m", debt=True), row("c", "control", horizon="12m", debt=True),
            row("d", "deal", horizon="6m", years=4), row("c", "control", horizon="6m", years=3),
            row("d", "deal", horizon="3m"), row("c", "control", horizon="3m", debt=True)]
    out = {c["horizon"]: c for c in compare_pairs(rows, CONFIG, set(), "full")}
    assert out["12m"]["outcome"] == "tie" and out["6m"]["outcome"] == "win" and out["3m"]["outcome"] == "loss"
    assert out["6m"]["category"] == "clock-driven" and out["12m"]["category"] is None


def test_win_categories():
    def cat(deal, control, confirmed=frozenset()):
        return classify_win(contributions(deal, CONFIG, set(confirmed)), contributions(control, CONFIG, set(confirmed)))[0]
    assert cat(row(debt=True), row()) == "weak (debt-only)"
    assert cat(row(ready=True), row()) == "unconfirmed-only"
    assert cat(row(ready=True), row(), {"sig-ready"}) == "other"
    assert cat(row(years=3, debt=True), row(years=2)) == "clock-driven"


def test_verified_only_removes_only_unconfirmed_llm_terms():
    r = row(years=3, debt=True, ready=True, intent=True, fund=True)
    full = {c["term"] for c in contributions(r, CONFIG, {"sig-intent"})}
    verified = {c["term"] for c in contributions(r, CONFIG, {"sig-intent"}, "verified_only")}
    assert full - verified == {"readiness_18m", "fundraise_12m"}
    assert {"clock", "debt_event_12m", "intent_present"} <= verified


# --- real data --------------------------------------------------------------------------------------------

def real():
    scores, features = ROOT / "data" / "processed" / "scores.json", ROOT / "data" / "processed" / "features.json"
    if not scores.exists():
        pytest.skip("scores.json not generated yet")
    return json.loads(scores.read_text()), json.loads(features.read_text())


def test_real_36_rows_and_contributions_trace_to_step7_provenance():
    from deal_radar.score import PROVENANCE_KEY
    scores, features = real()
    assert len(scores) == 36
    feat = {(r["company_id"], r["prediction_date"]): r for r in features}
    for s in scores:
        f = feat[(s["company_id"], s["prediction_date"])]
        for c in s["contributions"]:
            assert c["ids"] and c["ids"] == f["provenance"][PROVENANCE_KEY[c["term"]]]
        assert s["score"] == round(sum(c["value"] for c in s["contributions"]), 6)


def test_real_scores_recompute_with_the_pre_registered_config():
    from deal_radar.extract import match
    scores, features = real()
    gold = json.loads((ROOT / "data" / "cases" / "gold_signals.json").read_text())["signals"]
    sonnet = load_json_list(ROOT / "data" / "processed" / "llm_signals_sonnet.json", Signal)
    confirmed = {p.signal_id for _, p in match(gold, sonnet)["pairs"]}
    feat = {(r["company_id"], r["prediction_date"]): r for r in features}
    for s in scores:
        f = feat[(s["company_id"], s["prediction_date"])]
        assert score(f, CONFIG, confirmed)[0] == s["score"]
        for variant, value in s["variant_scores"].items():
            assert score(f, CONFIG, confirmed, variant)[0] == value


def test_late_clues_are_never_scored():
    scores, _ = real()
    _, _, pairs = load_cases(ROOT / "data" / "cases")
    processed = ROOT / "data" / "processed"
    signals = load_json_list(processed / "llm_signals_sonnet.json", Signal) + \
        load_json_list(processed / "registry_signals.json", Signal)
    used = {i for s in scores for c in s["contributions"] for i in c["ids"]}
    clues = [c for p in pairs for c in late_clues(p, signals)]
    assert clues
    assert not ({c.signal_id for c in clues} | {c.evidence_id for c in clues}) & used


def test_no_probability_or_percentage_in_outputs():
    scores, _ = real()
    text = json.dumps(scores).lower()
    for bad in ("prob", "percent", "likelihood_pct", "%"):
        assert bad not in text
    results = (ROOT / "docs" / "scoring_results.md").read_text().lower()
    assert "probability" not in results.replace("never a probability", "")
    assert "%" not in results
