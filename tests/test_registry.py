import json
from datetime import date
from pathlib import Path

import pytest

from deal_radar.registry import (
    CFO_CHAIR_KEYWORDS,
    APPOINT_TYPES,
    build_signals,
    coverage,
    match_filing,
    norm_name,
    normalise,
)
from deal_radar.rules import is_usable
from deal_radar.schemas import AmbiguousMatch, RegistryEvent, Signal

FIXTURES = Path(__file__).parent / "fixtures" / "companies_house"
PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())["items"]


@pytest.fixture(scope="module")
def raw():
    return {name: load(name) for name in ("officers", "filing_history", "charges", "psc")}


@pytest.fixture(scope="module")
def result(raw):
    return normalise("fakeco", "99999999", raw)


@pytest.fixture(scope="module")
def events(result):
    return result[0]


@pytest.fixture(scope="module")
def ambiguous(result):
    return result[1]


def one(events, event_type, name=None, code=None):
    found = [
        e for e in events
        if e.event_type == event_type
        and (name is None or e.details.get("name") == name)
        and (code is None or e.details.get("charge_code") == code)
    ]
    assert len(found) == 1, found
    return found[0]


def reason(ambiguous, event):
    return next(a for a in ambiguous if a.event_id == event.event_id)


# --- names ---------------------------------------------------------------------------------

def test_norm_name_ignores_order_case_punctuation_and_titles():
    assert norm_name("SMITH, John Michael") == norm_name("Mr John Michael Smith")
    assert norm_name("WIENER, Aeneas, Dr") == norm_name("Aeneas Wiener")


def test_norm_name_keeps_similar_names_apart():
    assert norm_name("SMITH, John") != norm_name("SMYTH, John")
    assert norm_name("BROWN, Anna") != norm_name("BROWN, Anna Lee")


def test_empty_identity_never_matches():
    filings = [{"type": "AP01", "date": "2021-01-02", "description_values": {}}]
    assert match_filing(filings, APPOINT_TYPES, "officer_name", None) == []
    assert match_filing(filings, APPOINT_TYPES, "officer_name", "") == []


# --- publication date: leakage-critical --------------------------------------------------------

def test_publication_comes_from_filing_not_event_date(events):
    e = one(events, "officer_appointed", "SMITH, John")
    assert e.event_date == date(2024, 3, 1)
    assert e.publication_date == date(2024, 5, 10)
    assert e.details["filing_id"] == "tid-smith"


def test_no_matching_filing_gives_none_and_is_listed(events, ambiguous):
    e = one(events, "officer_appointed", "JONES, Pat")
    assert e.publication_date is None
    assert reason(ambiguous, e).reason == "no_candidate"


def test_two_filings_same_day_for_different_officers_match_their_own(events):
    assert one(events, "officer_appointed", "MANN, Alice").details["filing_id"] == "tid-alice"
    assert one(events, "officer_appointed", "HILL, Bob").details["filing_id"] == "tid-bob"


def test_two_identical_candidates_give_none_and_are_listed(events, ambiguous):
    e = one(events, "officer_appointed", "TWIN, Sam")
    assert e.publication_date is None
    a = reason(ambiguous, e)
    assert a.reason == "multiple_candidates"
    assert sorted(a.candidate_filing_ids) == ["tid-twin1", "tid-twin2"]
    assert a.candidate_filing_dates == [date(2023, 5, 20), date(2023, 5, 20)]


def test_similar_officer_names_are_never_cross_matched(events, ambiguous):
    # John Smith has a filing; John Smyth (same appointment date) has none and must not borrow it.
    smyth = one(events, "officer_appointed", "SMYTH, John")
    assert smyth.publication_date is None
    assert reason(ambiguous, smyth).reason == "no_candidate"
    assert one(events, "officer_appointed", "SMITH, John").details["filing_id"] == "tid-smith"
    # Anna Brown / Anna Lee Brown each get their own filing.
    assert one(events, "officer_appointed", "BROWN, Anna").details["filing_id"] == "tid-abrown"
    assert one(events, "officer_appointed", "BROWN, Anna Lee").details["filing_id"] == "tid-aleebrown"


def test_similar_psc_names_are_never_cross_matched(events, ambiguous):
    assert one(events, "psc_added", "Mr Zed Alpha").details["filing_id"] == "tid-psc-alpha"
    assert one(events, "psc_added", "Mr Zed Alpine").details["filing_id"] == "tid-psc-alpine"
    alp = one(events, "psc_added", "Mr Zed Alp")
    assert alp.publication_date is None
    assert reason(ambiguous, alp).reason == "no_candidate"


def test_filing_with_a_different_stated_date_is_not_a_candidate(raw):
    kwargs = {"date_field": "appointment_date"}
    filings = raw["filing_history"]
    assert match_filing(filings, APPOINT_TYPES, "officer_name", "John Smith", event_date="2024-03-02", **kwargs) == []
    assert len(match_filing(filings, APPOINT_TYPES, "officer_name", "John Smith", event_date="2024-03-01", **kwargs)) == 1


def test_resignation_matched_to_termination_filing(events):
    assert one(events, "officer_appointed", "ROE, Rae").publication_date == date(2020, 1, 10)
    resigned = one(events, "officer_resigned", "ROE, Rae")
    assert resigned.event_date == date(2024, 4, 1)
    assert resigned.publication_date == date(2024, 4, 12)


def test_llp_prefixed_filings_match(events):
    assert one(events, "officer_appointed", "LEE, Kim").publication_date == date(2023, 2, 15)
    assert one(events, "officer_resigned", "LEE, Kim").publication_date == date(2024, 2, 20)
    assert one(events, "charge_satisfied", code="999999990003").publication_date == date(2024, 10, 5)
    assert one(events, "psc_added", "Fake Holdings Limited").publication_date == date(2023, 8, 9)


def test_charge_created_publication_is_delivered_on(events):
    e = one(events, "charge_created", code="999999990001")
    assert e.event_date == date(2023, 3, 1)
    assert e.publication_date == date(2023, 3, 9)


def test_charge_satisfied_matches_mr04_and_old_charge_without_code_is_none(events, ambiguous):
    assert one(events, "charge_satisfied", code="999999990002").publication_date == date(2024, 9, 15)
    old = [e for e in events if e.event_type == "charge_satisfied" and e.details["charge_code"] is None]
    assert len(old) == 1 and old[0].publication_date is None
    assert reason(ambiguous, old[0]).reason == "no_candidate"


def test_psc_added_and_ceased(events, ambiguous):
    added = one(events, "psc_added", "Mr Old Owner")
    assert added.publication_date is None  # initial PSC, no PSC01 filing
    assert reason(ambiguous, added).reason == "no_candidate"
    ceased = one(events, "psc_ceased", "Mr Old Owner")
    assert (ceased.event_date, ceased.publication_date) == (date(2023, 9, 1), date(2023, 9, 12))


def test_accounts_and_auditor_events_come_from_filings(events):
    accounts = sorted((e for e in events if e.event_type == "accounts_filed"), key=lambda e: e.event_date)
    assert [(e.event_date, e.publication_date, e.details["accounts_type"]) for e in accounts] == [
        (date(2023, 3, 31), date(2023, 12, 1), "full"),
        (date(2024, 3, 31), date(2024, 12, 1), "small"),
    ]
    auditor = one(events, "auditor_resigned")
    assert (auditor.event_date, auditor.publication_date) == (None, date(2023, 11, 4))


def test_only_directors_and_llp_members_are_normalised(events):
    names = {e.details.get("name") for e in events}
    assert "CLERK, Sec" not in names  # secretary
    assert "LEE, Kim" in names  # LLP member


def test_every_unusable_event_is_in_ambiguous_matches(events, ambiguous):
    assert {a.event_id for a in ambiguous} == {e.event_id for e in events if e.publication_date is None}
    assert len({e.event_id for e in events}) == len(events)


def test_source_urls_are_public_ch_pages(events):
    assert one(events, "officer_appointed", "SMITH, John").source_url.endswith("/company/99999999/officers")
    assert one(events, "charge_created", code="999999990001").source_url.endswith("/company/99999999/charges")
    assert all(e.source_url.startswith("https://find-and-update.company-information.service.gov.uk/") for e in events)


# --- signals -----------------------------------------------------------------------------------

def test_cfo_chair_keyword_mapping_is_case_insensitive_and_ignores_plain_directors(events):
    signals = [s for s in build_signals(events) if s.signal_type == "new_cfo_or_chair"]
    by_id = {e.event_id: e for e in events}
    assert sorted(by_id[s.evidence_id].details["name"] for s in signals) == ["CHAIRS, Eve", "FOURIE, Chris"]
    # DAVIES, Dana is a "Company Director": no signal. A bare director is never inferred to be a CFO/chair.
    assert all(by_id[s.evidence_id].details["name"] != "DAVIES, Dana" for s in signals)


def test_keywords_live_in_one_constant():
    assert set(CFO_CHAIR_KEYWORDS) == {
        "cfo", "chief financial officer", "finance director", "chair", "chairman", "chairwoman"
    }


def test_charge_events_produce_debt_signals(events):
    signals = [s for s in build_signals(events) if s.signal_type == "debt_charge_event"]
    assert len(signals) == 7  # 4 charges created + 3 satisfied
    assert all(s.signal_class == "counter_signal" or s.signal_class == "timing_clock" for s in signals)
    created = next(s for s in signals if s.event_date == date(2023, 3, 1))
    assert "Fake Bank plc" in created.evidence_quote


def test_psc_accounts_and_auditor_events_produce_no_signals(events):
    signalled = {s.evidence_id for s in build_signals(events)}
    blocked = {e.event_id for e in events if e.event_type in ("psc_added", "psc_ceased", "accounts_filed", "auditor_resigned")}
    assert blocked and not (signalled & blocked)


def test_signals_validate_against_schema(events):
    signals = build_signals(events)
    assert signals
    for s in signals:
        Signal.model_validate(s.model_dump())
        assert s.extraction_method == "registry_rule" and s.status == "confirmed"
        assert s.source_url and len(s.evidence_quote.split()) <= 25


def test_long_lender_name_is_capped_at_25_words():
    raw = {
        "officers": [], "filing_history": [], "psc": [],
        "charges": [{"charge_code": "X1", "created_on": "2024-01-01", "delivered_on": "2024-01-02",
                     "persons_entitled": [{"name": " ".join(["Lender"] * 40)}]}],
    }
    events, _ = normalise("fakeco", "99999999", raw)
    (signal,) = build_signals(events)
    assert len(signal.evidence_quote.split()) == 25


# --- leakage on signals ----------------------------------------------------------------------

def test_signal_event_before_prediction_date_but_published_after_is_unusable(events):
    by_id = {e.event_id: e for e in events}
    signals = build_signals(events)
    cfo = next(s for s in signals if by_id[s.evidence_id].details.get("name") == "FOURIE, Chris")
    assert cfo.event_date == date(2024, 6, 1) and cfo.publication_date == date(2024, 6, 10)
    assert not is_usable(cfo, date(2024, 6, 5))  # event is earlier, but the filing was not public yet
    assert not is_usable(cfo, date(2024, 6, 10))  # published ON the prediction date
    assert is_usable(cfo, date(2024, 6, 11))


def test_signal_without_publication_date_is_never_usable(events):
    signals = build_signals(events)
    unmatched = [s for s in signals if s.publication_date is None]
    assert unmatched  # the old charge satisfied without a charge code
    assert not any(is_usable(s, date(2030, 1, 1)) for s in unmatched)


# --- coverage ------------------------------------------------------------------------------------

def test_coverage(events, raw):
    c = coverage(events, {"99999999": {name: raw[name] for name in raw}})
    assert c["registry_events"] == len(events)
    assert c["latest_accounts_type"] == "small"
    assert c["has_officers"] and c["has_charges"] and c["has_psc"]


def test_coverage_of_empty_company():
    empty = {"officers": [], "filing_history": [], "charges": [], "psc": []}
    c = coverage([], {"1": empty})
    assert c == {"entities": ["1"], "registry_events": 0, "latest_accounts_type": None,
                 "has_officers": False, "has_charges": False, "has_psc": False}


# --- real data (skipped until the script has been run) ---------------------------------------------

def test_real_registry_signals_validate():
    path = PROCESSED / "registry_signals.json"
    if not path.exists():
        pytest.skip("registry_signals.json not generated yet")
    for item in json.loads(path.read_text()):
        signal = Signal.model_validate(item)
        assert signal.source_url


def test_real_registry_events_validate():
    path = PROCESSED / "registry_events.json"
    if not path.exists():
        pytest.skip("registry_events.json not generated yet")
    payload = json.loads(path.read_text())
    events = [RegistryEvent.model_validate(e) for e in payload["events"]]
    ambiguous = [AmbiguousMatch.model_validate(a) for a in payload["ambiguous_matches"]]
    assert len({e.event_id for e in events}) == len(events)
    assert {a.event_id for a in ambiguous} == {e.event_id for e in events if e.publication_date is None}
