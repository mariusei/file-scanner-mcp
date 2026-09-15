"""The MCP tools `surface`, `overlap`, `callers` and `resolve` in server.py
close the gap the field study found: a client with only the scantool MCP
server registered (no shell, so no `sct`) could not reach these four
capabilities at all, even though `sct surface` was "the most useful single
call" in three of the study's blank-agent runs.

Each tool is a thin wrapper around the same modules `sct surface` / `sct
overlap` / `sct callers` / `sct resolve` already call (surface.py,
overlap.py, callers.py, resolve.py) — no new logic. The parity tests below
are the proof: the MCP tool's text answer on a fixture must match what the
CLI prints for the equivalent command on the same fixture.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

from scantool import cli, server

sys.path.insert(0, str(Path(__file__).parent))
from test_callers_resolve import CODE, V1, V2, _git  # noqa: E402
from test_overlap import repo as overlap_repo  # noqa: E402, F401 (used as a fixture by name)
from test_surface import PACKAGE, _write  # noqa: E402
from test_surface import package as surface_package  # noqa: E402, F401 (used as a fixture by name)

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def run(*argv, capsys):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return captured.out, captured.err, code


# --------------------------------------------------------------------------- surface


def test_surface_matches_cli(surface_package, capsys):  # noqa: F811 (imported fixture)
    out, _, code = run("surface", "pkg", capsys=capsys)
    assert code == 0

    result = server.surface("pkg")
    assert len(result) == 1
    assert result[0].text == out.rstrip("\n")


def test_surface_json_matches_cli(surface_package, capsys):  # noqa: F811 (imported fixture)
    out, _, code = run("surface", "pkg", "--json", capsys=capsys)
    assert code == 0
    cli_document = json.loads(out)

    result = server.surface("pkg", output_format="json")
    mcp_document = json.loads(result[0].text)

    assert mcp_document == cli_document
    assert mcp_document["coverage"]["public_names"] == 8


@requires_git
def test_surface_diff_matches_cli(tmp_path, monkeypatch, capsys):
    _write(tmp_path, PACKAGE)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "v1")
    _git(tmp_path, "checkout", "-qb", "next")
    core = (tmp_path / "pkg" / "core.py").read_text()
    (tmp_path / "pkg" / "core.py").write_text(core.replace("size: int = 1", "size: int = 2"))
    _git(tmp_path, "commit", "-qam", "v2")
    monkeypatch.chdir(tmp_path)

    out, _, code = run("surface", "pkg", "--ref", "main", "--against", "next", capsys=capsys)
    assert code == 0

    result = server.surface("pkg", ref="main", against="next")
    assert result[0].text == out.rstrip("\n")


def test_surface_error_is_text_not_a_raise(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = server.surface("does-not-exist")
    assert len(result) == 1
    assert result[0].text.startswith("Error")


# --------------------------------------------------------------------------- overlap


@requires_git
def test_overlap_matches_cli(overlap_repo, capsys):  # noqa: F811 (imported fixture)
    out, _, code = run("overlap", "main", "feat-a", "feat-b", "feat-c", "feat-d", capsys=capsys)
    assert code == 0

    result = server.overlap("main", ["feat-a", "feat-b", "feat-c", "feat-d"])
    assert result[0].text == out.rstrip("\n")


@requires_git
def test_overlap_json_matches_cli(overlap_repo, capsys):  # noqa: F811 (imported fixture)
    out, _, code = run("overlap", "main", "feat-a", "feat-b", "--json", capsys=capsys)
    assert code == 0
    cli_document = json.loads(out)

    result = server.overlap("main", ["feat-a", "feat-b"], output_format="json")
    mcp_document = json.loads(result[0].text)

    assert mcp_document == cli_document
    assert mcp_document["coverage"]["branches"] == 2


@requires_git
def test_overlap_unknown_ref_is_text_not_a_raise(overlap_repo, capsys):  # noqa: F811 (imported fixture)
    _, err, code = run("overlap", "main", "nope", capsys=capsys)
    assert code == 1 and "unknown ref 'nope'" in err

    result = server.overlap("main", ["nope"])
    assert len(result) == 1
    assert "Error" in result[0].text and "nope" in result[0].text


def test_overlap_outside_a_repo_is_text_not_a_raise(tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside-overlap")
    result = server.overlap("main", ["feat"], repo=str(outside))
    assert len(result) == 1
    assert result[0].text.startswith("Error")


# --------------------------------------------------------------------------- callers


def test_callers_matches_cli(tmp_path, monkeypatch, capsys):
    (tmp_path / "mod.py").write_text(CODE)
    (tmp_path / "other.py").write_text(
        "from mod import target\n\n\ndef elsewhere():\n    return target(3)\n"
    )
    monkeypatch.chdir(tmp_path)

    out, _, code = run("callers", "target", capsys=capsys)
    assert code == 0

    result = server.callers("target")
    assert result[0].text == out.rstrip("\n")


def test_callers_json_matches_cli(tmp_path, monkeypatch, capsys):
    (tmp_path / "mod.py").write_text(CODE)
    monkeypatch.chdir(tmp_path)

    out, _, code = run("callers", "target", "--json", capsys=capsys)
    assert code == 0
    cli_document = json.loads(out)

    result = server.callers("target", output_format="json")
    mcp_document = json.loads(result[0].text)
    assert mcp_document == cli_document
    assert mcp_document["coverage"]["call_sites"] >= 1


def test_callers_none_matches_cli(tmp_path, monkeypatch, capsys):
    (tmp_path / "mod.py").write_text("def lonely():\n    return 1\n")
    monkeypatch.chdir(tmp_path)

    out, _, code = run("callers", "lonely", capsys=capsys)
    assert code == 1

    result = server.callers("lonely")
    assert result[0].text == out.rstrip("\n")
    assert "no call sites of lonely" in result[0].text


def test_callers_bad_directory_is_text_not_a_raise():
    result = server.callers("target", directory="/no/such/directory")
    assert len(result) == 1
    assert result[0].text.startswith("Error")


# --------------------------------------------------------------------------- resolve


@pytest.fixture
def resolve_repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "mod.py").write_text(V1)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "v1")
    _git(tmp_path, "tag", "v1")
    (tmp_path / "mod.py").write_text(V2)
    _git(tmp_path, "commit", "-qam", "v2")
    _git(tmp_path, "tag", "v2")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@requires_git
def test_resolve_line_matches_cli(resolve_repo, capsys):
    out, _, code = run("resolve", "mod.py:2", "--from", "v1", "--to", "v2", capsys=capsys)
    assert code == 0

    result = server.resolve("mod.py:2", ref_from="v1", ref_to="v2")
    assert result[0].text == out.rstrip("\n")


@requires_git
def test_resolve_renamed_matches_cli(resolve_repo, capsys):
    out, _, code = run("resolve", "mod.py::beta", "--from", "v1", "--to", "v2", capsys=capsys)
    assert code == 0

    result = server.resolve("mod.py::beta", ref_from="v1", ref_to="v2")
    assert result[0].text == out.rstrip("\n")


@requires_git
def test_resolve_gone_matches_cli(resolve_repo, capsys):
    out, _, code = run("resolve", "mod.py::prelude", "--from", "v2", "--to", "v1", capsys=capsys)
    assert code == 1

    result = server.resolve("mod.py::prelude", ref_from="v2", ref_to="v1")
    assert result[0].text == out.rstrip("\n")
    assert "gone at v1" in result[0].text


@requires_git
def test_resolve_json_matches_cli(resolve_repo, capsys):
    out, _, code = run("resolve", "mod.py:6", "--from", "v1", "--to", "v2", "--json", capsys=capsys)
    assert code == 0
    cli_document = json.loads(out)

    result = server.resolve("mod.py:6", ref_from="v1", ref_to="v2", output_format="json")
    mcp_document = json.loads(result[0].text)
    assert mcp_document == cli_document
    assert mcp_document["to"]["how"] == "renamed"


@requires_git
def test_resolve_address_carries_ref_from(resolve_repo, capsys):
    (resolve_repo / "mod.py").write_text(V2 + "\n\ndef tail():\n    return 0\n")

    out, _, code = run("resolve", "mod.py::alpha@v1", capsys=capsys)
    assert code == 0

    result = server.resolve("mod.py::alpha@v1")
    assert result[0].text == out.rstrip("\n")


@requires_git
def test_resolve_missing_ref_from_is_text_not_a_raise(resolve_repo):
    result = server.resolve("mod.py:2")
    assert len(result) == 1
    assert result[0].text.startswith("Error")
    # cli.main raises UsageError (argparse-style exit 2) for the same input;
    # the MCP tool has no process exit code, so it reports the same failure
    # as text instead of raising.
    assert cli.main(["resolve", "mod.py:2"]) == 2
