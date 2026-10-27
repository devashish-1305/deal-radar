from datetime import date

import pytest
from pydantic import ValidationError

from deal_radar.rules import add_months
from deal_radar.schemas import Company, MatchedPair, Signal, Snapshot, Transaction


def make_signal(**overrides):
    fields = dict(
        signal_id="s1",
        company_id="c1",
        evidence_id="e1",
        signal_class="direct_intent",
        signal_type="advisers_appointed",
        event_date=None,
        publication_date=date(2024, 1, 1),
        evidence_quote="The company has appointed advisers.",
        status="attributed",
        source_url="https://example.org/a",
        extraction_method="llm",
    )
    fields.update(overrides)
    return Signal(**fields)


def make_pair(anchor, **overrides):
    fields = dict(
        pair_id="p1",
        deal_company_id="d1",
        control_company_id="k1",
        anchor_date=anchor,
        control_status="verified",
        sources_checked=["rns"],
        check_period_start=add_months(anchor, -12),
        check_period_end=add_months(anchor, 12),
    )
    fields.update(overrides)
    return MatchedPair(**fields)


def make_tx(source_types, source_urls=("https://example.org/a",)):
    return Transaction(
        company_id="c1",
        transaction_type="change_of_control",
        announcement_date=date(2025, 3, 1),
        description="test",
        source_urls=list(source_urls),
        source_types=source_types,
    )


def test_company_valid_and_bad_owner_type():
    Company(company_id="c1", name="X Ltd", owner_type="pe_backed")
    with pytest.raises(ValidationError):
        Company(company_id="c1", name="X Ltd", owner_type="hedge_fund")


def test_psc_only_transaction_rejected():
    with pytest.raises(ValidationError):
        make_tx(["companies_house_psc"])


def test_psc_with_other_source_accepted():
    assert make_tx(["companies_house_psc", "rns"]).source_types == ["companies_house_psc", "rns"]


def test_transaction_requires_source_urls():
    with pytest.raises(ValidationError):
        make_tx(["rns"], source_urls=())


def test_signal_type_class_mismatch_rejected():
    with pytest.raises(ValidationError):
        make_signal(signal_class="readiness", signal_type="advisers_appointed")


def test_signal_type_outside_prd_rejected():
    with pytest.raises(ValidationError):
        make_signal(signal_type="job_posting")


def test_quote_25_words_accepted():
    assert make_signal(evidence_quote=" ".join(["word"] * 25))


def test_quote_over_25_words_rejected():
    with pytest.raises(ValidationError):
        make_signal(evidence_quote=" ".join(["word"] * 26))


@pytest.mark.parametrize("anchor", [date(2024, 12, 31), date(2025, 10, 1)])
def test_anchor_outside_jan_sep_2025_rejected(anchor):
    with pytest.raises(ValidationError):
        make_pair(anchor)


@pytest.mark.parametrize("anchor", [date(2025, 1, 1), date(2025, 9, 30)])
def test_anchor_at_bounds_accepted(anchor):
    assert make_pair(anchor).anchor_date == anchor


def test_wrong_check_period_rejected():
    with pytest.raises(ValidationError):
        make_pair(date(2025, 3, 31), check_period_start=date(2024, 4, 1))


def test_snapshot_window_end_must_be_12_months():
    Snapshot(company_id="c1", prediction_date=date(2024, 2, 29), window_end=date(2025, 2, 28))
    with pytest.raises(ValidationError):
        Snapshot(company_id="c1", prediction_date=date(2024, 2, 29), window_end=date(2025, 3, 1))


def test_evidence_tags_default_empty_and_restricted():
    from datetime import datetime

    from deal_radar.schemas import Evidence

    base = dict(evidence_id="e", company_id="c", url="https://x", source_type="news",
                publication_date=None, retrieved_at=datetime(2026, 10, 27))
    assert Evidence(**base).tags == []
    assert Evidence(**base, tags=["late", "ownership_history"]).tags == ["late", "ownership_history"]
    with pytest.raises(ValidationError):
        Evidence(**base, tags=["rumour"])
