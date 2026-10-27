# Scoring: pre-registered (Step 8, Phase A)

This document fixes the score, the bands, the evaluation and the falsification criteria **before any score is computed**. Phase B (`src/deal_radar/score.py`, `scripts/run_scoring.py`) must use exactly what is written here. A test compares the weights Phase B uses with the JSON block below, as committed in "step 8a: pre-registered scoring".

**Disclosure:** the Step 7 feature table (`docs/features.md`) had already been seen when these weights were written. The weights are justified only by the PRD §8 signal hierarchy, not by that table. The sensitivity check (all weights ±1) and the verified-only diagnostic below exist to show how much the results depend on these specific choices and on extraction errors.

## 1. Weights (PRD §8 hierarchy)
PRD §8 orders the signals: direct intent strongest, timing clocks next, readiness weaker, external context excluded, counter-signals negative.

| Term | Contribution | Why |
|---|---|---|
| intent_present | +3 | Direct intent, the strongest class. |
| clock | 2 × min(pe_holding_years / 5, 1); 0 if pe_holding_years is None | A timing clock. "About 5 years" is an **explicit assumption about a typical PE hold, not a fact**. In the holding-only comparison, any increasing function of holding years gives the same pair outcomes, so this cap cannot change those results. |
| debt_event_12m | +1 | Timing clock (debt / new charges), weaker than the holding clock. |
| readiness_18m | +1 | Readiness, weaker than intent and clocks. |
| recently_acquired | −2 | Counter-signal (acquired < 2 years ago). |
| fundraise_12m | −1 | Counter-signal (recent fundraise). |
| external_context | not scored | PRD §8: context only (it is not a feature in Step 7). |

Score = sum of the contributions. Each contribution keeps its Step 7 provenance ids.

```json
{
  "weights": {
    "intent_present": 3,
    "clock": 2,
    "debt_event_12m": 1,
    "readiness_18m": 1,
    "recently_acquired": -2,
    "fundraise_12m": -1
  },
  "clock_cap_years": 5,
  "likelihood_bands": {"high_min": 3, "medium_min": 1.5},
  "confidence_bands": {"high_min": 50, "medium_min": 15},
  "sensitivity_weights": {
    "intent_present": 1,
    "clock": 1,
    "debt_event_12m": 1,
    "readiness_18m": 1,
    "recently_acquired": -1,
    "fundraise_12m": -1
  },
  "tie_tolerance": 1e-9
}
```

## 2. Likelihood band (fixed now)
- **High:** score ≥ 3.
- **Medium:** 1.5 ≤ score < 3.
- **Low:** score < 1.5.

The score is a ranking aid. **It is never expressed as a probability or a percentage.**

## 3. Confidence band (fixed now)
Based on `coverage_items` (usable evidence items plus usable registry events at the prediction date):
- **High:** ≥ 50.
- **Medium:** 15–49.
- **Low:** < 15.

Confidence is **capped at Medium** for any row with zero usable news or press evidence (no evidence id in the row's coverage provenance). Insufficient evidence is not low likelihood (PRD §12): confidence is reported separately and never changes the score.

## 4. Evaluation (defined now)
- **Comparisons:** 6 pairs × 3 horizons (12, 6 and 3 months before the anchor) = 18. For each one:
  - **win** if the deal score > the control score;
  - **tie** if the two are equal within 1e-9;
  - **loss** otherwise.
- **Benchmarks:**
  - (a) **Random:** 9 of 18 wins expected.
  - (b) **Holding-only:** the clock term alone. Non-PE pairs tie by construction.
- **Ablations:**
  - clock only (identical to holding-only);
  - full minus clock (every term except the clock);
  - full.
- **Sensitivity:** every non-zero weight is set to ±1 with the same sign (`sensitivity_weights` above), and the clock becomes min(years / 5, 1).
- **Diagnostic "verified-only":** recompute the full score, dropping any contribution from an LLM signal (intent, readiness, fundraise) that did **not** match a gold label in the Step 6 evaluation (`extract.match`, as in `docs/extraction_eval.md`).
  - An LLM term is kept if at least one of its provenance signals matched gold.
  - Registry contributions (debt) and sponsor-entry contributions (clock, recently_acquired) are unaffected.
  - This diagnoses how much extraction errors matter. **It is not a tuned score.**
- **Driving term of a win:** the term or terms whose contribution is larger for the deal than for the control in that comparison. Each win is classified in this order:
  1. **clock-driven:** the clock is among the driving terms;
  2. **weak (debt-only):** the only driving term is debt_event_12m. It is weak because debt events do not separate deals from controls elsewhere in this sample (for example, Cognism, a control, has 4 at every snapshot);
  3. **unconfirmed-only:** every driving term is an LLM term flagged gold-unconfirmed. This counts as **no support**;
  4. **other:** any remaining driving terms, each named (for example readiness_18m).
- **Reporting:** results are reported per pair (and per horizon), **never pooled into one accuracy percentage**. Counts such as "wins out of 18" are given only alongside the per-pair table.

## 5. What would falsify our hypotheses on this sample (written before results)
- **H1: a clock plus an intent signal beats either one alone and beats the holding-only baseline.**
  - **Testable only if `intent_present` is True in at least one of the 36 rows.** If intent is absent in all of them, H1 is reported as **"untestable"** and nothing more. No pass or fail is implied, and no other result is used as support for or against it.
  - If testable: H1 is contradicted if, in the comparisons where either company has intent, the full score does not win more often than **both** clock only and full minus clock, or does not win more often than holding-only.
- **H2: PE-backed companies (and carve-outs) are the most predictable segments.**
  - Contradicted if the full-score win share in the PE-backed pairs (P1 and P6, 6 comparisons) is **not higher** than in the VC-backed pairs (P2–P5, 12 comparisons).
  - Each win is also labelled with its driving term (clock-driven / weak (debt-only) / unconfirmed-only / other), reported per segment.
  - A PE advantage resting only on weak or unconfirmed-only wins is reported as such, not as support.
  - The carve-out part is **untestable**: the sample has no carve-outs. Two PE pairs are anecdotal.
- **H3: useful signals appear at least 6 months before the announcement.**
  - For each pair, look at the full-score wins at the 12-month and 6-month horizons and classify the pair by its strongest win, in this order: clock-driven, then other (named), then weak (debt-only), then no support. Unconfirmed-only wins, losses and ties count as no support.
  - **Report H3 as counts across the 6 pairs:** clock-driven, other (named terms), weak (debt-only) and no support.
  - H3 is contradicted on this sample if **no** pair has clock-driven or other support.
  - Signals that appear only in the late-clue window (the last 3 months; `docs/features.md`) count **against** H3, never for it. They are shown separately and never scored.

## 6. Wording rules (all outputs)
- PTSG and Xeinadin holding periods are always labelled **"announcement-based proxy"**, because their sponsor entry is an announcement with completion not confirmed.
- Any separation between deals and controls is **"hypothesis-generating, not validation"**.
- No output claims predictive performance. Six pairs and 36 correlated snapshots are a feasibility study (PRD §17).
- No probability, percentage likelihood or calibrated-sounding language for the score.
