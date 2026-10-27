"""Normalise cached Companies House JSON into dated registry events and rule-based signals.

Pure functions, no I/O. publication_date is the date an item became public on Companies House:
the date of the one matching filing (or the charge's delivered_on). It is never taken from event_date.
When a filing cannot be matched to exactly one candidate, publication_date stays None (unusable under
rules.is_usable) and the event is listed in ambiguous_matches.
"""

import hashlib
import re
from collections.abc import Callable
from typing import Any

from deal_radar.schemas import SIGNAL_CLASS_OF, AmbiguousMatch, RegistryEvent, Signal

CH_SITE = "https://find-and-update.company-information.service.gov.uk"

# Matched against officer occupation / role text, case-insensitive. A plain "director" never matches.
CFO_CHAIR_KEYWORDS = ("cfo", "chief financial officer", "finance director", "chair", "chairman", "chairwoman")

OFFICER_ROLES = {
    "director", "corporate-director", "nominee-director", "corporate-nominee-director",
    "llp-member", "llp-designated-member", "corporate-llp-member", "corporate-llp-designated-member",
}
# Filing-type families. The LL-prefixed types are the LLP equivalents of the company filings.
APPOINT_TYPES = {"AP01", "AP02", "LLAP01", "LLAP02"}
RESIGN_TYPES = {"TM01", "LLTM01"}
CHARGE_SATISFIED_TYPES = {"MR04", "LLMR04"}
PSC_ADDED_TYPES = {"PSC01", "PSC02", "PSC03", "LLPSC01", "LLPSC02", "LLPSC03"}
PSC_CEASED_TYPES = {"PSC07", "LLPSC07"}

TITLES = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir", "lord", "lady", "dame", "rev", "hon"}
MAX_QUOTE_WORDS = 25


def norm_name(name: str | None) -> tuple[str, ...]:
    """Lower-case, strip punctuation and titles, sort tokens: 'SMITH, John M' == 'Mr John M Smith'."""
    tokens = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split()
    return tuple(sorted(t for t in tokens if t not in TITLES))


def norm_code(code: str | None) -> str:
    return (code or "").strip()


def match_filing(
    filings: list[dict],
    types: set[str],
    field: str,
    identity: str | None,
    norm: Callable[[str | None], Any] = norm_name,
    date_field: str | None = None,
    event_date: str | None = None,
) -> list[dict]:
    """Candidate filings: type in family, same identity, and same event date when the filing states one.

    An empty identity never matches anything, so two blank names are never "equal".
    """
    key = norm(identity)
    if not key:
        return []
    candidates = []
    for f in filings:
        if f.get("type") not in types or not f.get("date"):
            continue
        values = f.get("description_values") or {}
        if norm(values.get(field)) != key:
            continue
        stated = values.get(date_field) if date_field else None
        if stated and event_date and stated != event_date:
            continue
        candidates.append(f)
    return candidates


def _event_id(ch_number: str, event_type: str, event_date: str | None, key: str) -> str:
    digest = hashlib.sha1("|".join([ch_number, event_type, event_date or "", key]).encode()).hexdigest()[:10]
    return f"{ch_number}-{event_type}-{digest}"


def normalise(
    company_id: str, ch_number: str, raw: dict[str, list[dict]]
) -> tuple[list[RegistryEvent], list[AmbiguousMatch]]:
    """raw holds the cached item lists: officers, filing_history, charges, psc."""
    events: list[RegistryEvent] = []
    ambiguous: list[AmbiguousMatch] = []
    filings = raw["filing_history"]

    def add(event_type, event_date, key, details, section, publication, candidates=None):
        """candidates=None: publication is already known. Otherwise exactly one candidate is required."""
        if candidates is not None:
            if len(candidates) == 1:
                publication = candidates[0]["date"]
                details = {**details, "filing_id": candidates[0].get("transaction_id")}
            else:
                publication = None
        event = RegistryEvent(
            event_id=_event_id(ch_number, event_type, event_date, key),
            company_id=company_id,
            ch_number=ch_number,
            event_type=event_type,
            event_date=event_date,
            publication_date=publication,
            details=details,
            source_url=f"{CH_SITE}/company/{ch_number}/{section}",
        )
        events.append(event)
        if publication is None:
            found = candidates or []
            ambiguous.append(AmbiguousMatch(
                event_id=event.event_id,
                company_id=company_id,
                ch_number=ch_number,
                event_type=event_type,
                event_date=event.event_date,
                reason="multiple_candidates" if len(found) > 1 else "no_candidate",
                candidate_filing_ids=[f["transaction_id"] for f in found if f.get("transaction_id")],
                candidate_filing_dates=[f["date"] for f in found],
            ))

    for o in raw["officers"]:
        if o.get("officer_role") not in OFFICER_ROLES:
            continue
        details = {"name": o.get("name"), "role": o.get("officer_role"), "occupation": o.get("occupation")}
        for event_type, day, types, date_field in (
            ("officer_appointed", o.get("appointed_on"), APPOINT_TYPES, "appointment_date"),
            ("officer_resigned", o.get("resigned_on"), RESIGN_TYPES, "termination_date"),
        ):
            if day:
                candidates = match_filing(filings, types, "officer_name", o.get("name"), norm_name, date_field, day)
                add(event_type, day, o.get("name") or "", details, "officers", None, candidates)

    for c in raw["charges"]:
        code = c.get("charge_code")
        key = code or c.get("links", {}).get("self", "")
        lenders = [p["name"] for p in c.get("persons_entitled", []) if p.get("name")]
        details = {"charge_code": code, "lenders": lenders, "status": c.get("status")}
        if c.get("created_on"):
            add("charge_created", c["created_on"], key, details, "charges", c.get("delivered_on"))
        if c.get("satisfied_on"):
            candidates = match_filing(filings, CHARGE_SATISFIED_TYPES, "charge_number", code, norm_code)
            add("charge_satisfied", c["satisfied_on"], key, details, "charges", None, candidates)

    for p in raw["psc"]:
        details = {"name": p.get("name"), "kind": p.get("kind")}
        for event_type, day, types, date_field in (
            ("psc_added", p.get("notified_on"), PSC_ADDED_TYPES, "notification_date"),
            ("psc_ceased", p.get("ceased_on"), PSC_CEASED_TYPES, "cessation_date"),
        ):
            if day:
                candidates = match_filing(filings, types, "psc_name", p.get("name"), norm_name, date_field, day)
                add(event_type, day, p.get("name") or "", details, "persons-with-significant-control", None, candidates)

    for f in filings:
        if not f.get("date"):
            continue
        values = f.get("description_values") or {}
        if f.get("type") == "AA":
            accounts_type = re.sub(r"^accounts-with-accounts-type-", "", f.get("description") or "")
            details = {"accounts_type": accounts_type, "filing_id": f.get("transaction_id")}
            add("accounts_filed", values.get("made_up_date"), f.get("transaction_id") or f["date"], details,
                "filing-history", f["date"])
        elif f.get("category") == "auditors" and "resignation" in (f.get("description") or ""):
            details = {"filing_id": f.get("transaction_id")}
            add("auditor_resigned", None, f.get("transaction_id") or f["date"], details, "filing-history", f["date"])

    return events, ambiguous


def _cap_words(text: str, limit: int = MAX_QUOTE_WORDS) -> str:
    return " ".join(text.split()[:limit])


def _is_cfo_or_chair(details: dict) -> bool:
    text = f"{details.get('occupation') or ''} {details.get('role') or ''}".lower()
    return any(keyword in text for keyword in CFO_CHAIR_KEYWORDS)


def build_signals(events: list[RegistryEvent]) -> list[Signal]:
    """Deterministic signals: CFO/chair appointments and charge events. PSC events never produce signals."""
    signals = []
    for e in events:
        if e.event_type == "officer_appointed" and _is_cfo_or_chair(e.details):
            signal_type = "new_cfo_or_chair"
            title = e.details.get("occupation") or e.details.get("role")
            quote = f"{e.details.get('name')} appointed {title} on {e.event_date}"
        elif e.event_type in ("charge_created", "charge_satisfied"):
            signal_type = "debt_charge_event"
            verb = "created" if e.event_type == "charge_created" else "satisfied"
            lenders = e.details.get("lenders") or []
            quote = f"Charge {e.details.get('charge_code') or ''} {verb} {e.event_date}"
            if lenders:
                quote += f" in favour of {lenders[0]}"
        else:
            continue
        signals.append(Signal(
            signal_id=f"sig-{e.event_id}",
            company_id=e.company_id,
            evidence_id=e.event_id,
            signal_class=SIGNAL_CLASS_OF[signal_type],
            signal_type=signal_type,
            event_date=e.event_date,
            publication_date=e.publication_date,
            evidence_quote=_cap_words(quote),
            status="confirmed",
            source_url=e.source_url,
            extraction_method="registry_rule",
        ))
    return signals


def coverage(
    events: list[RegistryEvent], raw_by_number: dict[str, dict[str, list[dict]]]
) -> dict[str, Any]:
    """Data-availability summary for one company (feeds the confidence output later)."""
    accounts = [e for e in events if e.event_type == "accounts_filed" and e.event_date]
    latest = max(accounts, key=lambda e: e.event_date) if accounts else None
    return {
        "entities": list(raw_by_number),
        "registry_events": len(events),
        "latest_accounts_type": latest.details.get("accounts_type") if latest else None,
        "has_officers": any(r["officers"] for r in raw_by_number.values()),
        "has_charges": any(r["charges"] for r in raw_by_number.values()),
        "has_psc": any(r["psc"] for r in raw_by_number.values()),
    }
