"""
Golden-output tests: freeze the default output format.

The output format IS the API for LLM consumers (M2b: agents consume it
directly and uncritically — format drift is behavior drift in the consumer).
The snapshots freeze the scanner+formatter layer with default settings,
mirroring the MCP tools, but without the environment-dependent parts:

- file-info (mtime/size follows the checkout) is omitted
- git signals (churn, line_edits) and delta memory live in the server
  layer and are therefore out of scope

A deliberate format change requires a deliberate snapshot update:

    UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py
"""

import os
from pathlib import Path

import pytest

from scantool.directory_formatter import DirectoryFormatter
from scantool.focus import format_focus
from scantool.formatter import TreeFormatter
from scantool.scanner import FileScanner

TESTS_DIR = Path(__file__).parent
GOLDEN_DIR = TESTS_DIR / "golden"

# One representative sample file per language.
SAMPLES = {
    "c": "c_cpp/samples/basic.c",
    "cpp": "c_cpp/samples/basic.cpp",
    "csharp": "csharp/samples/Basic.cs",
    "css": "css/basic.css",
    "go": "go/samples/basic.go",
    "html": "html/basic.html",
    "java": "java/samples/Basic.java",
    "markdown": "markdown/samples/basic.md",
    "php": "php/samples/basic.php",
    "python": "python/samples/basic.py",
    "ruby": "ruby/samples/basic.rb",
    "rust": "rust/samples/basic.rs",
    "scss": "scss/basic.scss",
    "sql": "sql/samples/basic.sql",
    "swift": "swift/samples/basic.swift",
    "text": "text/samples/basic.txt",
    "typescript": "typescript/samples/basic.ts",
    "zig": "zig/samples/basic.zig",
}

UPDATE_HINT = (
    "The default output is the contract with LLM consumers. Is the format "
    "change deliberate? Update the snapshots with: "
    "UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py"
)


def _render_file(sample: Path) -> str:
    structures = FileScanner().scan_file(str(sample), include_file_metadata=False)
    assert structures, f"no structure for sample: {sample}"
    return TreeFormatter().format(str(sample), structures)


def _render_directory(fixture_dir: Path) -> str:
    results = FileScanner().scan_directory(str(fixture_dir))
    assert results, f"no files scanned in: {fixture_dir}"
    stripped = {
        path: [node for node in (nodes or []) if node.type != "file-info"]
        for path, nodes in results.items()
    }
    # Server-defaults for katalogvisning: kompakt inline-format med glimt
    formatter = DirectoryFormatter(include_structures=True, flatten_structures=True)
    return formatter.format(str(fixture_dir), stripped)


def _assert_matches_golden(name: str, actual: str) -> None:
    golden = GOLDEN_DIR / f"{name}.txt"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.write_text(actual + "\n", encoding="utf-8")
        return
    assert golden.exists(), f"golden-fil mangler: {golden}. {UPDATE_HINT}"
    expected = golden.read_text(encoding="utf-8")
    assert actual + "\n" == expected, UPDATE_HINT


@pytest.mark.parametrize("lang", sorted(SAMPLES))
def test_scan_file_output_is_frozen(lang):
    _assert_matches_golden(lang, _render_file(TESTS_DIR / SAMPLES[lang]))


def test_scan_directory_output_is_frozen():
    _assert_matches_golden("directory", _render_directory(GOLDEN_DIR / "fixture_dir"))


def _render_focus(sample: Path, focus: str) -> str:
    structures = FileScanner().scan_file(str(sample), include_file_metadata=False)
    assert structures, f"no structure for sample: {sample}"
    source_lines = sample.read_text(encoding="utf-8").split("\n")
    return format_focus(str(sample), structures, source_lines, focus)


def test_focus_python_method_is_frozen():
    _assert_matches_golden(
        "focus_python",
        _render_focus(TESTS_DIR / SAMPLES["python"], "DatabaseManager.query"))


def test_focus_markdown_heading_is_frozen():
    _assert_matches_golden(
        "focus_markdown",
        _render_focus(TESTS_DIR / SAMPLES["markdown"], "Quick Start"))
