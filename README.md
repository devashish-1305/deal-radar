# Deal Radar

Deal Radar is a prototype that ranks UK private companies by how likely they are to announce a change of control in the next ~12 months, using only public, legitimate data (Companies House and news). It is built to help Third Bridge prepare research before client demand arrives; it is research prioritisation, not investment advice. This repository holds the proof of concept: 6 matched pairs (a company that announced a deal in Jan–Sep 2025 and a similar one that did not), scored at 12, 6 and 3 months before each deal using only information published before each date. The full specification is in [docs/PRD.md](docs/PRD.md).

## Headline findings (hypothesis-generating, not validation)
See [docs/findings.md](docs/findings.md) for the numbers, evidence and caveats.
- **The PE holding clock was the only consistent separator** between deal and control companies; weaker signals (debt events) added noise.
- **No intent signal was visible before the last 3 months**, and the only one found was at a company that did not transact.
- **Free public news was thin** compared with the registry, so the product's main cost is licensed news, not the LLM; leakage guards caught real post-deal content.

## Rerun everything downstream (one command)
```
PYTHONPATH=src .venv/bin/python scripts/run_all.py
```
A fresh clone can rerun the extraction evaluation, features, scoring, findings and chart data with this one command, using only committed files: **no API key, no network**. Outputs are byte-identical on every run. If the local LLM response cache (`data/raw/llm/`, git-ignored) is present it is used instead; both modes give identical results. Setup: `python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'` (pinned dependencies in `pyproject.toml`). Tests: `.venv/bin/python -m pytest`.

Upstream steps that need the network are not part of the rerun: the Companies House fetch (`scripts/fetch_registry.py`, needs a key in `.env`), evidence collection (`scripts/collect_evidence.py`) and live LLM extraction (`scripts/run_extraction.py`, needs `ANTHROPIC_API_KEY`).

## Repo map
- `src/deal_radar/` — pipeline code: schemas, point-in-time rules, Companies House client, evidence, extraction, features, score.
- `scripts/` — runnable steps; `run_all.py` rebuilds everything downstream.
- `data/cases/` — matched pairs, sponsor entries, gold labels, search protocol.
- `data/processed/` — structured outputs (evidence metadata, registry events, signals, features, scores, `charts/` for slides).
- `data/raw/` — downloaded pages and API responses; git-ignored (copyright and terms of use).
- `prompts/` — the LLM extraction prompt. `tests/` — pytest suite.

## Key documents
- [PRD](docs/PRD.md) and [decisions](docs/decisions.md)
- [Case selection](docs/case_selection.md) — the 6 matched pairs and how controls were verified
- [Evidence log](docs/evidence_log.md) — search protocol, every page opened, blocked or excluded
- [Extraction evaluation](docs/extraction_eval.md) — Haiku vs Sonnet against reviewed gold labels
- [Features](docs/features.md) — point-in-time features at 12/6/3 months
- [Scoring (pre-registered)](docs/scoring.md) and [scoring results](docs/scoring_results.md)
- [Findings](docs/findings.md) — the single source of truth for the slides
- [Architecture](docs/architecture.md) — the proof of concept as built, and the proposed 100,000-company design
- Prompt sample: [prompts/extract_v1.md](prompts/extract_v1.md)
