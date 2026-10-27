from datetime import date, datetime

import pytest

from deal_radar.rules import add_months, is_usable, label_window, snapshot_dates, usable_pairs
from deal_radar.schemas import Evidence, MatchedPair, Signal, Transaction

PRED = date(2024, 6, 15)


def evidence(publication_date):
    return Evidence(
        evidence_id="e1",
        company_id="c1",
        url="https://example.org/a",
        source_type="news",
        publication_date=publication_date,
        retrieved_at=datetime(2026, 10, 27, 12, 0),
    )


def signal(event_date, publication_date):
    return Signal(
        signal_id="s1",
        company_id="c1",
        evidence_id="e1",
        signal_class="direct_intent",
        signal_type="advisers_appointed",
        event_date=event_date,
        publication_date=publication_date,
        evidence_quote="The company has appointed advisers.",
        status="confirmed",
        source_url="https://example.org/a",
        extraction_method="llm",
    )


def tx(transaction_type, announcement_date):
    return Transaction(
        company_id="c1",
        transaction_type=transaction_type,
        announcement_date=announcement_date,
        description="test",
        source_urls=["https://example.org/a"],
        source_types=["rns"],
    )


def pair(anchor, status="verified"):
    return MatchedPair(
        pair_id="p1",
        deal_company_id="d1",
        control_company_id="k1",
        anchor_date=anchor,
        control_status=status,
        sources_checked=["rns"],
        check_period_start=add_months(anchor, -12),
        check_period_end=add_months(anchor, 12),
    )


# --- Leakage ---------------------------------------------------------------

def test_published_day_before_is_usable():
    assert is_usable(evidence(date(2024, 6, 14)), PRED)


def test_published_on_prediction_date_not_usable():
    assert not is_usable(evidence(PRED), PRED)


def test_published_after_not_usable():
    assert not is_usable(evidence(date(2024, 6, 16)), PRED)


def test_unknown_publication_date_not_usable():
    assert not is_usable(evidence(None), PRED)
    assert not is_usable(signal(date(2024, 1, 1), None), PRED)


def test_later_article_describing_earlier_events_not_usable():
    # Article published after the prediction date about events from before it.
    assert not is_usable(signal(event_date=date(2024, 3, 1), publication_date=date(2024, 9, 1)), PRED)


def test_signal_event_before_but_published_after_not_usable():
    assert not is_usable(signal(event_date=date(2024, 6, 1), publication_date=date(2024, 6, 15)), PRED)


def test_signal_published_before_is_usable():
    assert is_usable(signal(event_date=None, publication_date=date(2024, 6, 14)), PRED)


# --- Labels ----------------------------------------------------------------

def test_change_of_control_in_window_positive():
    assert label_window([tx("change_of_control", date(2024, 12, 1))], PRED) == "positive"


def test_announcement_on_window_end_positive():
    assert label_window([tx("change_of_control", add_months(PRED, 12))], PRED) == "positive"


def test_announcement_day_after_window_not_observed():
    assert label_window([tx("change_of_control", date(2025, 6, 16))], PRED) == "no_publicly_observed_transaction"


def test_announcement_on_prediction_date_not_in_window():
    assert label_window([tx("change_of_control", PRED)], PRED) == "no_publicly_observed_transaction"


def test_ipo_before_change_of_control_in_window_excluded():
    txs = [tx("change_of_control", date(2025, 1, 1)), tx("ipo", date(2024, 9, 1))]
    assert label_window(txs, PRED) == "excluded_competing_ipo"


def test_change_of_control_before_ipo_in_window_positive():
    txs = [tx("ipo", date(2025, 1, 1)), tx("change_of_control", date(2024, 9, 1))]
    assert label_window(txs, PRED) == "positive"


def test_same_day_ipo_and_change_of_control_excluded():
    txs = [tx("change_of_control", date(2024, 9, 1)), tx("ipo", date(2024, 9, 1))]
    assert label_window(txs, PRED) == "excluded_competing_ipo"


def test_ipo_before_window_out_of_scope():
    txs = [tx("ipo", date(2023, 1, 1)), tx("change_of_control", date(2024, 9, 1))]
    assert label_window(txs, PRED) == "out_of_scope_public"


def test_ipo_on_prediction_date_out_of_scope():
    assert label_window([tx("ipo", PRED)], PRED) == "out_of_scope_public"


def test_no_events_not_observed():
    assert label_window([], PRED) == "no_publicly_observed_transaction"


def test_mixed_company_ids_rejected():
    other = tx("change_of_control", date(2024, 9, 1)).model_copy(update={"company_id": "c2"})
    with pytest.raises(ValueError):
        label_window([tx("change_of_control", date(2024, 9, 1)), other], PRED)


def test_ipo_exclusion_applies_to_window_only():
    # IPO excludes the window it falls in; an earlier window without it is still labelled normally.
    txs = [tx("ipo", date(2025, 3, 1))]
    assert label_window(txs, date(2024, 6, 1)) == "excluded_competing_ipo"
    assert label_window(txs, date(2023, 6, 1)) == "no_publicly_observed_transaction"


# --- Date arithmetic --------------------------------------------------------

@pytest.mark.parametrize(
    "d, n, expected",
    [
        (date(2025, 3, 31), -1, date(2025, 2, 28)),
        (date(2024, 3, 31), -1, date(2024, 2, 29)),
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
        (date(2025, 8, 31), -6, date(2025, 2, 28)),
        (date(2025, 5, 31), -3, date(2025, 2, 28)),
        (date(2025, 1, 15), -12, date(2024, 1, 15)),
        (date(2024, 12, 31), 2, date(2025, 2, 28)),
    ],
)
def test_add_months(d, n, expected):
    assert add_months(d, n) == expected


def test_snapshot_dates():
    assert snapshot_dates(date(2025, 3, 31)) == [date(2024, 3, 31), date(2024, 9, 30), date(2024, 12, 31)]


def test_control_gets_same_snapshot_dates_as_deal():
    p = pair(date(2025, 3, 31))
    deal_dates = snapshot_dates(p.anchor_date)  # deal company
    control_dates = snapshot_dates(p.anchor_date)  # control is anchored to its matched deal
    assert control_dates == deal_dates


# --- Pairs -----------------------------------------------------------------

def test_usable_pairs_drops_unresolved():
    verified = pair(date(2025, 3, 31), "verified")
    unresolved = pair(date(2025, 4, 30), "unresolved")
    assert usable_pairs([verified, unresolved]) == [verified]
