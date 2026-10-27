# CLAUDE.md

## Project summary
Deal Radar: an AI tool that ranks private companies by their likelihood of a publicly announced change-of-control transaction in the next ~12 months, using only public, legitimate data.
Purpose: help Third Bridge prepare research before client demand arrives (research prioritisation, not investment advice).
Pilot: 100 UK mid-market private companies, with a design for scaling to ~100,000. Full spec in `docs/PRD.md`.

## How we work
- One step at a time. Each step has a goal, acceptance criteria and tests.
- At the end of a step: run the tests, report, STOP. Never start the next step unprompted.

## Gate checklist
Items 1–4 and 6 apply to EVERY step. Item 5 (user approval) is required only at gate steps (1, 3, 6, 8). At non-gate steps: report and stop; the user's next prompt counts as approval.

1. Tests pass.
2. Acceptance criteria met.
3. Simplicity check: is there anything not required by the PRD/step? Remove it.
4. Sufficiency check: does anything required by the PRD/step remain missing? Flag it.
5. User approval (gate steps only).
6. Pre-push check:
   - `git status` and `git ls-files` show no .env, keys, raw data or local artifacts.
   - If any secret was ever committed, STOP and tell the user (adding it to .gitignore later is not enough; the key must be rotated).

## Simplicity rules
- Build the simplest thing that meets the acceptance criteria.
- No new dependency without stating why.
- No abstraction or class unless it is used at least twice.
- Models are limited to a transparent weighted score and logistic regression.
- No UI or dashboards (the product view is a slide mock-up).

## Hard rules (non-negotiable)
- Public, legitimate data only, and respect terms of use. No scraping LinkedIn or any site that forbids it. Companies House only via its official API.
- Point-in-time rule: a piece of evidence may be used for a prediction date ONLY if its publication/filing date is strictly before that date. Content published later never counts, even if it describes earlier events.
- The LLM only extracts evidence. It never outputs a probability, score or prediction.
- Every extracted signal must carry: source URL, publication date, verbatim evidence quote, and status (confirmed / attributed / speculative).
- Never fabricate companies, deals, dates, URLs or quotes. If something is unknown, record it as unknown.
- Secrets live only in .env.
- Data commit policy:
  - Commit structured records (signals, dates, URLs, short evidence quotes) and Companies House data (Open Government Licence).
  - NEVER commit full article text or full documents. These live only in data/raw/, which is git-ignored, to respect copyright and terms of use.
  - Evidence quotes are the shortest verbatim span that supports the signal, max 25 words.

## Testing rules
- pytest.
- Tests are written alongside each module.
- Any code that touches dates must have leakage tests.

## Repo map
- `docs/` — PRD and decisions log.
- `src/deal_radar/` — Python package (pipeline code).
- `scripts/` — runnable pipeline scripts (e.g. `fetch_registry.py`).
- `tests/` — pytest tests (fixtures in `tests/fixtures/`).
- `prompts/` — LLM extraction/summary prompts.
- `data/raw/` — raw downloaded source data (git-ignored).
- `data/processed/` — cleaned, derived datasets.
- `data/cases/` — matched-pair PoC case files.
- `notebooks/` — analysis notebooks.

## Step tracker
| Step | Status | Gate |
|---|---|---|
| 1 Scaffold + PRD | done | Gate |
| 2 Data contracts + tests | done | |
| 3 Case selection (matched pairs) | done | Gate |
| 4 Companies House fetcher | done | |
| 5 Dated evidence collection | done | |
| 6 LLM extraction + accuracy check | done | Gate |
| 7 Point-in-time features at 12/6/3 months + leakage tests | done | |
| 8 Baseline score + benchmarks | done | Gate |
| 9 Findings + chart | done | |
| 10 Slide content | not started | |
