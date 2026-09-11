"""`sct` is a second door into the tool functions the MCP server exposes.

What is asserted here is the door, not the room: the arguments map to the
same calls, the output is the frozen scanner+formatter contract with the
server-layer decorations (file-info, churn) removed, exit codes follow the
help text, and stdout is UTF-8 with LF on every platform.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scantool import cli

TESTS_DIR = Path(__file__).parent
GOLDEN_DIR = TESTS_DIR / "golden"
FIXTURE_DIR = GOLDEN_DIR / "fixture_dir"
PYTHON_SAMPLE = TESTS_DIR / "python" / "samples" / "basic.py"
MARKDOWN_SAMPLE = TESTS_DIR / "markdown" / "samples" / "basic.md"
FOCUS_MODULE = Path(cli.__file__).parent / "focus.py"


def run(*argv: str, capsys) -> tuple[str, str, int]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return captured.out, captured.err, code


def test_help_on_no_arguments_and_on_flag(capsys):
    for argv in ((), ("--help",), ("-h",)):
        out, _, code = run(*argv, capsys=capsys)
        assert code == 0
        assert out.startswith("sct — structure-first reader")
        assert "  sct scan " in out and "  sct focus " in out and "  sct search " in out


def test_usage_error_exits_2(capsys):
    for argv in (("scan",), ("scan", "--budget", "x"), ("focus", "only-one"), ("nope", "--bogus")):
        with pytest.raises(SystemExit) as exit_info:
            cli.main(list(argv))
        assert exit_info.value.code == 2


def test_scan_file_is_byte_identical_to_the_golden_contract(capsys):
    out, _, code = run("scan", str(PYTHON_SAMPLE), capsys=capsys)
    golden = (GOLDEN_DIR / "python.txt").read_text(encoding="utf-8")
    assert code == 0
    assert out.rstrip("\n") == golden.rstrip("\n")


def test_scan_markdown_is_byte_identical_to_golden(capsys):
    out, _, code = run("scan", str(MARKDOWN_SAMPLE), capsys=capsys)
    assert code == 0
    assert out.rstrip("\n") == (GOLDEN_DIR / "markdown.txt").read_text(encoding="utf-8").rstrip(
        "\n"
    )


def test_environment_lines_are_stripped(capsys):
    out, _, _ = run("scan", str(PYTHON_SAMPLE), str(FIXTURE_DIR), capsys=capsys)
    for marker in ("file-info", "edits/90d", "[ts:", "x/90d", "unchanged since"):
        assert marker not in out, marker
    assert "fixture_dir/ (" in out


def test_scan_json_is_one_document_without_file_info(capsys):
    out, _, code = run("scan", str(PYTHON_SAMPLE), "--json", capsys=capsys)
    document = json.loads(out)
    assert code == 0
    assert isinstance(document, dict) and document["file"] == str(PYTHON_SAMPLE)
    assert all(node["type"] != "file-info" for node in document["structures"])
    assert {"DatabaseManager"} <= {node["name"] for node in document["structures"]}


def test_scan_json_several_paths_is_a_list(capsys):
    out, _, _ = run("scan", str(PYTHON_SAMPLE), str(FIXTURE_DIR), "--json", capsys=capsys)
    documents = json.loads(out)
    assert isinstance(documents, list) and len(documents) == 2
    directory = documents[1]
    assert directory["coverage"]["files_seen"] == len(directory["files"])
    assert all(
        node["type"] != "file-info"
        for entry in directory["files"].values()
        for node in entry["structures"]
    )


def test_scan_missing_path_is_reported_and_exits_1(capsys):
    out, _, code = run("scan", str(PYTHON_SAMPLE), "no-such-file.py", capsys=capsys)
    assert code == 1
    assert "no such file or directory: no-such-file.py" in out
    assert "DatabaseManager" in out  # the existing path is still answered


def test_scan_json_keeps_stdout_pure(capsys):
    out, err, code = run("scan", "no-such-file.py", str(PYTHON_SAMPLE), "--json", capsys=capsys)
    assert code == 1
    assert json.loads(out)["file"] == str(PYTHON_SAMPLE)
    assert "no such file or directory" in err


def test_focus_hit_miss_and_ambiguity(capsys):
    out, _, code = run("focus", str(FOCUS_MODULE), "_walk", capsys=capsys)
    assert code == 0 and out.startswith("focus: _walk @")
    assert "43 | def _walk(" in out

    out, _, code = run("focus", str(FOCUS_MODULE), "no_such_node", capsys=capsys)
    assert code == 1 and "matches no node" in out

    out, _, code = run("focus", str(FOCUS_MODULE), "_", capsys=capsys)
    assert code == 1 and "is ambiguous" in out and "_resolve @" in out

    out, _, code = run("focus", "no-such-file.py", "x", capsys=capsys)
    assert code == 1 and "no such file" in out


def test_focus_matches_a_heading_substring(capsys):
    golden = (GOLDEN_DIR / "focus_markdown.txt").read_text(encoding="utf-8")
    leaf = golden.splitlines()[0].split("focus: ")[1].split(" @")[0].split(".")[-1]
    out, _, code = run("focus", str(MARKDOWN_SAMPLE), leaf[1:-1], capsys=capsys)
    assert code == 0
    assert out.rstrip("\n") == golden.rstrip("\n")


def test_search_text_names_type_json_and_no_match(capsys):
    out, _, code = run("search", str(FOCUS_MODULE.parent), "format_focus", capsys=capsys)
    assert code == 0 and "hits in" in out and "focus.py" in out

    out, _, code = run(
        "search", str(FOCUS_MODULE.parent), "^format_focus$", "--names", capsys=capsys
    )
    assert code == 0 and "- format_focus " in out

    out, _, code = run(
        "search", str(FOCUS_MODULE.parent), "format_focus", "--type", "function", capsys=capsys
    )
    assert code == 0 and "(module level)" not in out

    out, _, code = run("search", str(FOCUS_MODULE.parent), "format_focus", "--json", capsys=capsys)
    assert code == 0 and json.loads(out)["pattern"] == "format_focus"

    out, _, code = run("search", str(FOCUS_MODULE.parent), "zzqqxx_nowhere", capsys=capsys)
    assert code == 1 and out.startswith("<") and "No content matches" in out

    out, _, code = run("search", "no-such-dir", "x", capsys=capsys)
    assert code == 1 and "no such directory" in out


def test_directory_without_command_is_orientation(capsys):
    out, _, code = run(str(FIXTURE_DIR), capsys=capsys)
    assert code == 0
    assert "ENTRY POINTS" in out or "STRUCTURE" in out
    for marker in ("file-info", "edits/90d"):
        assert marker not in out

    out, _, code = run("no-such-dir", capsys=capsys)
    assert code == 1 and "no such directory" in out


def test_ascii_maps_scantools_glyphs_only(capsys):
    out, _, code = run("scan", str(FOCUS_MODULE), "--depth", "quick", "--ascii", capsys=capsys)
    assert code == 0 and "..." in out
    assert all(ord(char) < 128 for char in out), [c for c in out if ord(c) >= 128]
    assert cli.to_ascii("⟨…⟩ → ━ ─ é") == "<...> -> - - é"


def test_stdout_is_utf8_and_lf_even_when_the_console_is_not():
    """PYTHONIOENCODING=ascii:strict stands in for a legacy console code page:
    the CLI reconfigures its streams, so the em dash still arrives as UTF-8."""
    env = {**os.environ, "PYTHONIOENCODING": "ascii:strict"}
    result = subprocess.run(
        [sys.executable, "-m", "scantool.cli", "--help"], capture_output=True, env=env, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert "—".encode() in result.stdout
    assert b"\r\n" not in result.stdout


def test_help_opens_with_the_three_lines_every_agent_needs(capsys):
    out, _, _ = run("--help", capsys=capsys)
    first = [line.strip() for line in out.splitlines()[2:5]]
    assert first[0].startswith("sct <dir>")
    assert first[1].startswith("sct scan <path>")
    assert first[2].startswith("sct focus <path> <name>")


def test_scan_reads_a_path_list_from_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{PYTHON_SAMPLE}\n\n{MARKDOWN_SAMPLE}\n"))
    out, _, code = run("scan", "-", "--depth", "quick", capsys=capsys)
    assert code == 0
    assert "DatabaseManager" in out and "basic.md (" in out


def test_scan_stdin_content_under_a_name(monkeypatch, capsys):
    """`git show REF:path | sct scan - --as path`: bytes scanned as that file."""
    monkeypatch.setattr("sys.stdin", io.StringIO(PYTHON_SAMPLE.read_text()))
    out, _, code = run("scan", "-", "--as", "lib/basic.py", capsys=capsys)
    golden = (GOLDEN_DIR / "python.txt").read_text(encoding="utf-8")
    assert code == 0
    assert out.rstrip("\n") == golden.rstrip("\n")

    monkeypatch.setattr("sys.stdin", io.StringIO(PYTHON_SAMPLE.read_text()))
    out, _, code = run("scan", "-", "--as", "lib/basic.py", "--json", capsys=capsys)
    assert code == 0 and json.loads(out)["file"] == "lib/basic.py"


def test_focus_on_stdin_content(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(PYTHON_SAMPLE.read_text()))
    out, _, code = run("focus", "-", "--as", "basic.py", "DatabaseManager.query", capsys=capsys)
    golden = (GOLDEN_DIR / "focus_python.txt").read_text(encoding="utf-8")
    assert code == 0
    assert out.rstrip("\n") == golden.rstrip("\n")


def test_stdin_usage_errors_exit_2(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert cli.main(["scan", "-"]) == 2  # `-` with nothing on stdin
    monkeypatch.setattr("sys.stdin", io.StringIO("x"))
    assert cli.main(["scan", str(PYTHON_SAMPLE), "--as", "a.py"]) == 2  # --as without `-`
    monkeypatch.setattr("sys.stdin", io.StringIO("x"))
    assert cli.main(["focus", "-", "name"]) == 2  # `-` without --as
    _, err, _ = run("--help", capsys=capsys)  # drain
