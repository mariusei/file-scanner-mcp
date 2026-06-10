"""
FIL: git_signals.py

PROBLEM:
  Git-historikk bærer signaler et menneske bruker for å forstå et prosjekt
  (hva jobbes det med, hva endres sammen), men scantool brukte dem ikke.

LØSNING:
  Fil-nivå og språkagnostisk — virker like godt for dokumentasjons- og
  config-repoer som for kode. Alt er valgfritt: uten git, uten repo, eller
  ved timeout returneres None/tomt, og output skal være identisk med
  output før denne modulen fantes. Fravær av signal = fravær av label.

SCOPE:
  ✓ churn (commits per fil i vindu), co-change (filer endret sammen)
  ✗ Ikke per-funksjon-churn (krever hunk→node-mapping)
  ✗ Ikke blame/forfatter-analyse
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


def collect_git_signals(
    directory: str,
    window_days: int = 90,
    co_change_top: int = 5,
) -> Optional[GitSignals]:
    """Collect churn and co-change for files under directory.

    Returns None when the directory is not in a git repository or git is
    unavailable — callers must treat that as "no signal", not as an error.
    """
    toplevel = _run_git(directory, "rev-parse", "--show-toplevel")
    if toplevel is None:
        return None
    toplevel = toplevel.strip()

    log = _run_git(
        directory, "log",
        f"--since={window_days} days ago",
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
    return f"\n━━━ GIT ACTIVITY (last {signals.window_days}d) ━━━\n" + "\n".join(lines)


def file_churn(file_path: str, window_days: int = 90) -> Optional[int]:
    """Commits touching a single file in the window; None without git/repo."""
    parent = str(Path(file_path).parent) or "."
    out = _run_git(
        parent, "rev-list", "--count",
        f"--since={window_days} days ago",
        "HEAD", "--", os.path.abspath(file_path),
    )
    if out is None:
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None
