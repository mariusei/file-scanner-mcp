"""`sct callers`: actual call sites, never mentions in prose. `sct resolve`:
a line or a name at one ref, the enclosing structure and its whereabouts at
another."""

import json
import os
import re
import shutil
import subprocess

import pytest

from scantool import cli

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

CODE = '''"""Docs mention target() here, which is not a call."""


def target(x):
    return x


def user_one():
    # target() in a comment is not a call either
    return target(1)


class Box:
    def method(self):
        label = "target()"
        return target(self) + target(2)


value = target(0)
'''


def run(*argv, capsys):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return captured.out, captured.err, code


def test_callers_lists_actual_call_sites_only(tmp_path, monkeypatch, capsys):
    (tmp_path / "mod.py").write_text(CODE)
    (tmp_path / "other.py").write_text(
        "from mod import target\n\n\ndef elsewhere():\n    return target(3)\n"
    )
    monkeypatch.chdir(tmp_path)
    out, _, code = run("callers", "target", capsys=capsys)
    assert code == 0
    assert out.splitlines()[0].startswith(
        "<5 call sites in 2 files, 1 definition, 2 files scanned> callers of target"
    )
    assert "defined: mod.py::target (function) mod.py:4" in out
    assert "  - user_one mod.py:10   return target(1)" in out
    assert (
        "  - Box.method mod.py:16   return target(self) + target(2)" in out
        or "  - method mod.py:16" in out
    )
    assert "  - (module level) mod.py:19   value = target(0)" in out
    assert "  - elsewhere other.py:5   return target(3)" in out
    assert not re.search(r"mod\.py:(1|9|15)\b", out)  # the docstring, comment and string lines


def test_callers_none(tmp_path, monkeypatch, capsys):
    (tmp_path / "mod.py").write_text("def lonely():\n    return 1\n")
    monkeypatch.chdir(tmp_path)
    out, _, code = run("callers", "lonely", capsys=capsys)
    assert code == 1 and "no call sites of lonely" in out


def _git(cwd, *args):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x",
        },
    )


V1 = "def alpha(x):\n    return x\n\n\ndef beta(y):\n    total = y\n    return total * 2\n"
V2 = "import os\n\n\ndef prelude():\n    return os.getcwd()\n\n\ndef alpha(x):\n    return x\n\n\ndef gamma(y):\n    total = y\n    return total * 2\n"


@requires_git
class TestResolve:
    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
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

    def test_line_to_enclosing_structure_and_its_new_place(self, repo, capsys):
        out, _, code = run("resolve", "mod.py:2", "--from", "v1", "--to", "v2", capsys=capsys)
        assert code == 0
        assert out.splitlines() == ["mod.py::alpha@v1 (1-2)", "mod.py::alpha@v2 (8-9)"]

    def test_renamed_with_identical_body(self, repo, capsys):
        out, _, code = run("resolve", "mod.py::beta", "--from", "v1", "--to", "v2", capsys=capsys)
        assert code == 0
        assert out.splitlines()[0] == "mod.py::beta@v1 (5-7)"
        assert out.splitlines()[1] == "mod.py::gamma@v2 (12-14)   [renamed from beta]"

    def test_gone_with_nearest_names(self, repo, capsys):
        out, _, code = run(
            "resolve", "mod.py::prelude", "--from", "v2", "--to", "v1", capsys=capsys
        )
        assert code == 1
        assert out.splitlines() == ["mod.py::prelude@v2 (4-5)", "gone at v1"]

    def test_address_carries_the_from_ref_and_worktree_is_the_default_target(self, repo, capsys):
        (repo / "mod.py").write_text(V2 + "\n\ndef tail():\n    return 0\n")
        out, _, code = run("resolve", "mod.py::alpha@v1", capsys=capsys)
        assert code == 0 and out.splitlines()[1] == "mod.py::alpha@WORKTREE (8-9)"

    def test_json_and_usage(self, repo, capsys):
        out, _, code = run(
            "resolve", "mod.py:6", "--from", "v1", "--to", "v2", "--json", capsys=capsys
        )
        document = json.loads(out)
        assert (
            code == 0 and document["from"]["name"] == "beta" and document["to"]["how"] == "renamed"
        )
        assert cli.main(["resolve", "mod.py", "--from", "v1"]) == 2
