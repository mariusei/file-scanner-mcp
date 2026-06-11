"""
FILE: git_signals.py

PROBLEM:
  Git history carries signals a human uses to understand a project
  (what is being worked on, what changes together), but scantool did not
  use them.

SOLUTION:
  File-level and language-agnostic — works as well for documentation and
  config repos as for code. Everything is optional: without git, without a
  repo, or on timeout, None/empty is returned, and output must be identical
  to output before this module existed. Absence of signal = absence of label.

SCOPE:
  ✓ churn (commits per file in window), co-change (files changed together)
  ✗ Not per-function churn (requires hunk→node mapping)
  ✗ Not blame/author analysis
"""

import os
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_GIT_TIMEOUT = 5.0
# Commits touching more files than this are skipped for co-change —
# mass refactors and formatting sweeps say nothing about coupling
_MASS_COMMIT_LIMIT = 20

_COMMIT_SEP = "\x01"


@dataclass
class GitSignals:
    """File-level git activity, paths relative to the queried directory."""

    churn: dict[str, int]                    # path -> commits in window
    co_change: list[tuple[str, str, int]]    # (path_a, path_b, count), descending
    window_days: int


def _run_git(directory: str, *args: str) -> Optional[str]:
    """Run a git command; None on any failure (no git, no repo, timeout)."""
    try:
        result = subprocess.run(
            ["git", "-C", directory, *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _last_activity_ts(directory: str) -> Optional[float]:
    """Unix timestamp of the repository's most recent commit."""
    out = _run_git(directory, "log", "-1", "--format=%ct")
    if out is None:
        return None
    try:
        return float(out.strip())
    except ValueError:
        return None


def _window_start(directory: str, window_days: int) -> Optional[float]:
    """Window anchored at the project's LAST COMMIT, not at wall-clock now —
    "the last 90 days of activity". Older projects keep their signals; for
    actively developed projects this is indistinguishable from a now-window."""
    anchor = _last_activity_ts(directory)
    if anchor is None:
        return None
    return anchor - window_days * 86400


def collect_git_signals(
    directory: str,
    window_days: int = 90,
    co_change_top: int = 5,
) -> Optional[GitSignals]:
    """Collect churn and co-change for files under directory.

    The window covers the last window_days of ACTIVITY (anchored at the
    most recent commit). Returns None when the directory is not in a git
    repository or git is unavailable — callers must treat that as
    "no signal", not as an error.
    """
    toplevel = _run_git(directory, "rev-parse", "--show-toplevel")
    if toplevel is None:
        return None
    toplevel = toplevel.strip()

    since = _window_start(directory, window_days)
    if since is None:
        return None

    log = _run_git(
        directory, "log",
        f"--since=@{int(since)}",
        "--name-only",
        f"--pretty=format:{_COMMIT_SEP}",
        "--", ".",
    )
    if log is None:
        return None

    directory_abs = os.path.abspath(directory)
    churn: Counter = Counter()
    pairs: Counter = Counter()

    for block in log.split(_COMMIT_SEP):
        files = []
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            abs_path = os.path.join(toplevel, line)
            # only files that still exist — history also names deleted paths
            if not os.path.isfile(abs_path):
                continue
            rel = os.path.relpath(abs_path, directory_abs)
            if rel.startswith(".."):
                continue
            files.append(rel)

        for rel in files:
            churn[rel] += 1
        if 2 <= len(files) <= _MASS_COMMIT_LIMIT:
            for i, a in enumerate(files):
                for b in files[i + 1:]:
                    pairs[tuple(sorted((a, b)))] += 1

    co_change = [
        (a, b, count)
        for (a, b), count in pairs.most_common(co_change_top)
        if count >= 2
    ]
    return GitSignals(churn=dict(churn), co_change=co_change, window_days=window_days)


def format_activity(signals: GitSignals, max_entries: int = 8) -> str:
    """Compact activity section for preview output; "" when nothing to say."""
    hot = [
        (path, count)
        for path, count in sorted(signals.churn.items(), key=lambda kv: -kv[1])
        if count >= 2
    ][:max_entries]

    lines = []
    if hot:
        lines.append("  hot: " + ", ".join(f"{p} {c}x" for p, c in hot))
    if signals.co_change:
        lines.append("  co-change: " + ", ".join(
            f"{a} <-> {b} {c}x" for a, b, c in signals.co_change))
    if not lines:
        return ""
    return (f"\n━━━ GIT ACTIVITY (last {signals.window_days}d of activity) ━━━\n"
            + "\n".join(lines))


def recent_line_edits(file_path: str, window_days: int = 90) -> Optional[dict[int, str]]:
    """Map current line numbers to the commit that last touched them,
    filtered to the last window_days of ACTIVITY (anchored at the repo's
    most recent commit). Built on git blame, so history is projected
    onto TODAY's line numbers — no hunk drift. Line-based and therefore
    language-agnostic. None without git/repo; uncommitted lines count as
    one in-progress edit.

    One blame call per file (~20-40ms) — suited for scan_file, too costly
    to run per file in directory scans.
    """
    parent = str(Path(file_path).parent) or "."
    cutoff = _window_start(parent, window_days)
    if cutoff is None:
        return None
    out = _run_git(parent, "blame", "--line-porcelain", "--",
                   os.path.abspath(file_path))
    if out is None:
        return None
    edits: dict[int, str] = {}
    current_sha = ""
    current_line = 0
    current_ts = 0.0
    known_ts: dict[str, float] = {}

    for line in out.split("\n"):
        if line.startswith("\t"):
            if current_ts >= cutoff:
                edits[current_line] = current_sha
            continue
        parts = line.split()
        if len(parts) >= 3 and len(parts[0]) == 40 and all(
                c in "0123456789abcdef" for c in parts[0]):
            current_sha = parts[0]
            current_line = int(parts[2])
            current_ts = known_ts.get(current_sha, 0.0)
        elif line.startswith("committer-time "):
            current_ts = float(line.split()[1])
            known_ts[current_sha] = current_ts
    return edits


def file_churn(file_path: str, window_days: int = 90) -> Optional[int]:
    """Commits touching a single file in the last window_days of activity
    (anchored at the repo's most recent commit); None without git/repo."""
    parent = str(Path(file_path).parent) or "."
    since = _window_start(parent, window_days)
    if since is None:
        return None
    out = _run_git(
        parent, "rev-list", "--count",
        f"--since=@{int(since)}",
        "HEAD", "--", os.path.abspath(file_path),
    )
    if out is None:
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None
