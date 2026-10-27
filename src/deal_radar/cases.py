"""Load and check the matched-pair case files in data/cases/ (PRD section 17)."""

from pathlib import Path
from typing import get_args

from pydantic import TypeAdapter

from deal_radar.schemas import Company, LabelSourceType, MatchedPair, Transaction

ALL_LABEL_SOURCES = set(get_args(LabelSourceType))


def load_cases(cases_dir: Path) -> tuple[list[Company], list[Transaction], list[MatchedPair]]:
    """Read companies.json, transactions.json and pairs.json and validate them against the schemas."""
    cases_dir = Path(cases_dir)

    def load(name, model):
        return TypeAdapter(list[model]).validate_json((cases_dir / name).read_text())

    return (
        load("companies.json", Company),
        load("transactions.json", Transaction),
        load("pairs.json", MatchedPair),
    )


def check_pairs(
    companies: list[Company], transactions: list[Transaction], pairs: list[MatchedPair]
) -> list[str]:
    """Check each pair against the case rules. Raises ValueError on a hard failure; returns warnings."""
    by_id = {c.company_id: c for c in companies}
    warnings = []
    for p in pairs:
        if p.deal_company_id == p.control_company_id:
            raise ValueError(f"{p.pair_id}: deal and control are the same company")
        for cid in (p.deal_company_id, p.control_company_id):
            if cid not in by_id:
                raise ValueError(f"{p.pair_id}: unknown company_id {cid}")

        deal_dates = {
            t.announcement_date
            for t in transactions
            if t.company_id == p.deal_company_id and t.transaction_type == "change_of_control"
        }
        if p.anchor_date not in deal_dates:
            raise ValueError(f"{p.pair_id}: anchor_date does not match a deal change_of_control announcement")

        if p.control_status == "verified" and not ALL_LABEL_SOURCES <= set(p.sources_checked):
            missing = sorted(ALL_LABEL_SOURCES - set(p.sources_checked))
            raise ValueError(f"{p.pair_id}: verified control is missing source checks {missing}")

        for t in transactions:
            if (
                t.company_id == p.control_company_id
                and p.check_period_start <= t.announcement_date <= p.check_period_end
            ):
                raise ValueError(f"{p.pair_id}: control has a transaction inside the check period")

        deal_owner = by_id[p.deal_company_id].owner_type
        control_owner = by_id[p.control_company_id].owner_type
        if deal_owner != control_owner:
            warnings.append(f"{p.pair_id}: owner types differ ({deal_owner} vs {control_owner})")
    return warnings
