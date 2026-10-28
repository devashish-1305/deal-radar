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
ARROW = re.compile(r"(~~~|-\.->(?:\|\"[^\"]*\"\|)?|-->(?:\|\"[^\"]*\"\|)?)")
MAX_LINE_CHARS = 22  # design target is ~18 characters per line; small tolerance for unbreakable words
CLASSDEF = re.compile(r"^\s*classDef (\w+) (.+)$", re.M)
CLASS = re.compile(r"^\s*class ([\w,]+) (\w+)\s*$", re.M)
B1_DIAMONDS = ["Company changed this week?", "Document already processed?", "Relevant to ownership or deals?",
               "Passes point-in-time checks?", "Sale-intent language?", "Quote verbatim, right company, valid type?",
               "PE-backed or shortlisted?", "Intent found?"]


def diagrams() -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", DOC, re.S)


def read_json(path):
    return json.loads(Path(path).read_text())


def visible_lines(label: str) -> list[str]:
    return [re.sub(r"</?b>", "", part) for part in label.split("<br/>")]


def visible(label: str) -> str:
    return " ".join(visible_lines(label))


def parse(block: str):
    """(nodes {id: (kind, label)}, edges [(src, arrow, dst, label)]) for one Mermaid block."""
    nodes = {m.group(1): ("box", m.group(2)) for m in re.finditer(r'^\s*(\w+)\["([^"]*)"\]', block, re.M)}
    nodes |= {m.group(1): ("diamond", m.group(2)) for m in re.finditer(r'^\s*(\w+)\{"([^"]*)"\}', block, re.M)}
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


def subgraphs(block: str) -> dict:
    return {m.group(1): (m.group(2), m.group(3)) for m in
            re.finditer(r'subgraph (\w+)\["([^"]*)"\]\n(.*?)\n    end', block, re.S)}


def classes(block: str) -> tuple[dict, dict]:
    defs = {m.group(1): m.group(2) for m in CLASSDEF.finditer(block)}
    assigned = {n: cls for ids, cls in CLASS.findall(block) for n in ids.split(",")}
    return defs, assigned


# --- all three diagrams: structure and styling ---------------------------------------------------------------------

def test_three_diagrams_each_flowchart_td_without_comments():
    blocks = diagrams()
    assert len(blocks) == 3
    for b in blocks:
        assert b.startswith("flowchart TD") and "%%" not in b


def test_every_node_is_classed_with_explicit_colours_and_b_is_dashed():
    a, b1, b2 = diagrams()
    for idx, block in enumerate((a, b1, b2)):
        nodes, _ = parse(block)
        defs, assigned = classes(block)
        assert set(assigned) == set(nodes), set(nodes) ^ set(assigned)
        for cls, spec in defs.items():
            assert all(k in spec for k in ("fill:#", "stroke:#", "stroke-width:2px", "color:#")), cls
        used = set(assigned.values())
        assert used <= set(defs)
        for cls in used:
            assert ("stroke-dasharray" in defs[cls]) == (idx > 0), (idx, cls)  # A solid; B1 and B2 dashed
    assert set(classes(a)[1].values()) <= {"built", "ai", "decision", "excluded"}


def test_every_diamond_has_labelled_yes_no_edges_and_no_orphans():
    for block in diagrams():
        nodes, edges = parse(block)
        subs = subgraphs(block)
        for nid, (kind, _) in nodes.items():
            out = [e for e in edges if e[0] == nid and e[1] != "~~~"]
            if kind == "diamond":
                assert sorted(e[3] for e in out) == ["no", "yes"], nid
            assert [e for e in edges if nid in (e[0], e[2])], f"orphan {nid}"
        for src, _, dst, _ in edges:
            assert {src, dst} <= set(nodes) | set(subs)


def test_visible_label_lines_are_short():
    for block in diagrams():
        for nid, (_, label) in parse(block)[0].items():
            for line in visible_lines(label):
                assert len(line) <= MAX_LINE_CHARS, (nid, line)


# --- Architecture A: every number comes from a committed file ---------------------------------------------------------

def evidence_log_missed() -> int:
    return int(re.search(r"would have missed:\*\* (\d+) of the", (ROOT / "docs" / "evidence_log.md").read_text()).group(1))


def expected_a_numbers() -> set[int]:
    d = build_findings.load_all()
    f = build_findings.funnel(d)
    companies, _, pairs = load_cases(ROOT / "data" / "cases")
    ex = read_json(PROCESSED / "charts" / "extraction_compare.json")
    numbers = {len(companies), len(pairs), f["registry_events"], f["pages_opened"], f["usable_dated"],
               f["modified_after_anchor"], f["content_leak"], evidence_log_missed(),
               round(ex["models"]["sonnet"]["verbatim_quote_rate"] * 100),
               round(ex["sonnet_after_prd_rules"]["precision"] * 100), round(ex["sonnet_after_prd_rules"]["recall"] * 100),
               len(read_json(PROCESSED / "features.json")),
               ex["models"]["sonnet"]["false_direct_intent"], ex["models"]["haiku"]["false_direct_intent"]}
    for variant in ("holding_only", "full"):
        numbers |= set(build_findings.wtl(d["comparisons"][variant]))
    return numbers


def test_every_number_in_architecture_a_appears_in_its_source_file():
    a = diagrams()[0]
    labels = " ".join(visible(label) for _, label in parse(a)[0].values())  # labels only (not node ids such as A1)
    assert {int(n) for n in re.findall(r"\d+", labels)} == expected_a_numbers()
    d = build_findings.load_all()
    full, hold = build_findings.wtl(d["comparisons"]["full"]), build_findings.wtl(d["comparisons"]["holding_only"])
    assert f"{full[0]}/{full[1]}/{full[2]} vs {hold[0]}/{hold[1]}/{hold[2]}" in labels


def test_architecture_a_decisions_loops_and_model_choice():
    a = diagrams()[0]
    nodes, edges = parse(a)
    text = {k: visible(v[1]) for k, v in nodes.items()}
    ex = read_json(PROCESSED / "charts" / "extraction_compare.json")["models"]
    # model choice: both false-intent values come from extraction_compare.json; accuracy sits on the AI extracts node
    assert text["CHOSEN"] == f"Sonnet chosen {ex['sonnet']['false_direct_intent']} false intent signals (Haiku: {ex['haiku']['false_direct_intent']})"
    assert "84% precision" in text["AI"] and "89% recall" in text["AI"] and "100% verbatim" in text["AI"]
    assert not re.search(r"precision|recall", text["CHOSEN"])
    assert text["EXCL"] == f"Excluded 32 modified after 8 content leak ({evidence_log_missed()} passed date filters)"
    # retry self-loop, failure, and the model-used feedback edge
    assert ("AI", "-.->", "AI", "invalid JSON: retry once") in edges
    assert ("AI", "-->", "FAIL", "still invalid") in edges
    assert ("CHOSEN", "-.->", "AI", "model used") in edges
    assert ("OUTQ", "-->", "REJ", "no") in edges and ("LEAKQ", "-->", "EXCL", "no") in edges
    assert {e[0] for e in edges if e[2] == "FULL"} == {"RULES"} and {e[0] for e in edges if e[2] == "CLOCK"} == {"RULES"}
    assert {e[0] for e in edges if e[2] == "CMPR"} == {"FULL", "CLOCK"}
    assert "Data collected for validation only. Web search was the test method, not the production plan." in DOC


# --- Architecture B1: weekly processing --------------------------------------------------------------------------------

def test_b1_diamonds_in_order_and_recompute_clocks_not_cached_scores():
    b1 = diagrams()[1]
    nodes, edges = parse(b1)
    order = [visible(v[1]).replace("  ", " ") for k, v in sorted(nodes.items(), key=lambda kv: b1.index(f"{kv[0]}{{")
                                                                   if f"{kv[0]}{{" in b1 else 10**9) if v[0] == "diamond"]
    assert order == B1_DIAMONDS
    assert not [k for k, v in nodes.items() if "reuse cached score" in visible(v[1]).lower()]
    (recomp,) = [e for e in edges if e[0] == "Q1" and e[3] == "no"]
    assert "Recompute clocks only (reuse cached signals)" == visible(nodes[recomp[2]][1])
    assert (recomp[2], "-->", "FEAT", None) in edges
    assert ("Q1", "-->", "Q2", "yes") in edges and ("Q5", "-->", "STRONG", "yes") in edges and ("Q5", "-->", "CHEAP", "no") in edges


def test_b1_source_group_is_left_to_right_and_linked_as_a_whole():
    b1 = diagrams()[1]
    nodes, edges = parse(b1)
    label, body = subgraphs(b1)["SRC"]
    assert "direction LR" in body
    inner = set(re.findall(r'^\s*(\w+)\["', body, re.M))
    assert inner == {"FREE", "BROAD", "SEL", "LIB"}
    assert ("SRC", "-->", "Q1", None) in edges
    assert not [e for e in edges if (e[0] in inner or e[2] in inner) and e[1] != "~~~"]


# --- Architecture B2: feedback loops ---------------------------------------------------------------------------------------

def test_b2_five_closed_loops_with_dotted_returns():
    b2 = diagrams()[2]
    nodes, edges = parse(b2)
    subs = subgraphs(b2)
    # Defined 5 -> 1 because Mermaid places subgraphs in reverse definition order: they render left to right as 1..5.
    assert [v[0] for v in subs.values()] == ["5. Business check", "4. Extraction quality", "3. Source gate",
                                             "2. Recalibration", "1. Weekly refresh"]
    for sid, (_, body) in subs.items():
        ids = set(re.findall(r'^\s*(\w+)[\[{]"', body, re.M))
        inside = [e for e in edges if e[0] in ids and e[2] in ids]
        assert any(e[1] == "-.->" and e[3] for e in inside), f"{sid} has no labelled dotted return edge"
        assert not [e for e in edges if (e[0] in ids) != (e[2] in ids)], f"{sid} links outside itself"


def test_request_logs_link_only_inside_the_business_check_loop():
    a, b1, b2 = diagrams()
    assert "LOGS" not in a and "LOGS" not in b1
    nodes, edges = parse(b2)
    assert "LOGS[" in subgraphs(b2)["L5"][1]
    assert [e for e in edges if "LOGS" in (e[0], e[2])] == [("LOGS", "-->", "RR", LOGS_LABEL)]
    assert "evaluation only" in visible(nodes["LOGS"][1])


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
