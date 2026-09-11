"""Output is valid input: every address the CLI prints must be accepted back
by `sct focus` and hit exactly that structure (brief §9 item 1, decided as
the sober reading in §9d). The test composes addresses the way an agent
would, from the text of a scan — `<file line>::<Qualified.name>`, headings
quoted or by ID tag — and feeds each one back.
"""

import json
import re
from pathlib import Path

import pytest

from scantool import cli

TESTS_DIR = Path(__file__).parent
PYTHON_SAMPLE = TESTS_DIR / "python" / "samples" / "basic.py"
MARKDOWN_SAMPLE = TESTS_DIR / "markdown" / "samples" / "basic.md"
STRUCTURE_LINE = re.compile(r"^( *)- (.+?) (?:\(|@)")  # indent, name; stops at signature or @line
AT_LINE = re.compile(r" @(\d+)(?:\s|$)")


def run(*argv, capsys):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return captured.out, captured.err, code


def _synthetic_names(path: Path, capsys) -> set[str]:
    out, _, _ = run("scan", str(path), "--json", capsys=capsys)

    def walk(nodes):
        for node in nodes:
            if node.get("synthetic"):
                yield node["name"]
            yield from walk(node.get("children", []))

    return set(walk(json.loads(out)["structures"]))


def _addresses_from_scan(path: Path, quote: bool, capsys) -> list[tuple[str, int]]:
    """(address, start line) for every non-synthetic structure line of a scan,
    composed as the help text says: file line :: dotted names by indentation."""
    synthetic = _synthetic_names(path, capsys)
    out, _, code = run("scan", str(path), capsys=capsys)
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("<1 file seen")
    file_line = lines[1].split(" (")[0]
    assert file_line == str(path)  # the path as typed, not the base name
    stack: list[tuple[int, str]] = []
    found = []
    for line in lines[2:]:
        match = STRUCTURE_LINE.match(line)
        if not match:
            continue
        indent, name = len(match.group(1)), match.group(2)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, name))
        if name in synthetic:
            continue
        start = int(AT_LINE.search(line).group(1))
        qualified = f'"{name}"' if quote else ".".join(n for _, n in stack)
        found.append((f"{file_line}::{qualified}", start))
    assert found
    return found


@pytest.mark.parametrize("sample,quote", [(PYTHON_SAMPLE, False), (MARKDOWN_SAMPLE, True)])
def test_every_printed_address_is_accepted_back_by_focus(sample, quote, capsys):
    for address, start in _addresses_from_scan(sample, quote, capsys):
        out, err, code = run("focus", address, capsys=capsys)
        assert code == 0, (address, out, err)
        header = out.splitlines()[0]
        assert header.startswith(f"{sample}::") and f" ({start}-" in header, (address, header)
        if not quote:
            assert header == f"{address} ({start}-{header.rsplit('-', 1)[1].rstrip(')')})"


def test_next_trailer_is_a_focus_call_that_hits(capsys):
    out, _, _ = run("scan", str(PYTHON_SAMPLE), "--budget", "30", capsys=capsys)
    trailer = out.splitlines()[-1]
    assert trailer.startswith("next: sct focus ")
    assert out.splitlines()[0].endswith(" elided (budget)>")
    address = trailer.removeprefix("next: sct focus ")
    focus, _, code = run("focus", address, capsys=capsys)
    assert code == 0 and focus.splitlines()[0].startswith(address + " (")


def test_heading_with_an_id_tag_is_addressed_by_the_tag(tmp_path, capsys):
    doc = tmp_path / "notes.md"
    doc.write_text("# Intro\n\n## [DEV-L17] Contracts that survive\n\ntext\n\n## Other\n\nmore\n")
    out, _, code = run("focus", str(doc), "DEV-L17", capsys=capsys)
    assert code == 0 and out.splitlines()[0] == f"{doc}::DEV-L17 (3-6)"
    again, _, code = run("focus", f"{doc}::DEV-L17", capsys=capsys)
    assert code == 0 and again == out
    other, _, code = run("focus", f'{doc}::"Other"', capsys=capsys)
    assert code == 0 and other.splitlines()[0].startswith(f'{doc}::"Other" (7-')


def test_search_leads_are_path_line(capsys):
    out, _, code = run("search", str(TESTS_DIR / "golden" / "fixture_dir"), "push", capsys=capsys)
    assert code == 0
    leads = [line for line in out.splitlines() if line.startswith("leads ")]
    for line in leads:
        assert re.search(r"\.\w+:\d+", line) and "@" not in line, line


def test_address_form_usage_errors(capsys):
    assert cli.main(["focus", "no-separator-here"]) == 2
    assert "path::Qualified.name" in capsys.readouterr().err
