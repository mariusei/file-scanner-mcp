"""scan_file_content is the same reader as scan_file, fed bytes instead of a
path: same saliency tiers, same budget, same focus. Until this test existed
it returned bare structure with no skeletons and no focus, which is why the
study's agents had to write git blobs to scratch files to read them.
"""

from pathlib import Path

from scantool import server
from scantool.scanner import FileScanner

TESTS_DIR = Path(__file__).parent
GOLDEN_DIR = TESTS_DIR / "golden"
PYTHON_SAMPLE = TESTS_DIR / "python" / "samples" / "basic.py"


def _text(result) -> str:
    return "".join(part.text for part in result)


def _without_file_info(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith("- file-info:"))


def test_content_scan_matches_the_golden_contract():
    """Bytes in, the frozen scanner+formatter text out; the file-info record
    is the only addition and does not widen the header range."""
    text = _text(
        server.scan_file_content(content=PYTHON_SAMPLE.read_text(), filename=str(PYTHON_SAMPLE))
    )
    golden = (GOLDEN_DIR / "python.txt").read_text(encoding="utf-8")
    assert _without_file_info(text) == golden.rstrip("\n")


def test_content_scan_and_file_scan_agree_node_for_node():
    scanner = FileScanner()
    by_path = scanner.scan_file(str(PYTHON_SAMPLE), include_file_metadata=False)
    by_content = scanner.scan_content(PYTHON_SAMPLE.read_bytes(), str(PYTHON_SAMPLE))
    assert by_path and by_content
    for a, b in zip(by_path, by_content):
        assert (a.name, a.start_line, a.end_line, a.code_skeleton) == (
            b.name,
            b.start_line,
            b.end_line,
            b.code_skeleton,
        )


def test_budget_and_depth_reduce_content_output():
    content = PYTHON_SAMPLE.read_text()
    full = _text(server.scan_file_content(content=content, filename="basic.py"))
    # The sample's skeletons are small; 30 tokens is below their estimate,
    # "quick" (300) is not — the same thresholds scan_file shows on this file.
    budgeted = _text(server.scan_file_content(content=content, filename="basic.py", budget=30))
    quick = _text(server.scan_file_content(content=content, filename="basic.py", depth="quick"))
    assert len(budgeted) < len(full)
    assert quick == full
    assert "DatabaseManager" in budgeted  # names survive; only excerpts degrade
    # What the budget cut is said, not hidden: counted in the coverage line
    # and marked on the node with the lines focus= would show
    assert full.splitlines()[0] == "<1 file seen, 14 structures shown>"
    assert budgeted.splitlines()[0].endswith(" elided (budget)>")
    assert "⟨…⟩ +" in budgeted
    elided = sum(1 for line in budgeted.splitlines() if line.strip().startswith("⟨…⟩ +"))
    assert (
        budgeted.splitlines()[0] == f"<1 file seen, 14 structures shown, {elided} elided (budget)>"
    )


def test_focus_on_content_matches_the_focus_golden():
    golden = (GOLDEN_DIR / "focus_python.txt").read_text(encoding="utf-8")
    focus = golden.splitlines()[0].split("focus: ")[1].split(" @")[0]
    text = _text(
        server.scan_file_content(
            content=PYTHON_SAMPLE.read_text(), filename=str(PYTHON_SAMPLE), focus=focus
        )
    )
    # the server opens with the address; the body is the frozen contract
    assert text.splitlines()[0] == f"{PYTHON_SAMPLE}::{focus} (24-26)"
    assert _without_file_info(text).splitlines()[1:] == golden.splitlines()[1:]


def test_focus_miss_on_content_names_the_top_level_nodes():
    text = _text(
        server.scan_file_content(content="def a():\n    pass\n", filename="x.py", focus="zzz")
    )
    assert text.startswith("focus 'zzz' matches no node")
    assert "a" in text
