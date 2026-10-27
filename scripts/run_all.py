"""Step 9: rebuild every downstream output with one command, deterministically, with no network and no API key.

Run from the repo root:  PYTHONPATH=src .venv/bin/python scripts/run_all.py [--committed]

Order: extraction eval -> features -> scoring -> findings + chart data.
Extraction mode: "cache" if data/raw/llm/ exists (raw responses), otherwise "committed" (fresh clone: committed
llm_signals_*.json + extraction_runs.json + gold_signals.json via extract.match). Both modes produce identical outputs.
--committed forces committed mode. Upstream steps that need the network (Companies House fetch, evidence collection,
live LLM extraction) are not rerun.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_features  # noqa: E402
import build_findings  # noqa: E402
import run_extraction  # noqa: E402
import run_scoring  # noqa: E402

OUTPUTS = [
    "data/processed/llm_signals_haiku.json", "data/processed/llm_signals_sonnet.json",
    "data/processed/extraction_runs.json",
    "docs/extraction_eval.md", "data/processed/charts/extraction_compare.json",
    "data/processed/features.json", "docs/features.md",
    "data/processed/scores.json", "docs/scoring_results.md",
    "docs/findings.md", "data/processed/charts/pairs_scores.json", "data/processed/charts/evidence_funnel.json",
    "data/processed/charts/signal_timeline.json",
]


def extraction_mode(force_committed: bool = False) -> str:
    return "committed" if force_committed or not run_extraction.LLM_CACHE.exists() else "cache"


def main(force_committed: bool = False) -> str:
    mode = extraction_mode(force_committed)
    print(f"extraction mode: {mode} ({'data/raw/llm cache' if mode == 'cache' else 'committed files only'}); no API calls")
    run_extraction.main(mode)
    build_features.main()
    run_scoring.main()
    build_findings.main()
    return mode


if __name__ == "__main__":
    main("--committed" in sys.argv)
