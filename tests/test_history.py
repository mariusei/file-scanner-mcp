"""`sct history` (brief §5.4, §10, §11 E): one structure followed backwards
through the commits that touched its file — renames of the structure by
identical body, moves of the file by git's follow."""

import json
import os
import shutil
import subprocess

import pytest

from scantool import cli, server

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@x",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@x",
    "GIT_CONFIG_PARAMETERS": "'core.autocrlf=false'",
}


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, env={**os.environ, **_ENV}
    )


def _commit(cwd, message, date):
    _git(cwd, "add", "-A")
    subprocess.run(
        ["git", "commit", "-qm", message],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={**os.environ, **_ENV, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "mod.py").write_text(
        "def beta(y):\n    return y * 2\n\n\ndef other():\n    return 0\n"
    )
    _commit(tmp_path, "add beta", "2026-01-01T00:00:00Z")
    (tmp_path / "mod.py").write_text(
        "def beta(y):\n    return y * 2\n\n\ndef other():\n    return 1\n"
    )
    _commit(tmp_path, "touch other only", "2026-01-02T00:00:00Z")
    (tmp_path / "mod.py").write_text(
        "def alpha(y):\n    return y * 2\n\n\ndef other():\n    return 1\n"
    )
    _commit(tmp_path, "rename beta to alpha", "2026-01-03T00:00:00Z")
    (tmp_path / "mod.py").write_text(
        "def alpha(y, k=1):\n    return y * 2\n\n\ndef other():\n    return 1\n"
    )
    _commit(tmp_path, "alpha takes k", "2026-01-04T00:00:00Z")
    (tmp_path / "src").mkdir()
    _git(tmp_path, "mv", "mod.py", "src/mod.py")
    _commit(tmp_path, "move into src", "2026-01-05T00:00:00Z")
    (tmp_path / "src" / "mod.py").write_text(
        "def alpha(y, k=1):\n    return y * 2 + k\n\n\ndef other():\n    return 1\n"
    )
    _commit(tmp_path, "alpha uses k", "2026-01-06T00:00:00Z")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(*argv, capsys):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return captured.out, captured.err, code


@requires_git
class TestHistory:
    def test_follows_signature_rename_move_and_birth(self, repo, capsys):
        out, _, code = _run("history", "src/mod.py::alpha", capsys=capsys)
        assert code == 0, out
        lines = out.splitlines()
        assert lines[0].startswith(
            "<4 changes in 6 commits touching the file, 1 rename> history of src/mod.py::alpha@HEAD (1-2)"
        )
        marks = [line.split()[2] for line in lines[1:]]
        assert marks == ["~", "~", "=", "+"]
        assert "alpha uses k" in lines[1] and "[body: 1 code line]" in lines[1]
        assert "alpha takes k" in lines[2] and "[signature: (y) → (y, k=1)]" in lines[2]
        assert (
            "rename beta to alpha" in lines[3]
            and "[renamed from beta]" in lines[3]
            and "(mod.py)" in lines[3]
        )
        assert "add beta" in lines[4] and "+ beta(y)" in lines[4] and "[added]" in lines[4]
        assert not any(
            "touch other only" in line for line in lines
        )  # touched the file, not the structure
        assert not any("move into src" in line for line in lines)

    def test_line_form_and_ref_in_the_address(self, repo, capsys):
        by_line, _, code = _run("history", "src/mod.py:2", capsys=capsys)
        by_name, _, _ = _run("history", "src/mod.py::alpha@HEAD", capsys=capsys)
        assert code == 0 and by_line == by_name
        older, _, code = _run("history", "mod.py::alpha", "--ref", "HEAD~2", capsys=capsys)
        assert code == 0 and older.splitlines()[0].startswith("<3 changes in 4 commits")

    def test_json_and_both_doors_agree(self, repo, capsys):
        out, _, code = _run("history", "src/mod.py::alpha", "--json", capsys=capsys)
        document = json.loads(out)
        assert code == 0 and document["coverage"] == {
            "changes": 4,
            "commits_touching_file": 6,
            "truncated": False,
            "ref": "HEAD",
        }
        assert [e["mark"] for e in document["events"]] == ["~", "~", "=", "+"]
        assert document["events"][2]["note"] == "renamed from beta"
        assert document["events"][3]["path"] == "mod.py"
        mcp = "".join(p.text for p in server.history("src/mod.py::alpha", output_format="json"))
        assert json.loads(mcp) == document
        text, _, _ = _run("history", "src/mod.py::alpha", capsys=capsys)
        assert "".join(p.text for p in server.history("src/mod.py::alpha")) == text.rstrip("\n")

    def test_unchanged_structure_and_misses(self, repo, capsys):
        out, _, code = _run("history", "src/mod.py::other", capsys=capsys)
        assert code == 0 and out.splitlines()[1].split()[2] == "~"  # other changed once
        _, err, code = _run("history", "src/mod.py::nothing", capsys=capsys)
        assert code == 1 and "no structure matches 'nothing'" in err
        assert cli.main(["history", "src/mod.py"]) == 2  # neither ::name nor :line
