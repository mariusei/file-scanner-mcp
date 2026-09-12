"""`sct overlap`: several branches against one base, each at its own
merge-base. The fixture has two independent branches that touch the same
function and add the same new name in different files, a third and a fifth
stacked on the first (touching the same function differently), a fourth
already merged into the base, and a base that moves the shared function
after every branch forked.
"""

import json
import os
import shutil
import subprocess

import pytest

from scantool import cli

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

BASE = "def alpha(x):\n    return x\n\n\ndef beta(y):\n    return y\n"


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
    (tmp_path / "other.py").write_text("def gamma():\n    return 0\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    # feat-a: changes alpha, adds newfn in mod.py
    _git(tmp_path, "checkout", "-qb", "feat-a")
    (tmp_path / "mod.py").write_text(
        BASE.replace("return x", "return x + 1") + "\n\ndef newfn():\n    return 'a'\n"
    )
    _git(tmp_path, "commit", "-qam", "a")
    # feat-c stacks on feat-a and touches beta
    _git(tmp_path, "checkout", "-qb", "feat-c")
    text = (tmp_path / "mod.py").read_text()
    (tmp_path / "mod.py").write_text(text.replace("return y", "return y * 2"))
    _git(tmp_path, "commit", "-qam", "c")
    # feat-b: independent, changes alpha differently, adds newfn in other.py
    _git(tmp_path, "checkout", "-q", "main")
    _git(tmp_path, "checkout", "-qb", "feat-b")
    (tmp_path / "mod.py").write_text(BASE.replace("return x", "return x - 1"))
    (tmp_path / "other.py").write_text(
        "def gamma():\n    return 0\n\n\ndef newfn():\n    return 'b'\n"
    )
    _git(tmp_path, "commit", "-qam", "b")
    # feat-d: merged into main already (ancestor)
    _git(tmp_path, "checkout", "-q", "main")
    _git(tmp_path, "checkout", "-qb", "feat-d")
    (tmp_path / "other.py").write_text("def gamma():\n    return 1\n")
    _git(tmp_path, "commit", "-qam", "d")
    _git(tmp_path, "checkout", "-q", "main")
    _git(tmp_path, "merge", "-q", "--ff-only", "feat-d")
    # feat-e stacks on feat-a like feat-c and touches beta differently: the
    # pair feat-c/feat-e shares feat-a's commit, and beta is their residual
    _git(tmp_path, "checkout", "-qb", "feat-e", "feat-a")
    text = (tmp_path / "mod.py").read_text()
    (tmp_path / "mod.py").write_text(text.replace("return y", "return y * 3"))
    _git(tmp_path, "commit", "-qam", "e")
    # main moves alpha after every branch forked
    _git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "mod.py").write_text(BASE.replace("return x", "return x * 10"))
    _git(tmp_path, "commit", "-qam", "main moves alpha")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(*argv, capsys):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return captured.out, captured.err, code


@requires_git
class TestOverlap:
    def test_sections(self, repo, capsys):
        out, _, code = run("overlap", "main", "feat-a", "feat-b", "feat-c", "feat-d", capsys=capsys)
        assert code == 0
        first = out.splitlines()[0]
        assert first.startswith(
            "<4 branches vs main, 3 with structural changes, 1 already in base, 1 pair sharing history> base main ("
        )
        assert "feat-d" in out and "[already in base: ancestor]" in out
        assert "shared history: feat-a and feat-c share 1 commit beyond the base" in out
        assert (
            "overlap (structures touched by 2+ branches): 2 in 1 file, 1 also changed in base"
            in out
        )
        assert "mod.py::alpha" in out and "feat-a(~)  feat-b(~)  feat-c(~)  base(~)" in out
        assert "mod.py::newfn" in out and "feat-a(+)  feat-c(+)\n" in out
        assert "colliding new names (added independently on 2+ branches): 1" in out
        assert "newfn" in out and "feat-a:mod.py:9" in out and "feat-b:other.py:5" in out
        # feat-c and feat-e got newfn through the commits they share with
        # feat-a: added once, not a collision between them and feat-a
        row = next(line for line in out.splitlines() if line.startswith("  newfn"))
        assert "feat-c:" not in row and "feat-e:" not in row, row
        # feat-a and feat-b each share only alpha with a branch they do not
        # stack on (newfn is feat-a/feat-c shared history) and touch 2 each
        assert "merge order (a hint, not a verdict): feat-a < feat-b < feat-c   (all share 1" in out
        assert "stacked pairs count only their residual beyond shared commits" in out
        assert "feat-d" not in out.splitlines()[-1]  # already in base: not ordered

    def test_base_moved_marks_only_structures_the_base_changed(self, repo, capsys):
        out, _, _ = run("overlap", "main", "feat-a", "feat-c", "--json", capsys=capsys)
        rows = {o["address"]: o for o in json.loads(out)["overlap"]}
        assert rows["mod.py::alpha"]["base"] == "~" and rows["mod.py::alpha"]["kind"] == "function"
        assert rows["mod.py::newfn"]["base"] is None

    def test_residual_beyond_shared_commits(self, repo, capsys):
        out, _, code = run("overlap", "main", "feat-a", "feat-c", "feat-e", capsys=capsys)
        assert code == 0
        lines = out.splitlines()
        # raw overlap between feat-c and feat-e counts alpha and newfn, which
        # both inherit from feat-a; beyond their mutual merge-base only beta
        assert (
            "overlap (structures touched by 2+ branches): 3 in 1 file, 1 also changed in base"
            in out
        )
        assert "mod.py::beta" in out and "feat-c(~)  feat-e(~)\n" in out
        pairs = [i for i, line in enumerate(lines) if line.startswith("shared history: ")]
        assert [lines[i + 1] for i in pairs] == [
            "  residual beyond their shared commits: none",  # feat-a and feat-c
            "  residual beyond their shared commits: none",  # feat-a and feat-e
            "  residual beyond their shared commits: 1 structure in 1 file",  # feat-c and feat-e
        ]
        assert lines[-1].startswith(
            "merge order (a hint, not a verdict): feat-a < feat-c < feat-e   "
            "(feat-a shares 0 structures with the others, feat-e shares 1;"
        )
        assert lines[-1].endswith("stacked pairs count only their residual beyond shared commits)")

        out, _, _ = run("overlap", "main", "feat-a", "feat-c", "feat-e", "--json", capsys=capsys)
        history = json.loads(out)["coverage"]["sharing_history"]
        assert [(h["a"], h["b"], h["commits"]) for h in history] == [
            ("feat-a", "feat-c", 1),
            ("feat-a", "feat-e", 1),
            ("feat-c", "feat-e", 1),
        ]
        assert history[0]["residual"] == {"structures": 0, "files": 0, "addresses": []}
        assert history[2]["residual"] == {
            "structures": 1,
            "files": 1,
            "addresses": ["mod.py::beta"],
        }

    def test_each_branch_is_diffed_at_its_own_merge_base(self, repo, capsys):
        # feat-d moved main's other.py after feat-a forked; feat-a must not be
        # blamed for gamma's change
        out, _, _ = run("overlap", "main", "feat-a", "feat-b", capsys=capsys)
        assert "gamma" not in out

    def test_json(self, repo, capsys):
        out, _, code = run("overlap", "main", "feat-a", "feat-b", "--json", capsys=capsys)
        document = json.loads(out)
        assert code == 0 and document["coverage"]["branches"] == 2
        assert {o["address"] for o in document["overlap"]} == {"mod.py::alpha"}
        assert set(document["colliding_names"]) == {"newfn"}
        assert {site["kind"] for site in document["colliding_names"]["newfn"]} == {"function"}
        assert {site["branch"] for site in document["colliding_names"]["newfn"]} == {
            "feat-a",
            "feat-b",
        }

    def test_unknown_ref_and_no_repo(self, repo, tmp_path_factory, monkeypatch, capsys):
        _, err, code = run("overlap", "main", "nope", capsys=capsys)
        assert code == 1 and "unknown ref 'nope'" in err
        monkeypatch.chdir(tmp_path_factory.mktemp("outside"))
        _, err, code = run("overlap", "main", "feat-a", capsys=capsys)
        assert code == 1 and "pass --repo DIR" in err
