"""Step 7: point-in-time snapshots and features (pure functions, no I/O except load_sponsor_entries).

Every input is filtered to publication_date < prediction_date before anything else (rules.is_usable logic);
publication_date only gates usability and never replaces an event or entry date. Rules come from PRD definitions:
external_context never contributes (PRD §8: context only); the recently_acquired counter-signal is derived from the
sponsor entry, so LLM recently_acquired signals are ignored; only the sponsor entry sets the holding clock; the
deal's own ownership change (outcome events) is never used.
"""

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from pydantic import TypeAdapter

from deal_radar.rules import add_months, label_window, snapshot_dates
from deal_radar.schemas import Evidence, MatchedPair, RegistryEvent, Signal, SponsorEntry, Transaction

DIRECT_INTENT = {"advisers_appointed", "strategic_review", "exploring_options", "parent_non_core"}
READINESS = {"new_cfo_or_chair", "governance_change"}
CHARGE_EVENTS = {"charge_created", "charge_satisfied"}
HORIZONS = {12: "12m", 6: "6m", 3: "3m"}
HOLDING_BASIS = {"psc_notified": "psc_notified", "completion_stated": "completion_stated",
                 "announced_completion_not_confirmed": "announced_proxy"}


def usable(items: list, prediction_date: date) -> list:
    """Point-in-time filter: publication_date known and strictly before the prediction date."""
    return [i for i in items if i.publication_date is not None and i.publication_date < prediction_date]


def apply_prd_rules(signals: list[Signal]) -> list[Signal]:
    """Drop external_context (PRD §8: context only) and LLM recently_acquired (derived from the sponsor entry)."""
    return [s for s in signals if s.signal_class != "external_context"
            and not (s.extraction_method == "llm" and s.signal_type == "recently_acquired")]


def load_sponsor_entries(path: Path, evidence: list[Evidence], events: list[RegistryEvent],
                         pairs: list[MatchedPair], pe_company_ids: set[str]) -> dict[str, SponsorEntry]:
    """Read sponsor_entry.json and check every entry against its source record and the pair anchor."""
    entries = TypeAdapter(list[SponsorEntry]).validate_json(Path(path).read_text())
    ev_by_id = {e.evidence_id: e for e in evidence}
    re_by_id = {e.event_id: e for e in events}
    anchor = {}
    for p in pairs:
        anchor[p.deal_company_id] = anchor[p.control_company_id] = p.anchor_date
    if sorted(e.company_id for e in entries) != sorted(pe_company_ids):
        raise ValueError("sponsor_entry.json must have exactly one entry per PE-backed company")
    for e in entries:
        source = (ev_by_id if e.source_kind == "evidence" else re_by_id).get(e.source_id)
        if source is None or source.company_id != e.company_id:
            raise ValueError(f"{e.company_id}: source {e.source_id} not found")
        if source.publication_date != e.publication_date:
            raise ValueError(f"{e.company_id}: publication_date does not match its source")
        if e.source_kind == "registry_event" and (source.event_type != "psc_added" or source.event_date != e.entry_date):
            raise ValueError(f"{e.company_id}: a PSC entry_date must equal the psc_added event_date")
        if not e.entry_date < anchor[e.company_id]:
            raise ValueError(f"{e.company_id}: entry_date must be before the anchor")
    return {e.company_id: e for e in entries}


def count_financings(events: list[RegistryEvent]) -> int:
    """Count charge events, merging the same financing across group entities only.

    Key = (event_type, event_date, sorted lenders). Within one entity distinct charges are never merged, so the
    count for a key is the largest number of events with that key at any single entity. No lenders: never merged.
    """
    per_entity: dict[tuple, Counter] = defaultdict(Counter)
    unmergeable = 0
    for e in events:
        lenders = tuple(sorted(e.details.get("lenders") or []))
        if not lenders:
            unmergeable += 1
            continue
        per_entity[(e.event_type, e.event_date, lenders)][e.ch_number] += 1
    return unmergeable + sum(max(by_entity.values()) for by_entity in per_entity.values())


def recent(signals: list[Signal], prediction_date: date, months: int) -> tuple[list[Signal], str | None]:
    """Signals whose event_date (or publication_date as a flagged proxy) lies in [pd - months, pd)."""
    start, hits, proxy = add_months(prediction_date, -months), [], False
    for s in signals:
        when = s.event_date or s.publication_date
        if start <= when < prediction_date:
            hits.append(s)
            proxy |= s.event_date is None
    basis = None if not hits else ("publication_proxy" if proxy else "event_date")
    return hits, basis


def company_features(owner_type: str, prediction_date: date, sponsor: SponsorEntry | None,
                     evidence: list[Evidence], events: list[RegistryEvent], signals: list[Signal],
                     outcome_ids: set[str]) -> tuple[dict, dict]:
    """Features and provenance (feature -> ids used) for one company at one prediction date."""
    pd = prediction_date
    evidence = usable(evidence, pd)
    events = [e for e in usable(events, pd) if e.event_id not in outcome_ids]
    signals = apply_prd_rules(usable(signals, pd))
    f, prov = {}, {}

    sponsor_ok = (owner_type == "pe_backed" and sponsor is not None
                  and sponsor.publication_date < pd and sponsor.entry_date < pd)
    f["pe_holding_years"] = round((pd - sponsor.entry_date).days / 365.25, 2) if sponsor_ok else None
    f["recently_acquired"] = bool(sponsor_ok and add_months(pd, -24) <= sponsor.entry_date)
    f["holding_basis"] = HOLDING_BASIS[sponsor.entry_basis] if sponsor_ok else None
    prov["pe_holding_years"] = [sponsor.source_id] if sponsor_ok else []
    prov["recently_acquired"] = [sponsor.source_id] if f["recently_acquired"] else []

    year_ago = add_months(pd, -12)
    charges = [e for e in events if e.event_type in CHARGE_EVENTS and year_ago <= e.publication_date]
    f["debt_financings_12m"] = count_financings(charges)
    f["debt_event_12m"] = f["debt_financings_12m"] > 0
    prov["debt_financings_12m"] = [e.event_id for e in charges]

    intent = [s for s in signals if s.signal_type in DIRECT_INTENT and s.status in ("confirmed", "attributed")]
    f["intent_present"] = bool(intent)
    prov["intent_present"] = [s.signal_id for s in intent]

    readiness, f["readiness_date_basis"] = recent([s for s in signals if s.signal_type in READINESS], pd, 18)
    f["readiness_18m"] = bool(readiness)
    prov["readiness_18m"] = [s.signal_id for s in readiness]

    fundraise, f["fundraise_date_basis"] = recent([s for s in signals if s.signal_type == "large_recent_fundraise"], pd, 12)
    f["fundraise_12m"] = bool(fundraise)
    prov["fundraise_12m"] = [s.signal_id for s in fundraise]

    f["coverage_items"] = len(evidence) + len(events)
    prov["coverage_items"] = [e.evidence_id for e in evidence] + [e.event_id for e in events]
    return f, prov


def build_rows(pairs: list[MatchedPair], transactions: list[Transaction], owner_type: dict[str, str],
               sponsors: dict[str, SponsorEntry], evidence: list[Evidence], events: list[RegistryEvent],
               signals: list[Signal], outcome_ids: set[str]) -> list[dict]:
    """One row per pair x company x snapshot date (rules.snapshot_dates), labelled with rules.label_window."""
    rows = []
    for p in pairs:
        for cid, role in ((p.deal_company_id, "deal"), (p.control_company_id, "control")):
            txs = [t for t in transactions if t.company_id == cid]
            for months, pd in zip((12, 6, 3), snapshot_dates(p.anchor_date)):
                feats, prov = company_features(
                    owner_type[cid], pd, sponsors.get(cid),
                    [e for e in evidence if e.company_id == cid], [e for e in events if e.company_id == cid],
                    [s for s in signals if s.company_id == cid], outcome_ids)
                rows.append({"company_id": cid, "pair_id": p.pair_id, "role": role, "prediction_date": pd.isoformat(),
                             "horizon": HORIZONS[months], "label": label_window(txs, pd),
                             "features": feats, "provenance": prov})
    return rows


def late_clues(pair: MatchedPair, signals: list[Signal]) -> list[Signal]:
    """Reporting only (H3 lead time): signals of either company published in [latest snapshot date, anchor)."""
    start = snapshot_dates(pair.anchor_date)[-1]
    ids = {pair.deal_company_id, pair.control_company_id}
    return [s for s in apply_prd_rules(signals)
            if s.company_id in ids and s.publication_date is not None and start <= s.publication_date < pair.anchor_date]


def load_json_list(path: Path, model):
    return TypeAdapter(list[model]).validate_python(json.loads(Path(path).read_text()))
