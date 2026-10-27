"""Fetch Companies House data, normalise it into registry events and signals, and write coverage.

Run from the repo root:  PYTHONPATH=src .venv/bin/python scripts/fetch_registry.py
Prints counts only, never the API key. Raw responses are cached in data/raw/ (git-ignored).
"""

import json
from collections import Counter
from datetime import date
from pathlib import Path

from deal_radar.cases import check_entities, load_cases, load_entities
from deal_radar.companies_house import api_key, fetch_company
from deal_radar.registry import build_signals, coverage, normalise

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "cases"
RAW = ROOT / "data" / "raw" / "companies_house"
OUT = ROOT / "data" / "processed"
SNAPSHOT_CUTOFF = date(2023, 1, 1)


def dump(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=1, default=str) + "\n")


def main() -> None:
    companies, _, _ = load_cases(CASES)
    groups = load_entities(CASES)
    check_entities(companies, groups)
    key = api_key()

    events, ambiguous, signals, cover = [], [], [], {}
    for group in groups:
        raw_by_number, company_events = {}, []
        for number in group.ch_numbers:
            cached = fetch_company(number, RAW, key=key)
            raw = {name: cached[name]["items"] for name in ("officers", "filing_history", "charges", "psc")}
            raw_by_number[number] = raw
            e, a = normalise(group.company_id, number, raw)
            company_events += e
            ambiguous += a
        company_signals = build_signals(company_events)
        events += company_events
        signals += company_signals
        cover[group.company_id] = coverage(company_events, raw_by_number)
        print(f"{group.company_id}: {len(group.ch_numbers)} entities, {len(company_events)} events, "
              f"{len(company_signals)} signals, "
              f"{sum(e.publication_date is None for e in company_events)} without publication date")

    events.sort(key=lambda e: (e.company_id, e.ch_number, e.event_date or date.min, e.event_type, e.event_id))
    ambiguous.sort(key=lambda a: (a.company_id, a.ch_number, a.event_date or date.min, a.event_id))
    signals.sort(key=lambda s: s.signal_id)
    if len({e.event_id for e in events}) != len(events):
        raise ValueError("duplicate event_id")

    OUT.mkdir(parents=True, exist_ok=True)
    dump(OUT / "registry_events.json", {
        "events": [e.model_dump(mode="json") for e in events],
        "ambiguous_matches": [a.model_dump(mode="json") for a in ambiguous],
    })
    dump(OUT / "registry_signals.json", [s.model_dump(mode="json") for s in signals])
    dump(OUT / "coverage.json", cover)

    recent = sum(
        1 for a in ambiguous
        if (a.event_date and a.event_date >= SNAPSHOT_CUTOFF) or any(d >= SNAPSHOT_CUTOFF for d in a.candidate_filing_dates)
    )
    print(f"events by type: {dict(Counter(e.event_type for e in events))}")
    print(f"signals by type: {dict(Counter(s.signal_type for s in signals))}")
    print(f"publication_date None: {sum(e.publication_date is None for e in events)} "
          f"(ambiguous_matches: {len(ambiguous)}, on/after {SNAPSHOT_CUTOFF}: {recent})")


if __name__ == "__main__":
    main()
