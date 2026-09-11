"""`--ref` reads at a git ref without a checkout. A file or one node comes
from `git show` through scan_file_content; a directory or a search comes
from `git archive` unpacked into a temporary directory, with every path in
the answer written the way the caller spelled it. In the field study every
agent needed git show or git archive to scratch for this; the tool now does
it and says which ref it read on the coverage line.
"""

import json
import os
import shutil
import subprocess

import pytest

from scantool import cli

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

V1 = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"
V2 = "def alpha():\n    return 10\n"


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


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text(V1)
    (tmp_path / "src" / "gone.py").write_text("def vanishing():\n    return 1\n")
    (tmp_path / "notes.md").write_text("# Plan\n\n## Old section\n\nOld text.\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "v1")
    # the working tree moves on
    (tmp_path / "src" / "mod.py").write_text(V2)
    (tmp_path / "src" / "gone.py").unlink()
    (tmp_path / "src" / "added.py").write_text("def newcomer():\n    return 3\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(*argv, capsys):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return captured.out, captured.err, code


@requires_git
class TestRef:
    def test_file_at_ref_is_the_committed_content(self, repo, capsys):
        out, _, code = run("scan", "src/mod.py", "--ref", "HEAD", capsys=capsys)
        assert code == 0
        assert out.splitlines()[0] == "<1 file seen, 2 structures shown> @HEAD"
        assert "beta" in out  # only at the ref
        tree, _, _ = run("scan", "src/mod.py", capsys=capsys)
        assert "beta" not in tree  # the working tree lost it

    def test_focus_at_ref(self, repo, capsys):
        out, _, code = run("focus", "src/mod.py", "beta", "--ref", "HEAD", capsys=capsys)
        assert code == 0 and out.startswith("focus: beta @5-6")
        assert "return 2" in out

    def test_directory_at_ref_lists_the_committed_tree_under_the_callers_path(self, repo, capsys):
        out, _, code = run("scan", "src", "--ref", "HEAD", capsys=capsys)
        assert code == 0
        assert out.splitlines()[0].startswith("<2 files seen") and out.splitlines()[0].endswith(
            " @HEAD"
        )
        assert out.splitlines()[1].startswith("src/ (")
        assert "gone.py" in out and "added.py" not in out
        assert "sct-ref" not in out  # no temporary path leaks into the answer

    def test_search_at_ref_reports_paths_the_caller_can_use(self, repo, capsys):
        out, _, code = run("search", ".", "vanishing", "--ref", "HEAD", capsys=capsys)
        assert code == 0
        assert out.splitlines()[0].endswith(" @HEAD")
        # the caller typed "."; below it the OS separator is the one the
        # working-tree search prints too
        assert "src/gone.py" in out.replace("\\", "/") and "sct-ref" not in out

    def test_json_coverage_carries_the_ref(self, repo, capsys):
        out, _, code = run("scan", "src/mod.py", "--ref", "HEAD", "--json", capsys=capsys)
        document = json.loads(out)
        assert code == 0 and document["coverage"]["ref"] == "HEAD"
        assert document["file"] == "src/mod.py"

    def test_missing_at_ref_names_ref_and_repository(self, repo, capsys):
        out, err, code = run("scan", "src/added.py", "--ref", "HEAD", capsys=capsys)
        assert code == 1
        message = (out + err).replace("\\", "/")
        assert "HEAD:src/added.py" in message
        assert str(repo.resolve()).replace("\\", "/") in message  # git spells it with slashes

    def test_ref_outside_a_repository_says_so(self, tmp_path, monkeypatch, capsys):
        outside = tmp_path / "plain"
        outside.mkdir()
        (outside / "x.py").write_text("def x():\n    return 1\n")
        monkeypatch.chdir(outside)
        _, err, code = run("scan", "x.py", "--ref", "HEAD", capsys=capsys)
        assert code == 1 and "not inside a git repository" in err

    def test_ref_and_stdin_content_are_exclusive(self, repo, capsys):
        assert cli.main(["scan", "-", "--as", "a.py", "--ref", "HEAD"]) == 2
        assert "One or the other" in capsys.readouterr().err
