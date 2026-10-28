"""Markdown rendering guard (stdlib only, offline): tables and fences must render on GitHub.

A table row separated from its table by a blank line renders as plain text on GitHub, so every tracked .md file is
checked for that and for the other ways a table or fence silently breaks. Fenced code and mermaid blocks are skipped.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r"^\s*(```+|~~~+)")
DELIMITER = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__"}


def markdown_files() -> list[Path]:
    shown = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True)
    if shown.returncode == 0 and shown.stdout.split():
        return [ROOT / f for f in shown.stdout.split()]
    return [p for p in ROOT.rglob("*.md")
            if not EXCLUDED_DIRS & set(p.relative_to(ROOT).parts) and "data/raw" not in p.as_posix()]


def column_count(line: str) -> int:
    """Cells in a table row. `\\|` is an escaped pipe; GitHub splits on any other pipe, even inside `inline code`."""
    s = line.strip().replace("\\|", "XX")
    parts = s.split("|")
    if s.startswith("|"):
        parts = parts[1:]
    if s.endswith("|"):
        parts = parts[:-1]
    return len(parts)


def audit(text: str) -> list[str]:
    """Rendering problems in one Markdown document, as 'line N: message' strings."""
    lines = text.split("\n")
    problems, fence, fence_line = [], None, 0
    in_table, header_cols = False, 0
    for i, line in enumerate(lines, 1):
        marker = FENCE.match(line)
        if marker:
            if fence is None:
                fence, fence_line = marker.group(1)[:3], i
            elif line.strip().startswith(fence):
                fence = None
            in_table = False
            continue
        if fence:
            continue
        if line.lstrip().startswith("|"):
            if not in_table:
                following = lines[i] if i < len(lines) else ""
                if DELIMITER.match(following) and "|" in following:
                    in_table, header_cols = True, column_count(line)
                else:
                    problems.append(f"line {i}: stray '|' line outside a table: {line[:60]}")
            elif not DELIMITER.match(line) and column_count(line) != header_cols:
                problems.append(f"line {i}: {column_count(line)} columns, header has {header_cols}: {line[:60]}")
        else:
            if in_table and line.strip() == "":
                nxt = i
                while nxt < len(lines) and lines[nxt].strip() == "":
                    nxt += 1
                starts_new_table = nxt + 1 < len(lines) and bool(DELIMITER.match(lines[nxt + 1]))
                if nxt < len(lines) and lines[nxt].lstrip().startswith("|") and not starts_new_table:
                    problems.append(f"line {i}: blank line inside a table (table continues at line {nxt + 1})")
            in_table = False
    if fence:
        problems.append(f"line {fence_line}: code fence {fence} is never closed")
    return problems


@pytest.mark.parametrize("path", markdown_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_tracked_markdown_renders(path):
    assert audit(path.read_text()) == []


def test_every_tracked_markdown_file_is_checked():
    names = {p.relative_to(ROOT).as_posix() for p in markdown_files()}
    assert {"README.md", "CLAUDE.md", "docs/case_selection.md", "docs/architecture.md", "docs/findings.md"} <= names


# --- the checker itself ------------------------------------------------------------------------------------------------

GOOD = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"


def test_clean_table_passes_and_two_tables_may_be_separated_by_a_blank_line():
    assert audit(GOOD) == []
    assert audit(GOOD + "\ntext\n\n" + GOOD) == []
    assert audit(GOOD + "\n" + GOOD) == []  # a new header plus delimiter row starts a fresh table


def test_blank_line_inside_a_table_is_caught():
    problems = audit("| A | B |\n|---|---|\n| 1 | 2 |\n\n| 3 | 4 |\n")
    assert any("blank line inside a table" in p for p in problems)
    assert any("stray '|' line" in p for p in problems)  # the row that falls out renders as plain text


def test_wrong_column_count_is_caught_and_escaped_pipes_are_not_separators():
    assert any("3 columns" in p for p in audit("| A | B |\n|---|---|\n| 1 | 2 | 3 |\n"))
    assert audit("| A | B |\n|---|---|\n| a \\| b | 2 |\n") == []
    assert any("3 columns" in p for p in audit("| A | B |\n|---|---|\n| `a | b` | 2 |\n"))  # GitHub splits here


def test_stray_pipe_line_and_unclosed_fence_are_caught():
    assert any("stray" in p for p in audit("text\n| 1 | 2 |\n"))
    assert any("never closed" in p for p in audit("```python\ncode\n"))
    assert audit("```python\ncode\n```\n") == [] and audit("~~~\ncode\n~~~\n") == []


def test_fenced_code_and_mermaid_are_skipped():
    assert audit("```mermaid\nflowchart TD\n    A -->|\"x\"| B\n| not a table\n```\n") == []
    assert audit("```\n| 1 | 2 |\n\n| 3 | 4 |\n```\n") == []
