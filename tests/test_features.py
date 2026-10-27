"""Step 7: point-in-time features, leakage tests and real-data checks."""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from deal_radar.cases import load_cases
from deal_radar.features import (
    apply_prd_rules,
    company_features,
    count_financings,
    late_clues,
    load_json_list,
    load_sponsor_entries,
)
from deal_radar.schemas import SIGNAL_CLASS_OF, Evidence, RegistryEvent, Signal, SponsorEntry

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "cases"
PROCESSED = ROOT / "data" / "processed"
PD = date(2024, 6, 1)


# --- synthetic fixtures ---------------------------------------------------------------------------

def sig(stype, pub=date(2024, 5, 1), event=None, status="confirmed", method="llm", sid=None):
    return Signal(signal_id=sid or f"s-{stype}-{pub}-{event}-{status}", company_id="c", evidence_id="e",
                  signal_class=SIGNAL_CLASS_OF[stype], signal_type=stype, event_date=event, publication_date=pub,
                  evidence_quote="q", status=status, source_url="u", extraction_method=method)


def ev(eid="ev-1", pub=date(2024, 5, 1)):
    return Evidence(evidence_id=eid, company_id="c", url="https://x", source_type="news", publication_date=pub,
                    retrieved_at=datetime(2026, 10, 27))


def charge(eid, ch="111", etype="charge_created", event=date(2024, 3, 1), pub=date(2024, 3, 5), lenders=("Bank A",), code=None):
    return RegistryEvent(event_id=eid, company_id="c", ch_number=ch, event_type=etype, event_date=event,
                         publication_date=pub, details={"charge_code": code or eid, "lenders": list(lenders)},
                         source_url="https://ch")


def sponsor(entry=date(2019, 3, 28), pub=date(2019, 7, 26), basis="psc_notified"):
    return SponsorEntry(company_id="c", sponsor="S", announced_date=None, entry_date=entry, entry_basis=basis,
                        source_kind="registry_event", source_id="psc-1", publication_date=pub)


def feats(pd=PD, owner="pe_backed", sp=None, evidence=(), events=(), signals=(), outcome=frozenset()):
    return company_features(owner, pd, sp, list(evidence), list(events), list(signals), set(outcome))


# --- point-in-time ----------------------------------------------------------------------------------

def test_evidence_published_on_the_prediction_date_is_not_used():
    f, prov = feats(evidence=[ev("ev-on", PD), ev("ev-before", date(2024, 5, 31))])
    assert f["coverage_items"] == 1 and prov["coverage_items"] == ["ev-before"]


def test_event_before_but_published_after_the_prediction_date_is_not_used():
    late = charge("ch-late", event=date(2024, 5, 1), pub=date(2024, 6, 2))
    f, prov = feats(events=[late], signals=[sig("exploring_options", pub=date(2024, 6, 2), event=date(2024, 5, 1))])
    assert not f["debt_event_12m"] and not f["intent_present"] and prov["debt_financings_12m"] == []


def test_sponsor_entry_published_after_prediction_date_gives_no_clock():
    f, _ = feats(sp=sponsor(entry=date(2020, 1, 1), pub=date(2024, 7, 1)))
    assert f["pe_holding_years"] is None and f["holding_basis"] is None and not f["recently_acquired"]


def test_psc_clock_is_gated_by_publication_but_measured_from_entry():
    sp = sponsor()  # entry 2019-03-28, published 2019-07-26
    assert feats(pd=date(2019, 7, 26), sp=sp)[0]["pe_holding_years"] is None
    f, _ = feats(pd=date(2019, 7, 27), sp=sp)
    assert f["pe_holding_years"] == round((date(2019, 7, 27) - date(2019, 3, 28)).days / 365.25, 2)
    assert f["holding_basis"] == "psc_notified"


def test_announced_entry_is_flagged_as_proxy():
    f, _ = feats(sp=sponsor(entry=date(2023, 1, 1), pub=date(2023, 1, 1), basis="announced_completion_not_confirmed"))
    assert f["holding_basis"] == "announced_proxy" and f["recently_acquired"]


def test_non_pe_company_has_no_clock():
    f, _ = feats(owner="vc_backed", sp=sponsor())
    assert f["pe_holding_years"] is None and f["holding_basis"] is None


# --- PRD-derived rules ------------------------------------------------------------------------------

def test_external_context_never_changes_a_feature():
    base = feats(sp=sponsor(), signals=[sig("governance_change")])
    extra = [sig(t) for t in ("peer_deals_in_sector", "active_buyers", "sector_consolidation")]
    assert feats(sp=sponsor(), signals=[sig("governance_change"), *extra]) == base


def test_llm_pe_holding_period_never_sets_the_clock():
    for s in (sig("pe_holding_period"), sig("pe_holding_period", event=date(2020, 1, 1))):
        f, _ = feats(owner="pe_backed", sp=None, signals=[s])
        assert f["pe_holding_years"] is None and not f["recently_acquired"]


def test_llm_recently_acquired_is_ignored():
    f, _ = feats(sp=sponsor(), signals=[sig("recently_acquired", event=date(2024, 1, 1))])
    assert not f["recently_acquired"]
    assert apply_prd_rules([sig("recently_acquired")]) == []
    registry_rule = sig("debt_charge_event", method="registry_rule")
    assert apply_prd_rules([registry_rule]) == [registry_rule]


def test_speculative_intent_is_excluded():
    assert not feats(signals=[sig("advisers_appointed", status="speculative")])[0]["intent_present"]
    assert feats(signals=[sig("advisers_appointed", status="attributed")])[0]["intent_present"]


def test_old_event_reported_recently_is_not_recent_readiness():
    old = sig("new_cfo_or_chair", pub=date(2024, 2, 7), event=date(2022, 1, 1))
    assert not feats(signals=[old])[0]["readiness_18m"]
    f, _ = feats(signals=[sig("governance_change", pub=date(2024, 2, 7), event=None)])
    assert f["readiness_18m"] and f["readiness_date_basis"] == "publication_proxy"
    f, _ = feats(signals=[sig("governance_change", pub=date(2024, 2, 7), event=date(2024, 1, 15))])
    assert f["readiness_date_basis"] == "event_date"


def test_fundraise_proxy_is_flagged():
    f, _ = feats(signals=[sig("large_recent_fundraise", pub=date(2024, 2, 7), event=None)])
    assert f["fundraise_12m"] and f["fundraise_date_basis"] == "publication_proxy"
    assert not feats(signals=[sig("large_recent_fundraise", pub=date(2024, 2, 7), event=date(2021, 1, 1))])[0]["fundraise_12m"]


# --- debt de-duplication -------------------------------------------------------------------------------

def test_same_financing_across_entities_counts_once():
    assert count_financings([charge("a", ch="111"), charge("b", ch="222"), charge("c", ch="333")]) == 1


def test_two_charges_at_one_entity_same_type_date_lender_count_twice():
    assert count_financings([charge("a", ch="111", code="1110001"), charge("b", ch="111", code="1110002")]) == 2
    both = [charge("a", ch="111"), charge("b", ch="111"), charge("c", ch="222"), charge("d", ch="222")]
    assert count_financings(both) == 2


def test_different_lender_or_date_or_no_lender_never_merges():
    assert count_financings([charge("a", ch="111"), charge("b", ch="222", lenders=("Bank B",))]) == 2
    assert count_financings([charge("a", ch="111"), charge("b", ch="222", event=date(2024, 3, 2))]) == 2
    assert count_financings([charge("a", ch="111", lenders=()), charge("b", ch="222", lenders=())]) == 2


def test_debt_window_is_12_months_by_publication():
    events = [charge("old", pub=date(2023, 5, 31)), charge("edge", pub=date(2023, 6, 1), event=date(2023, 6, 1))]
    f, prov = feats(events=events)
    assert f["debt_financings_12m"] == 1 and prov["debt_financings_12m"] == ["edge"]


def test_outcome_event_is_never_used_even_if_filed_before():
    outcome = RegistryEvent(event_id="psc-deal", company_id="c", ch_number="111", event_type="psc_added",
                            event_date=date(2024, 1, 1), publication_date=date(2024, 1, 2), details={}, source_url="u")
    f, prov = feats(events=[outcome], outcome={"psc-deal"})
    assert f["coverage_items"] == 0 and "psc-deal" not in json.dumps(prov)


# --- real data ------------------------------------------------------------------------------------------

def real_rows():
    path = PROCESSED / "features.json"
    if not path.exists():
        pytest.skip("features.json not generated yet")
    return json.loads(path.read_text())


def real_inputs():
    evidence = load_json_list(PROCESSED / "evidence.json", Evidence)
    events = [RegistryEvent.model_validate(e) for e in json.loads((PROCESSED / "registry_events.json").read_text())["events"]]
    llm = load_json_list(PROCESSED / "llm_signals_sonnet.json", Signal)
    registry_signals = load_json_list(PROCESSED / "registry_signals.json", Signal)
    return evidence, events, llm, registry_signals


def test_exactly_36_rows_and_expected_labels():
    rows = real_rows()
    assert len(rows) == 36
    for r in rows:
        assert r["label"] == ("positive" if r["role"] == "deal" else "no_publicly_observed_transaction")
    _, _, pairs = load_cases(CASES)
    assert {(r["pair_id"], r["horizon"]) for r in rows} == {(p.pair_id, h) for p in pairs for h in ("12m", "6m", "3m")}
    assert "true negative" not in (ROOT / "docs" / "features.md").read_text().lower()


def test_every_provenance_id_was_published_before_its_prediction_date():
    evidence, events, llm, _ = real_inputs()
    published = {e.evidence_id: e.publication_date for e in evidence}
    published |= {e.event_id: e.publication_date for e in events}
    published |= {s.signal_id: s.publication_date for s in llm}
    n = 0
    for r in real_rows():
        pd = date.fromisoformat(r["prediction_date"])
        for ids in r["provenance"].values():
            for i in ids:
                assert published[i] is not None and published[i] < pd, (r["company_id"], r["prediction_date"], i)
                n += 1
    assert n > 0


def test_holding_basis_present_for_all_four_pe_companies():
    rows = real_rows()
    expected = {"hsl_compliance": "psc_notified", "aab": "psc_notified", "ptsg": "announced_proxy", "xeinadin": "announced_proxy"}
    for r in rows:
        f = r["features"]
        if r["company_id"] in expected:
            assert f["pe_holding_years"] is not None and f["holding_basis"] == expected[r["company_id"]]
        else:
            assert f["pe_holding_years"] is None and f["holding_basis"] is None
    assert "announced_proxy" in (ROOT / "docs" / "features.md").read_text()


def test_real_hsl_clock_gated_by_filing_and_measured_from_notified_date():
    evidence, events, _, _ = real_inputs()
    _, _, pairs = load_cases(CASES)
    sponsors = load_sponsor_entries(CASES / "sponsor_entry.json", evidence, events, pairs,
                                    {"hsl_compliance", "ptsg", "aab", "xeinadin"})
    hsl = sponsors["hsl_compliance"]
    assert (hsl.entry_date, hsl.publication_date) == (date(2019, 3, 28), date(2019, 7, 26))
    assert feats(pd=date(2019, 7, 26), sp=hsl)[0]["pe_holding_years"] is None
    assert feats(pd=date(2019, 7, 27), sp=hsl)[0]["pe_holding_years"] == round(121 / 365.25, 2)


def test_sponsor_entries_validate_and_sources_exist(tmp_path):
    evidence, events, _, _ = real_inputs()
    _, _, pairs = load_cases(CASES)
    sponsors = load_sponsor_entries(CASES / "sponsor_entry.json", evidence, events, pairs,
                                    {"hsl_compliance", "ptsg", "aab", "xeinadin"})
    assert sponsors["ptsg"].sponsor.startswith("Warburg Pincus")
    assert "minority" in sponsors["xeinadin"].note
    for field, value in (("source_id", "does-not-exist"), ("publication_date", "2019-07-25"), ("entry_date", "2019-03-29")):
        raw = json.loads((CASES / "sponsor_entry.json").read_text())
        raw[0][field] = value  # hsl_compliance (PSC source)
        bad = tmp_path / f"bad_{field}.json"
        bad.write_text(json.dumps(raw))
        with pytest.raises(ValueError):
            load_sponsor_entries(bad, evidence, events, pairs, {"hsl_compliance", "ptsg", "aab", "xeinadin"})


def test_outcome_events_exist_and_never_appear_in_provenance():
    _, events, _, _ = real_inputs()
    ids = {e.event_id for e in events}
    outcome = json.loads((CASES / "outcome_events.json").read_text())
    assert len(outcome) == 8 and all(o["event_id"] in ids for o in outcome)
    used = json.dumps([r["provenance"] for r in real_rows()])
    assert not any(o["event_id"] in used for o in outcome)


def test_late_clues_never_appear_in_features():
    _, _, llm, registry_signals = real_inputs()
    _, _, pairs = load_cases(CASES)
    used = {i for r in real_rows() for ids in r["provenance"].values() for i in ids}
    clues = [s for p in pairs for s in late_clues(p, llm + registry_signals)]
    assert clues
    for s in clues:
        assert s.signal_id not in used and s.evidence_id not in used
    xein = {(s.signal_type, s.status, s.publication_date) for s in clues if s.company_id == "xeinadin"}
    assert {("exploring_options", "attributed", date(2025, 5, 26)), ("advisers_appointed", "attributed", date(2025, 5, 26))} <= xein
