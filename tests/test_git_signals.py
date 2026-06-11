"""Tests for git_signals: churn, co-change, graceful absence.

Hard requirements: without git/repo every entry point returns None and
output stays identical to before the module existed; signals are file-level
and language-agnostic (docs-only repos work the same as code repos).
"""

import os
import shutil
import subprocess

import pytest

from scantool.git_signals import collect_git_signals, file_churn, format_activity

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(cwd, *args, date=None):
    env = None
    if date:
        env = {**os.environ,
               "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@test", *args],
        cwd=cwd, check=True, capture_output=True, env=env,
    )


@pytest.fixture
def repo(tmp_path):
    """Tiny docs+code repo: a.py+b.py committed together twice, notes.md once,
    deleted.py removed again."""
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "first")
    (tmp_path / "a.py").write_text("x = 11\n")
    (tmp_path / "b.py").write_text("y = 22\n")
    _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "second")
    (tmp_path / "notes.md").write_text("# Notater\n")
    (tmp_path / "deleted.py").write_text("gone = True\n")
    _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "third")
    _git(tmp_path, "rm", "-q", "deleted.py")
    _git(tmp_path, "commit", "-qm", "remove")
    return tmp_path


class TestGracefulAbsence:
    def test_non_git_directory_returns_none(self, tmp_path):
        (tmp_path / "f.py").write_text("x = 1\n")

        assert collect_git_signals(str(tmp_path)) is None
        assert file_churn(str(tmp_path / "f.py")) is None

    def test_missing_directory_returns_none(self, tmp_path):
        assert collect_git_signals(str(tmp_path / "does-not-exist")) is None


@requires_git
class TestSignals:
    def test_churn_counts_commits_per_file(self, repo):
        signals = collect_git_signals(str(repo))

        assert signals is not None
        assert signals.churn["a.py"] == 2
        assert signals.churn["b.py"] == 2
        # non-code files count the same way — signals are language-agnostic
        assert signals.churn["notes.md"] == 1

    def test_deleted_files_excluded(self, repo):
        signals = collect_git_signals(str(repo))

        assert "deleted.py" not in signals.churn

    def test_co_change_pairs(self, repo):
        signals = collect_git_signals(str(repo))

        pairs = {(a, b): c for a, b, c in signals.co_change}
        assert pairs.get(("a.py", "b.py")) == 2

    def test_file_churn_single_file(self, repo):
        assert file_churn(str(repo / "a.py")) == 2
        assert file_churn(str(repo / "notes.md")) == 1

    def test_format_activity(self, repo):
        signals = collect_git_signals(str(repo))

        section = format_activity(signals)

        assert "GIT ACTIVITY" in section
        assert "a.py" in section
        assert "a.py <-> b.py 2x" in section

    def test_format_activity_empty_when_quiet(self):
        from scantool.git_signals import GitSignals

        quiet = GitSignals(churn={"f.py": 1}, co_change=[], window_days=90)

        # single-commit files are noise, not a "hot" section
        assert format_activity(quiet) == ""


@requires_git
class TestActivityAnchoredWindow:
    """The window covers the last 90 days OF ACTIVITY, anchored at the
    repo's most recent commit — an older project (e.g. last touched 7
    months ago) keeps its signals instead of going silent."""

    @pytest.fixture
    def old_repo(self, tmp_path):
        _git(tmp_path, "init", "-q")
        # a.py: only one old commit, >90d before the latest activity
        (tmp_path / "a.py").write_text("x = 1\n")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-qm", "ancient", date="2019-06-01T12:00:00")
        # b.py: two commits within the last 90 active days
        (tmp_path / "b.py").write_text("y = 2\n")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-qm", "first", date="2020-01-01T12:00:00")
        (tmp_path / "b.py").write_text("y = 22\n")
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "-qm", "last", date="2020-03-01T12:00:00")
        return tmp_path

    def test_old_project_keeps_signals(self, old_repo):
        signals = collect_git_signals(str(old_repo))

        assert signals is not None
        assert signals.churn.get("b.py") == 2
        # a.py last changed >90d before the latest activity — outside the window
        assert "a.py" not in signals.churn

    def test_file_churn_anchored(self, old_repo):
        assert file_churn(str(old_repo / "b.py")) == 2
        assert file_churn(str(old_repo / "a.py")) == 0

    def test_line_edits_anchored(self, old_repo):
        from scantool.git_signals import recent_line_edits

        assert recent_line_edits(str(old_repo / "b.py"))
        assert recent_line_edits(str(old_repo / "a.py")) == {}


@requires_git
class TestPerNodeChurn:
    def test_line_edits_map_recent_commits_onto_current_lines(self, tmp_path):
        from scantool.git_signals import recent_line_edits

        _git(tmp_path, "init", "-q")
        (tmp_path / "mod.py").write_text(
            "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n")
        _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "first")
        # change only beta — the alpha lines keep commit 1, beta gets commit 2
        (tmp_path / "mod.py").write_text(
            "def alpha():\n    return 1\n\n\ndef beta():\n    return 2 + 2\n")
        _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "second")

        line_map = recent_line_edits(str(tmp_path / "mod.py"))

        assert line_map is not None
        # line 6 (the beta body) has a different commit than line 2 (the alpha body)
        assert line_map[6] != line_map[2]

    def test_node_labels_differentiate_edited_function(self, tmp_path):
        from scantool.scanner import FileScanner
        from scantool.git_signals import recent_line_edits

        _git(tmp_path, "init", "-q")
        path = tmp_path / "mod.py"
        path.write_text(
            "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n")
        _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "first")
        path.write_text(
            "def alpha():\n    return 1\n\n\ndef beta():\n    x = 2\n    return x + 2\n")
        _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "second")

        structures = FileScanner().scan_file(str(path), line_edits=recent_line_edits(str(path)))

        by_name = {n.name: n.recent_edits for n in structures if n.name in ("alpha", "beta")}
        assert by_name["beta"] == 2      # def line from c1, body from c2
        assert by_name["alpha"] == 1

    def test_uniform_counts_suppressed(self, tmp_path):
        """Newly created file: all nodes share the same count — labels without
        differentiation repeat the file churn and are suppressed."""
        from scantool.scanner import FileScanner
        from scantool.git_signals import recent_line_edits

        _git(tmp_path, "init", "-q")
        path = tmp_path / "fresh.py"
        path.write_text(
            "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n")
        _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "only")

        structures = FileScanner().scan_file(str(path), line_edits=recent_line_edits(str(path)))

        assert all(n.recent_edits is None for n in structures)

    def test_language_agnostic_markdown(self, tmp_path):
        """Blame is line-based — markdown sections get the same treatment."""
        from scantool.scanner import FileScanner
        from scantool.git_signals import recent_line_edits

        _git(tmp_path, "init", "-q")
        path = tmp_path / "doc.md"
        path.write_text("# Intro\n\nTekst.\n\n# Detaljer\n\nMer tekst.\n")
        _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "first")
        path.write_text("# Intro\n\nTekst.\n\n# Detaljer\n\nOppdatert tekst her.\n")
        _git(tmp_path, "add", "."), _git(tmp_path, "commit", "-qm", "second")

        line_map = recent_line_edits(str(path))

        assert line_map is not None
        FileScanner().scan_file(str(path), line_edits=line_map)  # must not fail on prose

    def test_no_git_returns_none(self, tmp_path):
        from scantool.git_signals import recent_line_edits

        (tmp_path / "f.py").write_text("x = 1\n")

        assert recent_line_edits(str(tmp_path / "f.py")) is None


@requires_git
class TestFormatterIntegration:
    def test_directory_scan_shows_churn_label(self, repo):
        from scantool.scanner import FileScanner
        from scantool.directory_formatter import DirectoryFormatter
        from scantool.server import _annotate_churn

        results = FileScanner().scan_directory(str(repo), pattern="**/*.py")
        _annotate_churn(results, str(repo))
        output = DirectoryFormatter(include_structures=True,
                                    flatten_structures=True).format(str(repo), results)

        assert "2x/90d" in output

    def test_non_git_directory_has_no_labels(self, tmp_path):
        from scantool.scanner import FileScanner
        from scantool.directory_formatter import DirectoryFormatter
        from scantool.server import _annotate_churn, _git_activity_section

        (tmp_path / "f.py").write_text("def fn():\n    return call_something()\n")
        results = FileScanner().scan_directory(str(tmp_path), pattern="**/*.py")
        _annotate_churn(results, str(tmp_path))
        output = DirectoryFormatter(include_structures=True,
                                    flatten_structures=True).format(str(tmp_path), results)

        assert "/90d" not in output
        assert _git_activity_section(str(tmp_path)) == ""
