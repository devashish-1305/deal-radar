"""Step 6a: content-leak exclusion and gold labels."""

import json
import subprocess
from pathlib import Path

import pytest

from deal_radar.cases import load_cases
from deal_radar.evidence import content_leak
from deal_radar.rules import is_usable
from deal_radar.schemas import Evidence, Signal

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "cases"
EVIDENCE = ROOT / "data" / "processed" / "evidence.json"
ARTICLES = ROOT / "data" / "raw" / "articles"
GOLD = CASES / "gold_signals.json"
LEAK = json.loads((CASES / "leak_check.json").read_text())
OXFORD_LEAKED = "ev-oxford_ionics-f7f92b5f3c"


def norm(s: str) -> str:
    return " ".join(s.split())


# --- content-leak check -----------------------------------------------------------------------------

def test_fixture_with_leaked_buyer_name_is_flagged():
    text = "Fakeco raises £2m.\nRelated: Buyerco completes deal for Fakeco"
    assert content_leak(text, ["Fakeco"], ["Buyerco"], LEAK["outcome_phrases"]) == "Buyerco"


def test_fixture_with_outcome_phrase_is_flagged():
    text = "Fakeco raises £2m.\nCompany profile: Fakeco [Acquired by someone]"
    assert content_leak(text, ["Fakeco"], [], LEAK["outcome_phrases"]) == "Fakeco acquired by"
    assert content_leak("Bigco completes acquisition of Fakeco", ["Fakeco"], [], LEAK["outcome_phrases"])


def test_clean_text_is_not_flagged():
    text = "Fakeco acquires Smallco. Another firm was acquired by Megacorp. Buyercorp is unrelated."
    assert content_leak(text, ["Fakeco"], ["Buyerco"], LEAK["outcome_phrases"]) is None


def test_every_pair_has_buyer_names():
    _, _, pairs = load_cases(CASES)
    assert {p.pair_id for p in pairs} == set(LEAK["buyers_by_pair"])
    assert all(LEAK["buyers_by_pair"].values())


def test_buyer_names_never_used_in_queries():
    spec = json.loads((CASES / "evidence_queries.json").read_text())
    buyers = [b.lower() for names in LEAK["buyers_by_pair"].values() for b in names]
    for q in spec["queries"]:
        assert not any(b in q["query"].lower() for b in buyers)


# --- real data ----------------------------------------------------------------------------------------

def evidence():
    if not EVIDENCE.exists():
        pytest.skip("evidence.json not generated yet")
    return [Evidence.model_validate(e) for e in json.loads(EVIDENCE.read_text())]


def in_scope():
    _, _, pairs = load_cases(CASES)
    anchor = {}
    for p in pairs:
        anchor[p.deal_company_id] = anchor[p.control_company_id] = p.anchor_date
    return {e.evidence_id: e for e in evidence() if is_usable(e, anchor[e.company_id])}


def test_real_oxford_ionics_leak_is_excluded_and_logged():
    assert OXFORD_LEAKED not in {e.evidence_id for e in evidence()}
    log = (ROOT / "docs" / "evidence_log.md").read_text()
    section = log.split("## Excluded as content_leak", 1)[1].split("\n## ", 1)[0]
    assert OXFORD_LEAKED in section


def test_real_in_scope_texts_have_no_leak():
    if not ARTICLES.exists():
        pytest.skip("data/raw/articles absent (e.g. CI)")
    spec = json.loads((CASES / "evidence_queries.json").read_text())["companies"]
    _, _, pairs = load_cases(CASES)
    pair_of = {}
    for p in pairs:
        pair_of[p.deal_company_id] = pair_of[p.control_company_id] = p.pair_id
    for eid, e in in_scope().items():
        text = f"{e.title}\n{(ARTICLES / f'{eid}.txt').read_text()}"
        assert content_leak(text, spec[e.company_id]["aliases"], LEAK["buyers_by_pair"][pair_of[e.company_id]],
                            LEAK["outcome_phrases"]) is None, eid


def test_gold_ids_equal_in_scope_set_after_leak_exclusion():
    gold = json.loads(GOLD.read_text())["signals"]
    assert set(gold) == set(in_scope())
    assert OXFORD_LEAKED not in gold


def test_gold_signals_validate_against_schema():
    scope = in_scope()
    for eid, signals in json.loads(GOLD.read_text())["signals"].items():
        e = scope[eid]
        for i, g in enumerate(signals):
            assert set(g) == {"signal_type", "signal_class", "evidence_quote", "status"}
            Signal(signal_id=f"gold-{eid}-{i}", company_id=e.company_id, evidence_id=eid, event_date=None,
                   publication_date=e.publication_date, source_url=e.url, extraction_method="llm", **g)


def test_gold_quotes_are_verbatim_in_stored_text():
    if not ARTICLES.exists():
        pytest.skip("data/raw/articles absent (e.g. CI)")
    for eid, signals in json.loads(GOLD.read_text())["signals"].items():
        text = norm((ARTICLES / f"{eid}.txt").read_text())
        for g in signals:
            assert norm(g["evidence_quote"]) in text, (eid, g["evidence_quote"])


PHASE_A_COMMIT = "4dbb030"  # "step 6a: gold labels", committed before any LLM call or output existed


def test_gold_labels_unchanged_since_phase_a():
    """Independence: the gold file must be byte-identical to the Phase A commit (made with no data/raw/llm/)."""
    shown = subprocess.run(["git", "show", f"{PHASE_A_COMMIT}:data/cases/gold_signals.json"],
                           cwd=ROOT, capture_output=True, text=True)
    if shown.returncode != 0:
        pytest.skip("git history unavailable")
    assert GOLD.read_text() == shown.stdout


def test_review_doc_covers_every_gold_id():
    review = (ROOT / "docs" / "gold_review.md").read_text()
    for eid in json.loads(GOLD.read_text())["signals"]:
        assert eid in review


def content_leak_ids() -> set[str]:
    log = (ROOT / "docs" / "evidence_log.md").read_text()
    section = log.split("## Excluded as content_leak", 1)[1].split("\n## ", 1)[0]
    return {line.split(" · ", 1)[0][2:] for line in section.splitlines() if line.startswith("- ev-")}


def test_no_gold_label_references_a_content_leak_excluded_item():
    leaked = content_leak_ids()
    assert OXFORD_LEAKED in leaked and len(leaked) == 8
    gold = json.loads(GOLD.read_text())["signals"]
    assert not leaked & set(gold)
    oxford = {eid: s for eid, s in gold.items() if eid.startswith("ev-oxford_ionics-")}
    assert oxford == {"ev-oxford_ionics-543ab30517": oxford["ev-oxford_ionics-543ab30517"]}
    assert len(oxford["ev-oxford_ionics-543ab30517"]) == 1
