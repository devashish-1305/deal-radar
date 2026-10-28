"""docs/architecture.md: diagram numbers match their source files; structural checks (mmdc is not available)."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_findings  # noqa: E402

from deal_radar.cases import load_cases  # noqa: E402

DOC = (ROOT / "docs" / "architecture.md").read_text()
PROCESSED = ROOT / "data" / "processed"
LOGS_LABEL = "Solely to measure research readiness. Never a feature or training signal."
ARROW = re.compile(r"(~~~|-\.->(?:\|\"[^\"]*\"\|)?|-->)")


def diagrams() -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", DOC, re.S)


def read_json(path):
    return json.loads(Path(path).read_text())


def nodes_and_edges(block: str):
    nodes = {m.group(1): m.group(2) for m in re.finditer(r'^\s*(\w+)\["([^"]*)"\]', block, re.M)}
    edges = []
    for line in block.splitlines():
        parts = ARROW.split(line.strip())
        if len(parts) < 3 or line.strip().startswith(("class", "subgraph")):
            continue
        for i in range(1, len(parts), 2):
            src, dst = parts[i - 1].strip().split()[-1], parts[i + 1].strip().split()[0]
            label = re.search(r'\|"([^"]*)"\|', parts[i])
            edges.append((src, parts[i].split("|")[0], dst, label.group(1) if label else None))
    return nodes, edges


# --- Architecture A: every number comes from a committed file ------------------------------------------------------

def expected_a_numbers() -> set[int]:
    d = build_findings.load_all()
    f = build_findings.funnel(d)
    companies, _, pairs = load_cases(ROOT / "data" / "cases")
    ex = read_json(PROCESSED / "charts" / "extraction_compare.json")
    log = (ROOT / "docs" / "evidence_log.md").read_text()
    missed = int(re.search(r"would have missed:\*\* (\d+) of the", log).group(1))
    wtl = build_findings.wtl
    numbers = {len(companies), len(pairs), f["registry_events"], f["pages_opened"], f["usable_dated"],
               f["modified_after_anchor"], f["content_leak"], missed,
               round(ex["models"]["sonnet"]["verbatim_quote_rate"] * 100),
               round(ex["sonnet_after_prd_rules"]["precision"] * 100), round(ex["sonnet_after_prd_rules"]["recall"] * 100),
               len(read_json(PROCESSED / "features.json"))}
    for variant in ("holding_only", "full"):
        numbers |= set(wtl(d["comparisons"][variant]))
    return numbers


def test_every_number_in_architecture_a_appears_in_its_source_file():
    a = diagrams()[0]
    labels = " ".join(nodes_and_edges(a)[0].values())  # node labels only (not node ids such as A1)
    shown = {int(n) for n in re.findall(r"\d+", labels)}
    assert shown == expected_a_numbers()
    d = build_findings.load_all()
    full, hold = build_findings.wtl(d["comparisons"]["full"]), build_findings.wtl(d["comparisons"]["holding_only"])
    assert f"Clock only {hold[0]}/{hold[1]}/{hold[2]}" in a and f"Full {full[0]}/{full[1]}/{full[2]}" in a


def test_architecture_a_labels_and_caption():
    a = diagrams()[0]
    assert a.startswith("flowchart TD")
    assert "4 would have passed date filters" in a
    assert "Data collected for validation only. Web search was the test method, not the production plan." in DOC
    assert "<br/>" in a


# --- Architecture B: structure -----------------------------------------------------------------------------------------

def test_architecture_b_structure():
    b = diagrams()[1]
    assert b.startswith("flowchart TD") and "%%" not in b
    nodes, edges = nodes_and_edges(b)
    subgraphs = dict(re.findall(r'subgraph (\w+)\["([^"]*)"\]', b))
    assert subgraphs == {"ACQ": "Data acquisition", "SIG": "Signal intelligence", "DEC": "Decision and feedback"}
    # Data acquisition is laid out left to right and linked to Signal intelligence as a whole subgraph.
    acq = b.split("subgraph ACQ")[1].split("    end")[0]
    assert "direction LR" in acq
    acq_nodes = set(re.findall(r'^\s*(\w+)\["', acq, re.M))
    assert acq_nodes == {"FREE", "BROAD", "SEL", "LIB"}
    assert ("ACQ", "-->", "SIG", None) in edges and ("SIG", "-->", "DEC", None) in edges
    assert not [e for e in edges if (e[0] in acq_nodes or e[2] in acq_nodes) and e[1] != "~~~"]
    # Every edge endpoint exists.
    for src, _, dst, _ in edges:
        assert {src, dst} <= set(nodes) | set(subgraphs)
    # All nodes dashed, at most 3 lines per node.
    assert "classDef dashed stroke-dasharray" in b
    classed = set(re.search(r"^\s*class ([\w,]+) dashed", b, re.M).group(1).split(","))
    assert classed == set(nodes)
    assert all(len(label.split("<br/>")) <= 3 for label in nodes.values())


def test_request_logs_link_only_to_the_evaluation_loop():
    b = diagrams()[1]
    nodes, edges = nodes_and_edges(b)
    dec = b.split("subgraph DEC")[1].split("    end")[0]
    assert "LOGS[" in dec and "LOGS[" not in b.split("subgraph DEC")[0]
    touching = [e for e in edges if "LOGS" in (e[0], e[2])]
    assert touching == [("LOGS", "-.->", "EVAL", LOGS_LABEL)]
    assert "Evaluation only" in nodes["LOGS"]


# --- supporting sections ---------------------------------------------------------------------------------------------------

def test_why_each_source_numbers_match_the_data():
    d = build_findings.load_all()
    f = build_findings.funnel(d)
    intent_rows = sum(bool(r["features"]["intent_present"]) for r in d["rows"])
    _, transactions, _ = load_cases(ROOT / "data" / "cases")
    weak_wins = sum(c["outcome"] == "win" and c["category"] == "weak (debt-only)" for c in d["comparisons"]["full"])
    losses = sum(c["outcome"] == "loss" for c in d["comparisons"]["full"])
    for expected in (f"{intent_rows} of {len(d['rows'])} snapshot rows",
                     f"{f['usable_dated']} usable dated articles vs {f['registry_usable_before_anchor']} usable registry events",
                     f"{f['officer_events_with_occupation']} of {f['officer_events']} officer events",
                     f"only {len(transactions)} labelled deals",
                     f"{weak_wins} wins rest on them alone and all {losses} losses"):
        assert expected in DOC, expected


def test_no_invented_figures_or_scraping_and_readme_links_the_doc():
    for phrase in ("Licensed data only, no scraping", "as-of (historical) snapshots", "gated by backtest lift"):
        assert phrase in DOC
    for section in ("Design rules", "Why each source", "Phased rollout", "Assumptions to validate"):
        assert f"## {section}" in DOC
    assert "**nothing in B is claimed as built**" in DOC
    assert "docs/architecture.md" in (ROOT / "README.md").read_text()
