"""Step 8: the pre-registered weighted score (docs/scoring.md), bands, and per-pair comparisons (pure functions).

The configuration (weights, clock cap, bands, sensitivity weights) is parsed from the JSON block in docs/scoring.md,
which was committed before any score was computed. The score is a ranking aid, never a probability.
"""

import json
import re

TERMS = ["intent_present", "clock", "debt_event_12m", "readiness_18m", "recently_acquired", "fundraise_12m"]
LLM_TERMS = {"intent_present", "readiness_18m", "fundraise_12m"}
PROVENANCE_KEY = {"intent_present": "intent_present", "clock": "pe_holding_years",
                  "debt_event_12m": "debt_financings_12m", "readiness_18m": "readiness_18m",
                  "recently_acquired": "recently_acquired", "fundraise_12m": "fundraise_12m"}
VARIANTS = ["full", "holding_only", "full_minus_clock", "sensitivity", "verified_only"]
CATEGORY_RANK = {"clock-driven": 3, "other": 2, "weak (debt-only)": 1, "unconfirmed-only": 0}


def load_config(scoring_md: str) -> dict:
    """The pre-registered configuration: the single ```json block in docs/scoring.md."""
    blocks = re.findall(r"```json\n(.*?)\n```", scoring_md, re.S)
    if len(blocks) != 1:
        raise ValueError("docs/scoring.md must contain exactly one ```json block")
    return json.loads(blocks[0])


def clock_value(years: float | None, cap: float) -> float:
    return 0.0 if years is None else min(years / cap, 1.0)


def contributions(row: dict, config: dict, confirmed_ids: set[str], variant: str = "full") -> list[dict]:
    """Non-zero term contributions for one row under a variant, each with its Step 7 provenance ids.

    gold_confirmed: for LLM terms, True if any provenance signal matched a gold label in Step 6, else False;
    "n/a" for registry (debt) and sponsor-entry (clock, recently_acquired) terms.
    """
    weights = config["sensitivity_weights"] if variant == "sensitivity" else config["weights"]
    f, out = row["features"], []
    for term in TERMS:
        if variant == "holding_only" and term != "clock":
            continue
        if variant == "full_minus_clock" and term == "clock":
            continue
        raw = clock_value(f["pe_holding_years"], config["clock_cap_years"]) if term == "clock" else float(bool(f[term]))
        value = weights[term] * raw
        if value == 0:
            continue
        ids = row["provenance"][PROVENANCE_KEY[term]]
        confirmed = (any(i in confirmed_ids for i in ids) if term in LLM_TERMS else "n/a")
        if variant == "verified_only" and confirmed is False:
            continue
        out.append({"term": term, "value": round(value, 6), "ids": ids, "gold_confirmed": confirmed})
    return out


def score(row: dict, config: dict, confirmed_ids: set[str], variant: str = "full") -> tuple[float, list[dict]]:
    contribs = contributions(row, config, confirmed_ids, variant)
    return round(sum(c["value"] for c in contribs), 6), contribs


def band(value: float, config: dict) -> str:
    b = config["likelihood_bands"]
    return "High" if value >= b["high_min"] else "Medium" if value >= b["medium_min"] else "Low"


def confidence(row: dict, config: dict) -> str:
    """Coverage band; capped at Medium when the row has no usable news/press evidence (no ev- ids)."""
    b, n = config["confidence_bands"], row["features"]["coverage_items"]
    level = "High" if n >= b["high_min"] else "Medium" if n >= b["medium_min"] else "Low"
    has_news = any(i.startswith("ev-") for i in row["provenance"]["coverage_items"])
    return "Medium" if level == "High" and not has_news else level


def classify_win(deal: list[dict], control: list[dict]) -> tuple[str, list[str]]:
    """Driving terms = terms whose contribution is larger for the deal than for the control (docs/scoring.md §4)."""
    d = {c["term"]: c for c in deal}
    k = {c["term"]: c for c in control}
    drivers = [t for t in TERMS if d.get(t, {}).get("value", 0) > k.get(t, {}).get("value", 0)]

    def unconfirmed(term):
        side = d.get(term) or k.get(term)  # the side whose non-zero contribution creates the difference
        return term in LLM_TERMS and side["gold_confirmed"] is False
    if "clock" in drivers:
        return "clock-driven", drivers
    if drivers == ["debt_event_12m"]:
        return "weak (debt-only)", drivers
    if drivers and all(unconfirmed(t) for t in drivers):
        return "unconfirmed-only", drivers
    return "other", drivers


def compare_pairs(rows: list[dict], config: dict, confirmed_ids: set[str], variant: str) -> list[dict]:
    """Deal vs control per (pair, horizon): win / tie / loss, with the win's driving terms and category."""
    by_key = {(r["pair_id"], r["horizon"], r["role"]): r for r in rows}
    out = []
    for (pair_id, horizon, role), deal in by_key.items():
        if role != "deal":
            continue
        control = by_key[(pair_id, horizon, "control")]
        ds, dc = score(deal, config, confirmed_ids, variant)
        cs, cc = score(control, config, confirmed_ids, variant)
        diff = ds - cs
        outcome = "tie" if abs(diff) <= config["tie_tolerance"] else "win" if diff > 0 else "loss"
        category, drivers = classify_win(dc, cc) if outcome == "win" else (None, [])
        out.append({"pair_id": pair_id, "horizon": horizon, "deal": deal["company_id"], "control": control["company_id"],
                    "deal_score": ds, "control_score": cs, "outcome": outcome, "category": category, "drivers": drivers})
    return out
