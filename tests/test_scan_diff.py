"""The MCP scan_diff tool is the same diff as `sct diff`: one engine
(structural_diff), the same table, ref vs working tree or ref vs ref, and
the review tail (candidate dead/orphan/drift in the changed files) only
when asked for — on both sides."""

import json
import shutil
import subprocess

import pytest

from scantool import server
from scantool.code_map import clear_corpus_cache
from scantool.connectivity import clear_connectivity_cache

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

V1 = """\
def alpha(items):
    kept = [i for i in items if i.valid]
    return summarize(kept, mode="alpha")


def beta(items):
    counts = {}
    for i in items:
        counts[i.kind] = counts.get(i.kind, 0) + 1
    return counts


def doomed():
    return legacy_call()
"""

V2 = """\
def alpha(items):
    kept = [i for i in items if i.valid]
    return summarize(kept, mode="alpha")


def beta(items, weighted=True):
    counts = {}
    for i in items:
        counts[i.kind] = counts.get(i.kind, 0) + i.weight
    return counts


def fresh(payload):
    return validate(payload) and persist(payload)
"""


def _git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _text(result) -> str:
    return "".join(part.text for part in result)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "mod.py").write_text(V1)
    (tmp_path / "gone.py").write_text("def vanishing():\n    return 1\n")
    (tmp_path / "notes.md").write_text("# Plan\n\nOld text.\n")
    _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "v1")
    # working-tree changes (uncommitted — the review flow)
    (tmp_path / "mod.py").write_text(V2)
    (tmp_path / "gone.py").unlink()
    (tmp_path / "added.py").write_text("def newcomer():\n    return shiny_call()\n")
    (tmp_path / "notes.md").write_text("# Plan\n\nNew text here.\n")
    return tmp_path


@requires_git
class TestScanDiff:
    def test_default_is_the_working_tree_against_head_in_table_form(self, repo):
        out = _text(server.scan_diff(str(repo)))
        assert out.splitlines()[0].endswith("> HEAD → WORKTREE")
        rows = [line.strip() for line in out.splitlines() if line.startswith("  ")]
        assert any(r.startswith("~ beta(items, weighted=True)") for r in rows)
        assert any("[signature: (items) → (items, weighted=True)" in r for r in rows)
        assert any(r.startswith("+ fresh(payload)") and "B:" in r for r in rows)
        assert any(r.startswith("- doomed()") and "A:" in r for r in rows)
        assert "added.py [new file]" in out and "newcomer" in out
        assert "gone.py [deleted]" in out and any(r.startswith("- vanishing()") for r in rows)
        assert any(r.startswith("~ Plan") and "doc line" in r for r in rows)  # markdown too
        assert 'mode="alpha"' not in out  # an unchanged body is not printed
        assert "REVIEW" not in out and "PEER DIVERGENCE" not in out  # off by default

    def test_ref_to_ref_against_the_merge_base_with_a_note(self, repo):
        _git(repo, "add", "-A"), _git(repo, "commit", "-qm", "v2")
        _git(repo, "checkout", "-qb", "feature", "HEAD~1")
        (repo / "mod.py").write_text(V1.replace("legacy_call()", "modern_call()"))
        _git(repo, "commit", "-qam", "feature")
        out = _text(server.scan_diff(str(repo), ref="main", ref2="feature"))
        assert out.splitlines()[0].startswith("note: main and feature diverged at ")
        assert "→ feature" in out.splitlines()[0]
        rows = [line.strip() for line in out.splitlines() if line.startswith("  ")]
        assert any(r.startswith("~ doomed()") for r in rows)
        assert not any("fresh" in r for r in rows)  # main's later work is not feature's removal
        tips = _text(server.scan_diff(str(repo), ref="main", ref2="feature", no_merge_base=True))
        assert not tips.startswith("note:") and any("fresh" in line for line in tips.splitlines())

    def test_directory_restricts_the_diff(self, repo):
        (repo / "pkg").mkdir()
        (repo / "pkg" / "inner.py").write_text("def inner():\n    return 1\n")
        out = _text(server.scan_diff(str(repo / "pkg")))
        assert "pkg/inner.py [new file]" in out and "mod.py" not in out

    def test_json_form(self, repo):
        document = json.loads(_text(server.scan_diff(str(repo), output_format="json")))
        assert document["side_a"] == "HEAD" and document["side_b"] == "WORKTREE"
        assert document["coverage"]["files_changed"] == 4
        marks = {(r["mark"], r["name"]) for f in document["files"] for r in f["rows"]}
        assert ("~", "beta") in marks and ("+", "fresh") in marks and ("-", "doomed") in marks
        assert "review" not in document
        with_review = json.loads(
            _text(server.scan_diff(str(repo), review=True, output_format="json"))
        )
        assert "review" in with_review

    def test_whitespace_only_change_has_no_rows(self, repo):
        _git(repo, "add", "-A"), _git(repo, "commit", "-qm", "v2")
        (repo / "mod.py").write_text(V2.replace("    return counts", "    return counts   "))
        out = _text(server.scan_diff(str(repo)))
        assert "1 without (1 no structural change)" in out
        assert "no structural differences between HEAD and WORKTREE" in out

    def test_no_changes(self, repo):
        _git(repo, "add", "-A"), _git(repo, "commit", "-qm", "v2")
        out = _text(server.scan_diff(str(repo)))
        assert out.startswith("<0 files changed") and "no structural differences" in out

    def test_unknown_ref(self, repo):
        assert "Unknown ref" in _text(server.scan_diff(str(repo), ref="does-not-exist"))

    def test_non_git_directory(self, tmp_path):
        (tmp_path / "f.py").write_text("x = 1\n")
        assert "not in a git repo" in _text(server.scan_diff(str(tmp_path)))


def _init_connectivity_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "core.py").write_text("def used():\n    return 1\n")
    (tmp_path / "main.py").write_text("from core import used\n\ndef main():\n    return used()\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    clear_corpus_cache()
    clear_connectivity_cache()


@requires_git
class TestScanDiffReview:
    """The review tail: dead/orphan loose ends a change introduces. Opt-in,
    the same tail on the MCP tool and on `sct diff --review`."""

    def test_flags_introduced_dead(self, tmp_path):
        _init_connectivity_repo(tmp_path)
        (tmp_path / "core.py").write_text(  # add a function nothing calls
            "def used():\n    return 1\n\ndef just_added():\n    return 2\n"
        )
        clear_corpus_cache()
        clear_connectivity_cache()
        out = _text(server.scan_diff(str(tmp_path), review=True))
        assert "candidate-dead" in out and "just_added" in out
        assert "candidate-dead" not in _text(server.scan_diff(str(tmp_path)))

    def test_flags_orphan_route(self, tmp_path):
        _init_connectivity_repo(tmp_path)
        (tmp_path / "app.py").write_text(  # a route referenced by no URL
            '@router.get("/konto-hint")\n'
            "def hent_konto_hint():\n    return 1\n\n"
            "def main():\n    return hent_konto_hint()\n"
        )
        clear_corpus_cache()
        clear_connectivity_cache()
        out = _text(server.scan_diff(str(tmp_path), review=True))
        assert "orphan" in out and "/konto-hint" in out

    def test_clean_change_has_no_loose_ends(self, tmp_path):
        _init_connectivity_repo(tmp_path)
        (tmp_path / "main.py").write_text(  # body tweak, nothing dead/orphan
            "from core import used\n\ndef main():\n    return used() + 0\n"
        )
        clear_corpus_cache()
        clear_connectivity_cache()
        out = _text(server.scan_diff(str(tmp_path), review=True))
        assert "candidate-dead" not in out and "orphan" not in out

    def test_the_cli_prints_the_same_tail_with_review(self, tmp_path, monkeypatch, capsys):
        from scantool import cli

        _init_connectivity_repo(tmp_path)
        (tmp_path / "core.py").write_text(
            "def used():\n    return 1\n\ndef just_added():\n    return 2\n"
        )
        clear_corpus_cache()
        clear_connectivity_cache()
        monkeypatch.chdir(tmp_path)
        code = cli.main(["diff", "HEAD"])
        plain = capsys.readouterr().out
        assert code == 0 and "candidate-dead" not in plain
        clear_corpus_cache()
        clear_connectivity_cache()
        code = cli.main(["diff", "HEAD", "--review"])
        reviewed = capsys.readouterr().out
        assert code == 0 and "candidate-dead" in reviewed and "just_added" in reviewed
        mcp = _text(server.scan_diff(str(tmp_path), review=True))
        assert reviewed.rstrip("\n") == mcp.rstrip("\n")  # one engine, one tail
