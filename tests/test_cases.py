import json
from datetime import date
from pathlib import Path

import pytest

from deal_radar.cases import check_entities, check_pairs, load_cases, load_entities
from deal_radar.rules import add_months, usable_pairs
from deal_radar.schemas import Company, EntityGroup

REAL_CASES = Path(__file__).resolve().parents[1] / "data" / "cases"
ANCHOR = date(2025, 3, 31)
ALL_SOURCES = ["pe_or_acquirer_press_release", "rns", "cma_notice", "companies_house_psc"]


def company(company_id, owner_type="pe_backed"):
    return {"company_id": company_id, "name": f"Fakeco {company_id} Ltd", "owner_type": owner_type}


def transaction(company_id, announcement_date, transaction_type="change_of_control"):
    return {
        "company_id": company_id,
        "transaction_type": transaction_type,
        "announcement_date": announcement_date.isoformat(),
        "description": "synthetic",
        "source_urls": ["https://example.org/fake"],
        "source_types": ["pe_or_acquirer_press_release"],
    }


def pair(deal="alpha", control="beta", anchor=ANCHOR, status="verified", sources=ALL_SOURCES):
    return {
        "pair_id": "p1",
        "deal_company_id": deal,
        "control_company_id": control,
        "anchor_date": anchor.isoformat(),
        "control_status": status,
        "sources_checked": sources,
        "check_period_start": add_months(anchor, -12).isoformat(),
        "check_period_end": add_months(anchor, 12).isoformat(),
    }


def write_cases(tmp_path, companies, transactions, pairs):
    for name, rows in [("companies.json", companies), ("transactions.json", transactions), ("pairs.json", pairs)]:
        (tmp_path / name).write_text(json.dumps(rows))
    return load_cases(tmp_path)


def good_cases():
    return [company("alpha"), company("beta")], [transaction("alpha", ANCHOR)], [pair()]


def test_happy_path(tmp_path):
    companies, transactions, pairs = write_cases(tmp_path, *good_cases())
    assert check_pairs(companies, transactions, pairs) == []
    assert usable_pairs(pairs) == pairs


def test_load_rejects_invalid_record(tmp_path):
    companies, transactions, _ = good_cases()
    with pytest.raises(ValueError):
        write_cases(tmp_path, companies, transactions, [pair(anchor=date(2025, 12, 1))])


def test_deal_equals_control_rejected(tmp_path):
    companies, transactions, _ = good_cases()
    loaded = write_cases(tmp_path, companies, transactions, [pair(control="alpha")])
    with pytest.raises(ValueError, match="same company"):
        check_pairs(*loaded)


def test_unknown_company_rejected(tmp_path):
    companies, transactions, _ = good_cases()
    loaded = write_cases(tmp_path, companies, transactions, [pair(control="gamma")])
    with pytest.raises(ValueError, match="unknown company_id"):
        check_pairs(*loaded)


def test_anchor_must_match_deal_announcement(tmp_path):
    companies, _, pairs = good_cases()
    loaded = write_cases(tmp_path, companies, [transaction("alpha", date(2025, 4, 1))], pairs)
    with pytest.raises(ValueError, match="anchor_date"):
        check_pairs(*loaded)


def test_anchor_must_match_change_of_control_not_ipo(tmp_path):
    companies, _, pairs = good_cases()
    loaded = write_cases(tmp_path, companies, [transaction("alpha", ANCHOR, "ipo")], pairs)
    with pytest.raises(ValueError, match="anchor_date"):
        check_pairs(*loaded)


def test_verified_requires_all_four_sources(tmp_path):
    companies, transactions, _ = good_cases()
    loaded = write_cases(tmp_path, companies, transactions, [pair(sources=ALL_SOURCES[:3])])
    with pytest.raises(ValueError, match="missing source checks"):
        check_pairs(*loaded)


def test_unresolved_with_partial_sources_allowed_but_not_usable(tmp_path):
    companies, transactions, _ = good_cases()
    loaded = write_cases(tmp_path, companies, transactions, [pair(status="unresolved", sources=["rns"])])
    assert check_pairs(*loaded) == []
    assert usable_pairs(loaded[2]) == []


@pytest.mark.parametrize("months", [-12, -1, 1, 12])
def test_control_transaction_in_check_period_rejected(tmp_path, months):
    companies, transactions, pairs = good_cases()
    transactions.append(transaction("beta", add_months(ANCHOR, months), "ipo"))
    loaded = write_cases(tmp_path, companies, transactions, pairs)
    with pytest.raises(ValueError, match="inside the check period"):
        check_pairs(*loaded)


def test_control_transaction_outside_check_period_allowed(tmp_path):
    companies, transactions, pairs = good_cases()
    transactions.append(transaction("beta", date(2026, 4, 1)))
    loaded = write_cases(tmp_path, companies, transactions, pairs)
    assert check_pairs(*loaded) == []


def test_owner_type_mismatch_warns(tmp_path):
    _, transactions, pairs = good_cases()
    loaded = write_cases(tmp_path, [company("alpha"), company("beta", "vc_backed")], transactions, pairs)
    assert check_pairs(*loaded) == ["p1: owner types differ (pe_backed vs vc_backed)"]


def test_real_case_files_validate():
    if not all((REAL_CASES / n).exists() for n in ("companies.json", "transactions.json", "pairs.json")):
        pytest.skip("data/cases/*.json not present yet")
    companies, transactions, pairs = load_cases(REAL_CASES)
    check_pairs(companies, transactions, pairs)
    assert pairs, "pairs.json is empty"


# --- entities.json -----------------------------------------------------------------------------------

def make_company(company_id, number):
    return Company(company_id=company_id, name=f"Fakeco {company_id} Ltd", companies_house_number=number, owner_type="pe_backed")


def test_entity_group_rejects_duplicates_and_empty():
    with pytest.raises(ValueError):
        EntityGroup(company_id="a", ch_numbers=["1", "1"])
    with pytest.raises(ValueError):
        EntityGroup(company_id="a", ch_numbers=[])


def test_check_entities_happy_path():
    check_entities(
        [make_company("alpha", "100"), make_company("beta", "200")],
        [EntityGroup(company_id="alpha", ch_numbers=["100", "101"]), EntityGroup(company_id="beta", ch_numbers=["200"])],
    )


@pytest.mark.parametrize(
    "groups, message",
    [
        ([EntityGroup(company_id="alpha", ch_numbers=["101"])], "own CH number"),
        ([EntityGroup(company_id="beta", ch_numbers=["200"])], "no entity group"),
        ([EntityGroup(company_id="alpha", ch_numbers=["100"]), EntityGroup(company_id="beta", ch_numbers=["100"])], "is in both"),
        ([EntityGroup(company_id="alpha", ch_numbers=["100"]), EntityGroup(company_id="ghost", ch_numbers=["900"])], "unknown companies"),
    ],
)
def test_check_entities_failures(groups, message):
    with pytest.raises(ValueError, match=message):
        check_entities([make_company("alpha", "100")], groups)


def test_real_entities_file_covers_every_company():
    if not (REAL_CASES / "entities.json").exists():
        pytest.skip("data/cases/entities.json not present yet")
    companies, _, _ = load_cases(REAL_CASES)
    check_entities(companies, load_entities(REAL_CASES))
