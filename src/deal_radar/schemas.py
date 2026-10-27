"""Data contracts (pydantic v2). See docs/PRD.md sections 5, 6, 8 and 17."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from deal_radar.rules import add_months

MAX_QUOTE_WORDS = 25
ANCHOR_MIN = date(2025, 1, 1)
ANCHOR_MAX = date(2025, 9, 30)

OwnerType = Literal["pe_backed", "corporate_subsidiary", "vc_backed", "founder_family", "unknown"]
TransactionType = Literal["change_of_control", "ipo"]
LabelSourceType = Literal["pe_or_acquirer_press_release", "rns", "cma_notice", "companies_house_psc"]
EvidenceSourceType = Literal["news", "press_release", "registry_filing", "rns", "cma_notice", "other"]
SignalClass = Literal["timing_clock", "direct_intent", "readiness", "external_context", "counter_signal"]
SignalType = Literal[
    "pe_holding_period", "pe_fund_age", "debt_charge_event",
    "advisers_appointed", "strategic_review", "exploring_options", "parent_non_core",
    "new_cfo_or_chair", "auditor_upgrade", "governance_change",
    "peer_deals_in_sector", "active_buyers", "sector_consolidation",
    "recently_acquired", "large_recent_fundraise",
]

# PRD section 8: which class each signal type belongs to.
SIGNAL_CLASS_OF: dict[str, str] = {
    "pe_holding_period": "timing_clock",
    "pe_fund_age": "timing_clock",
    "debt_charge_event": "timing_clock",
    "advisers_appointed": "direct_intent",
    "strategic_review": "direct_intent",
    "exploring_options": "direct_intent",
    "parent_non_core": "direct_intent",
    "new_cfo_or_chair": "readiness",
    "auditor_upgrade": "readiness",
    "governance_change": "readiness",
    "peer_deals_in_sector": "external_context",
    "active_buyers": "external_context",
    "sector_consolidation": "external_context",
    "recently_acquired": "counter_signal",
    "large_recent_fundraise": "counter_signal",
}


class Company(BaseModel):
    company_id: str
    name: str
    companies_house_number: str | None = None
    owner_type: OwnerType
    sector: str | None = None
    size_band: str | None = None


class Transaction(BaseModel):
    company_id: str
    transaction_type: TransactionType
    announcement_date: date
    description: str
    source_urls: list[str] = Field(min_length=1)
    source_types: list[LabelSourceType] = Field(min_length=1)

    @field_validator("source_types")
    @classmethod
    def psc_not_sole_source(cls, v: list[str]) -> list[str]:
        if set(v) == {"companies_house_psc"}:
            raise ValueError("companies_house_psc is a cross-check only and cannot be the sole source")
        return v


class Evidence(BaseModel):
    """Metadata for one source document. Full text is never stored here (see CLAUDE.md)."""

    evidence_id: str
    company_id: str
    url: str
    source_type: EvidenceSourceType
    publication_date: date | None
    retrieved_at: datetime
    title: str | None = None


class Signal(BaseModel):
    signal_id: str
    company_id: str
    evidence_id: str
    signal_class: SignalClass
    signal_type: SignalType
    event_date: date | None
    publication_date: date | None
    evidence_quote: str = Field(min_length=1)
    status: Literal["confirmed", "attributed", "speculative"]
    source_url: str
    extraction_method: Literal["registry_rule", "llm"]

    @field_validator("evidence_quote")
    @classmethod
    def quote_max_words(cls, v: str) -> str:
        if len(v.split()) > MAX_QUOTE_WORDS:
            raise ValueError(f"evidence_quote exceeds {MAX_QUOTE_WORDS} words")
        return v

    @model_validator(mode="after")
    def type_matches_class(self) -> "Signal":
        expected = SIGNAL_CLASS_OF[self.signal_type]
        if self.signal_class != expected:
            raise ValueError(f"signal_type {self.signal_type} belongs to {expected}, not {self.signal_class}")
        return self


class MatchedPair(BaseModel):
    pair_id: str
    deal_company_id: str
    control_company_id: str
    anchor_date: date
    control_status: Literal["verified", "unresolved"]
    sources_checked: list[str]
    check_period_start: date
    check_period_end: date

    @model_validator(mode="after")
    def anchor_and_check_period(self) -> "MatchedPair":
        if not ANCHOR_MIN <= self.anchor_date <= ANCHOR_MAX:
            raise ValueError(f"anchor_date must be within {ANCHOR_MIN}..{ANCHOR_MAX}")
        if self.check_period_start != add_months(self.anchor_date, -12):
            raise ValueError("check_period_start must be anchor_date - 12 months")
        if self.check_period_end != add_months(self.anchor_date, 12):
            raise ValueError("check_period_end must be anchor_date + 12 months")
        return self


class Snapshot(BaseModel):
    company_id: str
    pair_id: str | None = None
    prediction_date: date
    window_end: date

    @model_validator(mode="after")
    def window_is_12_months(self) -> "Snapshot":
        if self.window_end != add_months(self.prediction_date, 12):
            raise ValueError("window_end must be prediction_date + 12 months")
        return self


RegistryEventType = Literal[
    "officer_appointed", "officer_resigned", "charge_created", "charge_satisfied",
    "psc_added", "psc_ceased", "accounts_filed", "auditor_resigned",
]


class RegistryEvent(BaseModel):
    """A dated Companies House event. publication_date is when it became public; None means unusable."""

    event_id: str
    company_id: str
    ch_number: str
    event_type: RegistryEventType
    event_date: date | None
    publication_date: date | None
    details: dict[str, Any]
    source_url: str = Field(min_length=1)


class AmbiguousMatch(BaseModel):
    """An event whose publication date could not be matched to exactly one filing."""

    event_id: str
    company_id: str
    ch_number: str
    event_type: RegistryEventType
    event_date: date | None
    reason: Literal["no_candidate", "multiple_candidates"]
    candidate_filing_ids: list[str]
    candidate_filing_dates: list[date]


class EntityGroup(BaseModel):
    """The Companies House numbers of a company's group (operating company plus documented holding entities)."""

    company_id: str
    ch_numbers: list[str] = Field(min_length=1)

    @field_validator("ch_numbers")
    @classmethod
    def no_duplicates(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("duplicate ch_numbers")
        return v
