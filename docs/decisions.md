# Decisions

1. Frame as a research-prioritisation tool, not investment advice — research is currently reactive; content must be ready before client demand arrives.
2. Users are Third Bridge content/research teams — they are the ones who prepare research ahead of demand.
3. Target = publicly announced change of control within 12 months, dated by announcement — announcement is the public, observable event that drives client demand.
4. IPOs, refinancing/restructuring and growth/minority equity out of scope for v1 — less reliably observable in public data; future extensions.
5. Labels per window: CoC → positive; IPO first → window excluded; IPO before window → company out of scope; no deal → "no publicly observed transaction" — competing outcomes and undisclosed deals must not be mislabelled; the universe is private companies.
6. Labels from PE/acquirer press releases, LSE RNS and CMA notices; Companies House PSC only as cross-check — PSC shows only >25% holders and misses holding-company-level deals.
7. UK-first pilot of 100 mid-market companies stratified by owner type (40/25/20/15) — Companies House gives free, dated private-company data for honest point-in-time backtests; segments behave differently.
8. All signals (clocks, intent, readiness, external context, counter-signals) are hypotheses; only historically datable types used in backtests — they are unproven, and undatable signals would leak or be unbacktestable.
9. Pipeline: sources → deterministic entity matching → LLM extraction → deterministic validation/features → scoring → weekly list, LLM only on new documents — keeps weekly refresh cheap and reproducible.
10. LLM only extracts dated, source-backed events (plus summaries for top companies); never the probability — keeps predictions deterministic, auditable and free of hallucinated scores.
11. Transparent weighted baseline first, logistic regression only with enough labelled history; benchmarks random and holding-period-only — simple, explainable, and must beat naive baselines to be useful.
12. Three separate outputs: likelihood, evidence coverage, research priority, plus dated signals and counter-signals — insufficient evidence is not low likelihood, and priority depends on client relevance.
13. Walk-forward backtest with company- and time-grouped splits; internal request logs for evaluation only — snapshots of one company are correlated; leakage must be avoided; logs are not public data.
14. Tiered cost funnel, costs provisional — cheap data for all, expensive LLM only where needed; costs are untested.
15. Test H1 (clock + intent), H2 (PE/carve-outs most predictable), H3 (signals ≥6 months early) — these are the claims the approach depends on.
16. Track risks: undisclosed deals, late signals, coverage bias, holding chains, thin accounts, leakage, entity matching — known failure modes to measure and report.
17. PoC = 5–8 matched pairs (deals Jan–Sep 2025), controls verified clean ±12 months or marked "unresolved", snapshots at 12/6/3 months anchored to the deal date, reported per pair — a feasibility study, not validation; never assume no transaction occurred.
18. Deliverables: 3 slides (approach, evidence, product/success) plus optional notebook and prompt sample — brief allows max 3 slides plus a small PoC.
19. large_recent_fundraise is labelled for every disclosed round as a fact; PRD §8 does not define size/recency, so Step 7 applies the thresholds — keeps gold labels factual and judgement in one place.
20. Xeinadin/Exponent 2022 significant minority investment with board seats is labelled pe_holding_period: a PE sponsor's investment with board control starts the sponsor's holding clock.
