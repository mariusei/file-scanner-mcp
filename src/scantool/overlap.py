"""
FILE: overlap.py

PROBLEM:
  Several branches wait to be merged into one base. Which of them touch
  the same structure, which introduce the same new name independently,
  which are stacked on each other so their overlap is expected, and which
  are already in the base? git answers per file and per commit; the study's
  merge-plan assignment needed the answer per structure, and needed the
  "already in base" question answered by a named criterion.

SOLUTION:
  Each branch is diffed against ITS OWN merge-base with the base (not the
  base tip, which would report the base's later work as the branch's).
  Structures are the records structural_diff uses, so "touched" means the
  own body, signature or presence changed. Sections: structures touched by
  2+ branches, new names added independently by 2+ branches, commits two
  branches share beyond the base (a stack, so overlap between them is
  expected), and per branch whether it is already in the base and by which
  criterion. A merge-order hint closes it; it is a hint, not a verdict.

SCOPE:
  ✓ N branches vs one base, merge-base per branch, caps on every list
  ✗ no conflict simulation (git merge-tree), no similarity beyond identity
"""

from collections import Counter
from dataclasses import dataclass, field

from .scanner import FileScanner
from .structural_diff import (
    ahead_behind,
    git_output,
    language_of,
    merge_base,
    read_side,
    records,
    short,
)

ROW_CAP = 60
FILE_CAP = 20
NAME_CAP = 25
LABEL_CAP = 72


@dataclass
class BranchReport:
    branch: str
    merge_base: str  # short
    files: int = 0
    touched: dict[tuple[str, str], str] = field(default_factory=dict)  # (path, key) -> + ~ -
    names: dict[tuple[str, str], str] = field(default_factory=dict)  # (path, key) -> qualified name
    added_names: dict[str, tuple[str, int]] = field(default_factory=dict)  # name -> (path, line)
    ahead: int = 0
    behind: int = 0
    in_base: str | None = None  # ancestor | patch-equivalent | tree-equal
    commits: set[str] = field(default_factory=set)  # beyond the merge-base

    @property
    def counts(self) -> Counter:
        return Counter(self.touched.values())


@dataclass
class OverlapResult:
    base: str
    base_sha: str
    reports: list[BranchReport]
    shared: dict[tuple[str, str], list[tuple[str, str]]]  # (path, key) -> [(branch, mark)]
    names: dict[tuple[str, str], str]  # (path, key) -> qualified name, as the language spells it
    colliding: dict[str, list[tuple[str, str, int]]]  # name -> [(branch, path, line)]
    stacked: list[tuple[str, str, int]]  # (branch a, branch b, commits in common)


def _in_base(top: str, base: str, branch: str) -> str | None:
    """The criterion by which the branch is already in the base, if any.
    Patch-equivalence proves the branch can be deleted, not that its content
    is in the base's current tree."""
    if git_output(top, "merge-base", "--is-ancestor", branch, base) is not None:
        return "ancestor"
    if git_output(top, "rev-parse", f"{branch}^{{tree}}") == git_output(
        top, "rev-parse", f"{base}^{{tree}}"
    ):
        return "tree-equal"
    cherry = git_output(top, "cherry", base, branch) or ""
    lines = [line for line in cherry.split("\n") if line]
    if lines and all(line.startswith("-") for line in lines):
        return f"patch-equivalent ({len(lines)} commits)"
    return None


def branch_report(scanner: FileScanner, top: str, base: str, branch: str) -> BranchReport:
    base_of_branch = merge_base(top, base, branch)
    if base_of_branch is None:
        raise ValueError(f"no merge base between {base} and {branch}")
    report = BranchReport(branch, short(top, base_of_branch))
    report.ahead, report.behind = ahead_behind(top, base, branch)[::-1]
    report.in_base = _in_base(top, base, branch)
    report.commits = set((git_output(top, "rev-list", f"{base_of_branch}..{branch}") or "").split())

    name_status = git_output(top, "diff", "--name-status", "-M", base_of_branch, branch) or ""
    for line in name_status.split("\n"):
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, old_path, new_path = parts[0], parts[1], parts[-1]
        old = _records(scanner, top, base_of_branch, old_path) if not status.startswith("A") else {}
        new = _records(scanner, top, branch, new_path) if not status.startswith("D") else {}
        if old is None or new is None:
            continue
        if not old and not new:
            continue
        report.files += 1
        for key, record in new.items():
            report.names[(new_path, key)] = record.name
            if key not in old:
                report.touched[(new_path, key)] = "+"
                if not record.private:  # a name someone chose, not one the language did
                    report.added_names.setdefault(record.bare, (new_path, record.start))
            elif old[key].differs_from(record):
                report.touched[(new_path, key)] = "~"
        for key, record in old.items():
            if key not in new:
                report.touched[(old_path, key)] = "-"
                report.names[(old_path, key)] = record.name
    return report


def _records(scanner: FileScanner, top: str, ref: str, rel: str):
    """None for a file type without a handler; the empty dict for no structure."""
    content = read_side(top, ref, rel)
    if content is None:
        return {}
    structures = scanner.scan_content(content, rel, include_metadata=False)
    if structures is None:
        return None
    return records(structures, content.split("\n"), language_of(scanner, rel))


def overlap(top: str, base: str, branches: list[str]) -> OverlapResult:
    scanner = FileScanner()
    reports = [branch_report(scanner, top, base, branch) for branch in branches]

    by_structure: dict[tuple[str, str], list[tuple[str, str]]] = {}
    names: dict[tuple[str, str], str] = {}
    for report in reports:
        names.update(report.names)
        for site, mark in report.touched.items():
            by_structure.setdefault(site, []).append((report.branch, mark))
    shared = {site: hits for site, hits in by_structure.items() if len(hits) > 1}

    by_name: dict[str, list[tuple[str, str, int]]] = {}
    for report in reports:
        for name, (path, line) in report.added_names.items():
            by_name.setdefault(name, []).append((report.branch, path, line))
    colliding = {name: hits for name, hits in by_name.items() if len(hits) > 1}

    stacked = []
    for i, a in enumerate(reports):
        for b in reports[i + 1 :]:
            common = len(a.commits & b.commits)
            if common:
                stacked.append((a.branch, b.branch, common))

    return OverlapResult(base, short(top, base), reports, shared, names, colliding, stacked)


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def format_overlap(result: OverlapResult) -> str:
    reports = result.reports
    in_base = [r for r in reports if r.in_base]
    parts = [
        f"{len(reports)} {'branch' if len(reports) == 1 else 'branches'} vs {result.base}",
        f"{sum(1 for r in reports if r.touched)} with structural changes",
    ]
    if in_base:
        parts.append(f"{len(in_base)} already in base")
    if result.stacked:
        parts.append(f"{_count(len(result.stacked), 'pair')} sharing history")
    lines = [f"<{', '.join(parts)}> base {result.base} ({result.base_sha})"]

    width = max(len(r.branch) for r in reports)
    for r in reports:
        c = r.counts
        line = (
            f"{r.branch:<{width}}  merge-base {r.merge_base}  {r.ahead} ahead {r.behind} behind  "
            f"{_count(r.files, 'file')}, +{c['+']} ~{c['~']} -{c['-']} structures"
        )
        if r.in_base:
            line += f"   [already in base: {r.in_base}]"
        lines.append(line)
    if any("patch-equivalent" in (r.in_base or "") for r in reports):
        lines.append(
            "  patch-equivalent proves the branch can be deleted, not that its content is in the base's current tree"
        )

    for a, b, common in result.stacked:
        lines.append(
            f"shared history: {a} and {b} share {_count(common, 'commit')} beyond the base; "
            "overlap between them is expected, not a conflict"
        )

    if result.shared:
        rows = sorted(
            (
                (f"{path}::{result.names[(path, key)]}", hits)
                for (path, key), hits in result.shared.items()
            ),
            key=lambda row: (-len(row[1]), row[0]),
        )
        shown = rows[:ROW_CAP]
        files_hit = len({path for path, _ in result.shared})
        lines.append(
            f"overlap (structures touched by 2+ branches): {len(rows)} in {_count(files_hit, 'file')}"
        )
        label_width = min(max(len(label) for label, _ in shown), LABEL_CAP)
        for label, hits in shown:
            marks = "  ".join(f"{branch}({mark})" for branch, mark in sorted(hits))
            lines.append(f"  {label:<{label_width}}   {marks}")
        if len(rows) > len(shown):
            per_file = Counter(path for path, _ in result.shared)
            lines.append(f"  … {len(rows) - len(shown)} more, per file:")
            for path, count in per_file.most_common(FILE_CAP):
                lines.append(f"    {path}   {_count(count, 'structure')}")
    else:
        lines.append("overlap (structures touched by 2+ branches): none")

    if result.colliding:
        names = sorted(result.colliding)
        shown_names = names[:NAME_CAP]
        lines.append(f"colliding new names (added independently on 2+ branches): {len(names)}")
        name_width = min(max(len(n) for n in shown_names), LABEL_CAP)
        for name in shown_names:
            sites = "  ".join(
                f"{branch}:{path}:{line}" for branch, path, line in sorted(result.colliding[name])
            )
            lines.append(f"  {name:<{name_width}}   {sites}")
        if len(names) > len(shown_names):
            lines.append(f"  … and {len(names) - len(shown_names)} more")

    candidates = [r for r in reports if not r.in_base]
    if len(candidates) > 1:
        entangled = Counter(branch for hits in result.shared.values() for branch, _ in hits)
        order = sorted(
            candidates, key=lambda r: (entangled[r.branch], sum(r.counts.values()), r.branch)
        )
        chain = " < ".join(r.branch for r in order)
        first, last = order[0], order[-1]
        if entangled[first.branch] != entangled[last.branch]:
            reason = (
                f"{first.branch} shares {entangled[first.branch]} structures with the others, "
                f"{last.branch} shares {entangled[last.branch]}; the least entangled merges clean, the rest rebase"
            )
        else:
            reason = (
                f"all share {entangled[first.branch]} structures; ordered by change size, "
                f"{first.branch} touches {sum(first.counts.values())} and {last.branch} touches {sum(last.counts.values())}"
            )
        lines.append(f"merge order (a hint, not a verdict): {chain}   ({reason})")
    return "\n".join(lines)


def overlap_to_json(result: OverlapResult) -> dict:
    return {
        "coverage": {
            "branches": len(result.reports),
            "with_structural_changes": sum(1 for r in result.reports if r.touched),
            "already_in_base": {r.branch: r.in_base for r in result.reports if r.in_base},
            "sharing_history": [{"a": a, "b": b, "commits": n} for a, b, n in result.stacked],
        },
        "base": {"ref": result.base, "sha": result.base_sha},
        "branches": [
            {
                "branch": r.branch,
                "merge_base": r.merge_base,
                "ahead": r.ahead,
                "behind": r.behind,
                "files": r.files,
                "counts": dict(r.counts),
                "in_base": r.in_base,
            }
            for r in result.reports
        ],
        "overlap": [
            {
                "address": f"{path}::{result.names[(path, key)]}",
                "branches": [{"branch": b, "mark": m} for b, m in hits],
            }
            for (path, key), hits in result.shared.items()
        ],
        "colliding_names": {
            name: [{"branch": b, "path": p, "line": ln} for b, p, ln in hits]
            for name, hits in result.colliding.items()
        },
    }
