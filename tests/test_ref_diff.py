"""Tests for structural ref-diff: which nodes are new/changed/removed vs a
git ref, with whitespace-only changes reported as non-structural."""

import shutil
import subprocess

import pytest

from scantool.ref_diff import diff_against_ref

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

V1 = '''\
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
'''

V2 = '''\
def alpha(items):
    kept = [i for i in items if i.valid]
    return summarize(kept, mode="alpha")


def beta(items):
    counts = {}
    for i in items:
        counts[i.kind] = counts.get(i.kind, 0) + i.weight
    return counts


def fresh(payload):
    return validate(payload) and persist(payload)
'''


def _git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "mod.py").write_text(V1)
    (tmp_path / "gone.py").write_text("def vanishing():\n    return 1\n")
    (tmp_path / "notes.md").write_text("# Plan\n\nGammel tekst.\n")
    _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "v1")
    # arbeidstre-endringer (ucommittet — review-flyten)
    (tmp_path / "mod.py").write_text(V2)
    (tmp_path / "gone.py").unlink()
    (tmp_path / "added.py").write_text("def newcomer():\n    return shiny_call()\n")
    (tmp_path / "notes.md").write_text("# Plan\n\nNy tekst her.\n")
    return tmp_path


@requires_git
class TestRefDiff:
    def test_changed_nodes_labelled_with_detail(self, repo):
        out = diff_against_ref(str(repo))

        assert "[endret]" in out
        assert "i.weight" in out                 # endret kropp synlig
        assert "mode=\"alpha\"" not in out       # uendret kropp undertrykt

    def test_new_and_removed_nodes(self, repo):
        out = diff_against_ref(str(repo))

        assert "fresh" in out and "[ny]" in out
        assert "fjernet: doomed" in out

    def test_new_and_deleted_files(self, repo):
        out = diff_against_ref(str(repo))

        assert "added.py [ny fil]" in out
        assert "newcomer" in out
        assert "slettet: gone.py" in out

    def test_markdown_sections_diff_structurally(self, repo):
        out = diff_against_ref(str(repo))

        # md-endringen bor i Plan-seksjonen → strukturelt endret
        assert "notes.md" in out

    def test_whitespace_only_change_reported_as_non_structural(self, repo):
        (repo / "mod.py").write_text(V2.replace("    return counts",
                                                "    return counts  "))
        _git(repo, "add", "."), _git(repo, "commit", "-qm", "v2")
        (repo / "mod.py").write_text(V2.replace("    return counts",
                                                "    return counts   "))

        out = diff_against_ref(str(repo))

        assert "uten strukturell endring" in out or "Ingen endringer" in out

    def test_unknown_ref(self, repo):
        assert "Ukjent ref" in diff_against_ref(str(repo), ref="finnes-ikke")

    def test_no_changes(self, repo):
        _git(repo, "add", "."), _git(repo, "commit", "-qm", "v2")

        assert "Ingen endringer" in diff_against_ref(str(repo))

    def test_non_git_directory(self, tmp_path):
        (tmp_path / "f.py").write_text("x = 1\n")

        assert "ikke i et git-repo" in diff_against_ref(str(tmp_path))
