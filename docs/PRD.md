# Deal Radar — PRD

## 1. Problem
Third Bridge's research prioritisation is reactive. It needs to know earlier which private companies will transact, so content is ready when client demand arrives. This is a research-prioritisation tool, not investment advice.

## 2. Users
Third Bridge content/research teams.

## 3. Prediction target
At a prediction date, will the company have a PUBLICLY ANNOUNCED change-of-control transaction within the next 12 months? This covers a sale to a strategic buyer, a PE buyout (including secondary buyout), a merger, or a carve-out. The announcement date is the event, not the completion date.

**Unit of observation.** The operating business. A window is positive when a new party takes control of that business: a sale, a buyout, being merged into another group, or, for a carve-out, the division itself getting a new owner (the selling parent is not labelled). A merger of equals with no controlling party is ambiguous and excluded in v1. In the proof of concept every deal was a clear acquisition or majority stake, so this did not arise.

## 4. Out of scope for v1
IPOs, refinancing/restructuring and growth/minority equity. These are future extensions because they are less reliably observable in public data.

## 5. Label rules
Evaluated per prediction window:
- Change of control announced in the window (and before any IPO announcement) → POSITIVE.
- IPO announced in the window before any change of control → window EXCLUDED (competing outcome). This exclusion applies to that window only, not to the company forever.
- IPO announced before the window starts → the company is public and therefore out of scope (the universe is private companies). It is excluded from that point on.
- No announced deal → "no publicly observed transaction" (not a "true negative"), because some private deals go undisclosed.
- The same company can appear in several prediction windows.
- Steps 2 and 7 must enforce these rules with tests.

## 6. Label sources
- PE firm and acquirer press releases.
- London Stock Exchange RNS announcements when a listed buyer acquires a private target.
- CMA merger notices.
- Companies House PSC changes are used ONLY as a cross-check, not as the sole source (PSC shows >25% holders only, and PE deals often happen at holding-company level).

## 7. Universe and geography
- UK-first, as a PRACTICAL PILOT ASSUMPTION, not a claim that the UK is the best market. Reason: Companies House offers free, dated, company-level data on private companies (officers, PSC, charges, accounts), which enables honest point-in-time backtesting. The US has more news and deals but little private-company registry data. US expansion would use news, SEC Form D and state UCC filings.
- Pilot universe: 100 UK mid-market private companies, stratified by owner type: about 40 PE-backed, 25 corporate subsidiaries, 20 VC-backed, 15 founder/family. Performance and coverage are reported per segment.

## 8. Signals
All are HYPOTHESES to test, not established facts.
- **Timing clocks**
  - PE holding period (longer hold → exit more likely).
  - PE fund age (funds have a ~10-year life, which creates exit pressure, but this does not dictate individual deal timing).
  - Debt maturity / new charges.
- **Direct intent**
  - Advisers appointed.
  - Strategic review announced.
  - "Exploring options" reporting.
  - Parent describes the unit as non-core.
- **Readiness**
  - New CFO or chair with deal/IPO experience.
  - Auditor upgrade.
  - Governance changes.
- **External opportunity (context only)**
  - Peer deals in the sector.
  - Active buyers.
  - Sector consolidation.
- **Counter-signals**
  - Recently acquired (<2 years).
  - Large recent fundraise.
- Only signal types that can be dated historically (registry filings, news, press releases) are used in backtests. Job posts and website changes can only be collected going forward.

## 9. Pipeline
- Steps: Sources → entity matching (deterministic) → LLM extraction of dated, source-backed events → deterministic validation, dedup and feature building → scoring → weekly ranked list.
- Refresh logic: the ranked list is refreshed weekly. Deterministic features (e.g. holding-period clocks) are recomputed for all companies, which is cheap. LLM extraction runs only when a new document/event appears; cached evidence is reused otherwise.

## 10. Role of AI
- The LLM extracts events from unstructured text: company, event type, date, actors, verbatim quote, status, source. For top companies only, it also writes evidence-linked summaries.
- Everything else is deterministic.
- The LLM never produces the probability.

## 11. Scoring
- A transparent weighted baseline first; logistic regression only when enough labelled history exists.
- Benchmarks: (a) random selection, (b) a PE-holding-period-only ranking.

## 12. Outputs
Three outputs, kept separate:
- Transaction likelihood.
- Evidence confidence/coverage (insufficient evidence ≠ low likelihood).
- Research priority (likelihood × client relevance).
- Each company also shows its top dated signals with links and its counter-signals.

## 13. Evaluation
- Full scale: walk-forward backtest. Metrics: Precision@K, lift vs both benchmarks, lead time, measured calibration. Results sliced by owner segment and data coverage.
- Correlated snapshots: multiple snapshots of the same company are NOT independent observations. Train/test splits are grouped by company AND separated in time; no company appears on both sides of a split for overlapping windows.
- Business metric: the share of client research requests where coverage already existed (to be validated against Third Bridge's internal request logs).
- Third Bridge internal request logs are for EVALUATION ONLY. They are never a model input.

## 14. Scale and cost
- A tiered funnel: (1) cheap registry and clock data for all companies, (2) a cheap relevance filter on new news, (3) a small LLM for extraction on filtered documents only, (4) a larger LLM for summaries on the shortlist only.
- Expected main costs: news licensing and entity resolution.
- All cost figures are PROVISIONAL until tested.

## 15. Hypotheses to test
- H1: A clock plus an intent signal beats either one alone and beats the holding-period-only baseline.
- H2: PE-backed companies and carve-outs are the most predictable segments.
- H3: Useful signals appear ≥6 months before the announcement.

## 16. Risks
- Undisclosed deals (incomplete labels).
- Signals that appear too late.
- Disclosure/coverage bias toward well-documented companies.
- Holding-company ownership chains.
- Thin accounts for small companies.
- Leakage.
- Entity-matching errors.

## 17. Proof of concept (feasibility study, NOT validation)
- 5–8 matched pairs: a UK company with a change of control announced between Jan 2025 and Sep 2025, matched with a similar company (sector, size, owner type) with no publicly observed transaction.
- The Jan–Sep 2025 window ensures the full control-check period (below) has elapsed with at least a 1-month buffer as of 27 Oct 2026.
- Control definition: a control has "no publicly observed transaction" only if no change of control AND no IPO was announced from 12 months before its matched deal's announcement date through 12 months after it.
  - A control counts as verified only if all label sources (§6) were searched across the full period and nothing was found.
  - If any part of the period cannot be checked, the control is labelled "unresolved" and is not used. Never assume no transaction occurred.
- Snapshots of public evidence at 12, 6 and 3 months before the announcement. Each control's snapshot dates are anchored to its MATCHED DEAL's announcement date.
- It answers four questions:
  1. Were signals publicly observable?
  2. How early?
  3. Did the simple score rank the deal company above its pair?
  4. What was missing?
- Results are reported per matched pair, never pooled as independent observations. They are illustrative only, with no claims of predictive accuracy.

## 18. Deliverables
- Slide 1, Approach: target, data, pipeline, cost funnel.
- Slide 2, Evidence: signal hierarchy, hypotheses, PoC findings, limitations.
- Slide 3, Product and success: an illustrative ranked mock-up plus how success is measured.
- Optional: notebook and prompt sample.
