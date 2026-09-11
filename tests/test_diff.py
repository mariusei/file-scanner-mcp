"""`sct diff`: which structures changed between two refs, with both sides in
view. Built on a small repository with a base commit, a feature branch and
a main that moved on, so the merge-base default has something to do.
"""

import json
import os
import shutil
import subprocess

import pytest

from scantool import cli
from scantool.scanner import FileScanner
from scantool.structural_diff import file_rows, records

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

BASE = '''"""Module."""

LIMIT = 3


def alpha(x):
    return x + 1


def beta(y):
    total = 0
    for item in y:
        total += item
    return total


class K:
    """Holder."""

    def m1(self):
        return 1

    def m2(self):
        return 2
'''

FEATURE = '''"""Module."""

LIMIT = 4
NEW_FLAG = True


def alpha(x, flag):
    return x + 1


def gamma(y):
    total = 0
    for item in y:
        total += item
    return total


class K2:
    """Holder."""

    def m1(self):
        return 1

    def m2(self):
        return 22
'''


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
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "mod.py").write_text(BASE)
    (tmp_path / "docs.md").write_text(
        "# Title\n\n## Section A\n\nold words\n\n## Section B\n\nsame\n"
    )
    (tmp_path / "keep.py").write_text("def kept():\n    return 0\n")
    (tmp_path / "data.xyz").write_text("blob\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "checkout", "-qb", "feature")
    (tmp_path / "mod.py").write_text(FEATURE)
    (tmp_path / "docs.md").write_text(
        "# Title\n\n## Section A\n\nnew words here\n\n## Section B\n\nsame\n"
    )
    (tmp_path / "keep.py").unlink()
    (tmp_path / "new.py").write_text(
        "def fresh():\n    return 1\n\n\nclass Box:\n    def open(self):\n        return True\n"
    )
    (tmp_path / "data.xyz").write_text("blob changed\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "feature")
    _git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "keep.py").write_text("def kept():\n    return 100\n")
    _git(tmp_path, "commit", "-qam", "main moved on")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(*argv, capsys):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return captured.out, captured.err, code


@requires_git
class TestDiff:
    def test_rows_show_both_sides(self, repo, capsys):
        out, _, code = run("diff", "main", "feature", capsys=capsys)
        assert code == 0
        assert out.splitlines()[0].startswith("note: main and feature diverged at ")
        assert "comparing " in out.splitlines()[0] and "→ feature" in out.splitlines()[0]
        assert "<5 files changed, 4 with structural rows, 1 without (1 unstructured type)>" in out
        rows = [line.strip() for line in out.splitlines() if line.startswith("  ")]
        assert any(r.startswith("+ NEW_FLAG") and "B:4" in r for r in rows)
        assert any(r.startswith("~ LIMIT") and "[value: 3 → 4]" in r for r in rows)
        assert any(
            r.startswith("~ alpha(x, flag)") and "[signature: (x) → (x, flag)]" in r for r in rows
        )
        assert any(r.startswith("= gamma(y)") and "[renamed from beta]" in r for r in rows)
        assert any(
            r.startswith("= K2 ") and "[renamed from K; 1 member follows]" in r for r in rows
        )
        assert any(
            r.startswith("= K2.m2") and "renamed from K.m2; body: 1 code line]" in r for r in rows
        )
        assert not any("K.m1" in r or "K2.m1" in r for r in rows)  # follows its class
        assert not any(r.startswith("- beta") for r in rows)
        assert any(r.startswith("~ Section A") and "[body: 1 doc line]" in r for r in rows)
        assert "new.py [new file]" in out and "  - Box @" in out and "    - open" in out
        assert "keep.py [deleted]" in out and any(r.startswith("- kept()") for r in rows)
        assert "data.xyz (unstructured type)" in out
        assert "main moved on" not in out  # main's own commit is not in main→feature

    def test_no_merge_base_compares_the_tips(self, repo, capsys):
        out, _, code = run("diff", "main", "feature", "--no-merge-base", capsys=capsys)
        assert code == 0 and not out.startswith("note:")
        assert "keep.py" in out  # main changed it after the fork; feature deleted it

    def test_one_ref_means_working_tree(self, repo, capsys):
        (repo / "mod.py").write_text(BASE.replace("return x + 1", "return x + 2"))
        out, _, code = run("diff", "HEAD", capsys=capsys)
        assert code == 0 and "> HEAD → WORKTREE" in out.splitlines()[0]
        assert any(line.strip().startswith("~ alpha(x)") for line in out.splitlines())

    def test_path_restricts_and_repo_points_elsewhere(
        self, repo, tmp_path_factory, monkeypatch, capsys
    ):
        elsewhere = tmp_path_factory.mktemp("elsewhere")  # outside the repository
        monkeypatch.chdir(elsewhere)
        _, err, code = run("diff", "main", "feature", capsys=capsys)
        assert code == 1 and "pass --repo DIR" in err
        out, _, code = run(
            "diff", "main", "feature", "--repo", str(repo), "--path", "docs.md", capsys=capsys
        )
        assert code == 0 and "Section A" in out and "alpha" not in out

    def test_json_form(self, repo, capsys):
        out, _, code = run("diff", "main", "feature", "--json", capsys=capsys)
        document = json.loads(out)
        assert code == 0 and document["coverage"]["files_changed"] == 5
        marks = {(r["mark"], r["name"]) for f in document["files"] for r in f["rows"]}
        assert ("=", "gamma") in marks and ("~", "alpha") in marks

    def test_identical_signature_deltas_fold_into_one_row(self, tmp_path):
        old = "def a(x):\n    return 1\n\n\ndef b(x):\n    return 2\n\n\ndef c(x):\n    return 3\n"
        new = old.replace("(x)", "(x, binding)")
        scanner = FileScanner()
        a = records(scanner.scan_content(old, "m.py"), old.split("\n"))
        b = records(scanner.scan_content(new, "m.py"), new.split("\n"))
        rows = file_rows(a, b)
        assert len(rows) == 1 and rows[0].name == "3 functions"
        assert rows[0].note == "signature +binding: a, b, c"
