"""sct decides what .gitignore ignores the way git does, negations included.

Measured origin: `corpus/*` + `!corpus/README.md` — git lists README.md
(`corpus/*` matches the entries, never the directory, so the negation is
free to re-include), sct pruned the whole directory and reported the file
as excluded. The oracle is `git check-ignore -v --no-index` in a throwaway
repo; the walk is checked against `git ls-files --others --exclude-standard`.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scantool.gitignore import load_gitignore
from scantool.scanner import FileScanner

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is the parity oracle")

# (patterns, {path: ignored by git?}). The expectations are git's own answers
# (git 2.54); the test asks git again and fails on either side disagreeing.
CASES = [
    (["dir/*", "!dir/file.md"], {"dir/file.md": False, "dir/other.md": True}),
    (["dir/", "!dir/file.md"], {"dir/file.md": True, "dir/other.md": True}),
    (["dir", "!dir/file.md"], {"dir/file.md": True, "dir/other.md": True}),
    (
        ["*.md", "!README.md"],
        {"README.md": False, "notes.md": True, "dir/README.md": False, "dir/notes.md": True},
    ),
    (
        ["dir/*", "!dir/sub/", "dir/sub/*", "!dir/sub/keep.md"],
        {
            "dir/a.md": True,
            "dir/sub/keep.md": False,
            "dir/sub/drop.md": True,
            "dir/deep/x.md": True,
        },
    ),
    # The negation names the directory itself, so it is not excluded and
    # its files fall through to their own (absent) matches: re-included.
    # (`gen`, not `build`: the walk always prunes build/ regardless of git.)
    (
        ["**/gen/", "!src/gen/"],
        {"src/gen/a.py": False, "gen/a.py": True, "lib/gen/b.py": True, "src/a.py": False},
    ),
    (["!dir/file.md", "dir/*"], {"dir/file.md": True, "dir/other.md": True}),
    (["*.md", "!/README.md"], {"README.md": False, "dir/README.md": True}),
]
# `*` in the scanned directory's own .gitignore: the decisions agree with git,
# but the walk deliberately does not — an explicitly named directory is read
# even when its .gitignore ignores everything (the uv `.venv/.gitignore` case).
ROOT_STAR = (["*", "!keep.py"], {"keep.py": False, "drop.py": True, "dir/keep.py": True})


def _ids(cases):
    return [" ".join(patterns) for patterns, _ in cases]


_GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=_GIT_ENV
    )
    return result.stdout


def _repo(root: Path, patterns: list[str], paths: list[str]) -> Path:
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=_GIT_ENV)
    (root / ".gitignore").write_text("\n".join(patterns) + "\n")
    for path in paths:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text("# heading\n")
    return root


def _git_ignores(repo: Path, path: str) -> str | None:
    """The pattern git says ignores the path, or None (a negation clears it)."""
    line = _git(repo, "check-ignore", "-v", "--no-index", "--non-matching", path)
    pattern = line.split("\t", 1)[0].split(":", 2)[2]  # "<source>:<line>:<pattern>"
    return pattern if pattern and not pattern.startswith("!") else None


@pytest.mark.parametrize("patterns, expected", [*CASES, ROOT_STAR], ids=_ids([*CASES, ROOT_STAR]))
def test_decisions_agree_with_git_check_ignore(tmp_path, patterns, expected):
    repo = _repo(tmp_path, patterns, list(expected))
    stack = load_gitignore(repo)
    assert stack is not None
    for path, ignored in expected.items():
        by = _git_ignores(repo, path)
        assert (by is not None) == ignored, f"the table disagrees with git for {path}"
        assert stack.decide(path) == (f"{repo / '.gitignore'}: {by}" if by else None), path


@pytest.mark.parametrize("patterns, expected", CASES, ids=_ids(CASES))
def test_walk_sees_exactly_what_git_does_not_ignore(tmp_path, patterns, expected):
    repo = _repo(tmp_path, patterns, list(expected))
    untracked = set(_git(repo, "ls-files", "--others", "--exclude-standard").split())
    sweep = FileScanner().sweep(str(repo))
    seen = {Path(p).relative_to(repo).as_posix() for p in sweep.results}
    assert seen == untracked


def test_walk_enters_a_directory_whose_entries_are_ignored_but_prunes_an_ignored_one(tmp_path):
    entries = _repo(
        tmp_path / "entries", ["dir/*", "!dir/keep.md"], ["dir/keep.md", "dir/a.md", "dir/b.md"]
    )
    sweep = FileScanner().sweep(str(entries))
    assert [Path(p).name for p in sweep.results] == [".gitignore", "keep.md"]
    # counted per file: the walk went in
    assert sweep.excluded[f"{entries / '.gitignore'}: dir/*"] == 2

    whole = _repo(
        tmp_path / "whole", ["dir/", "!dir/keep.md"], ["dir/keep.md", "dir/a.md", "dir/b.md"]
    )
    sweep = FileScanner().sweep(str(whole))
    assert [Path(p).name for p in sweep.results] == [".gitignore"]
    # counted once: the directory was pruned, never entered
    assert sweep.excluded[f"{whole / '.gitignore'}: dir/"] == 1
