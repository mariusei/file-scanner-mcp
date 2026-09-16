"""
FILE: overlap.py

PROBLEM:
  Several branches wait to be merged into one base. Which of them touch
  the same structure, which introduce the same new name independently,
  which are stacked on each other so their overlap is expected, and which
  are already in the base? git answers per file and per commit; the study's
  merge-plan assignment needed the answer per structure, and needed the
  "already in base" question answered by a named criterion. A name that
  reached a stacked branch through shared commits was added once, so it
  is not a collision between the two. Two more
  questions decide a merge recommendation and were missing at structure
  level: has the base itself moved a shared structure since the branches
  forked (both branches are then behind, not just each other), and for a
  stacked pair, what stays shared once their common commits are removed.

SOLUTION:
  Each branch is diffed against ITS OWN merge-base with the base (not the
  base tip, which would report the base's later work as the branch's).
  Structures are the records structural_diff uses, so "touched" means the
  own body, signature or presence changed. Sections: structures touched by
  2+ branches, each with a base mark when the base tip changed it since the
  oldest fork point among the branches touching it; new names added
  independently by 2+ branches; commits two branches share beyond the base
  (a stack, so overlap between them is expected) with the residual overlap
  beyond their mutual merge-base; and per branch whether it is already in
  the base and by which criterion. A merge-order hint closes it, counting
  only the residual for stacked pairs; it is a hint, not a verdict.

SCOPE:
  ✓ N branches vs one base, merge-base per branch, caps on every list
  ✓ base marks and residuals computed only for the shared set (cheap)
  ✓ a Scope (path prefix, node kind) applied where records are read, so
    counts, rows, residuals and the merge order all agree with it
  ✗ no conflict simulation (git merge-tree), no similarity beyond identity
  ✗ base marks follow the path as the branch spells it; a rename on the
    base side reads as removed
"""

from collections import Counter
from dataclasses import dataclass, field

from .scanner import FileScanner
from .structural_diff import (
    NodeRecord,
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
RESIDUAL_CAP = 20

Site = tuple[str, str]  # (path, key)


@dataclass
class Scope:
    """Which structures take part: those in files under `path` (a
    repository-relative directory or file, forward slashes) whose type is
    `kind` (as scan prints it). None on either side means no filter. Applied
    where records are read, so every number downstream agrees with it."""

    path: str | None = None
    kind: str | None = None

    def __post_init__(self) -> None:
        self.path = self.path.replace("\\", "/").rstrip("/") or None if self.path else None
        self.kind = self.kind or None

    def admits_path(self, path: str) -> bool:
        return not self.path or path == self.path or path.startswith(self.path + "/")

    def admits(self, path: str, kind: str) -> bool:
        return self.admits_path(path) and (not self.kind or kind == self.kind)

    @property
    def label(self) -> str:
        parts = [
            f"{name} {value}" for name, value in (("path", self.path), ("kind", self.kind)) if value
        ]
        return ", ".join(parts)


@dataclass
class BranchReport:
    branch: str
    merge_base: str  # short
    files: int = 0
    touched: dict[Site, str] = field(default_factory=dict)  # + ~ -
    # qualified name as the language spells it, and the record's type
    names: dict[Site, str] = field(default_factory=dict)
    kinds: dict[Site, str] = field(default_factory=dict)
    # bare name -> (path, line, kind); a name someone chose, not one the language did
    added_names: dict[str, tuple[str, int, str]] = field(default_factory=dict)
    ahead: int = 0
    behind: int = 0
    in_base: str | None = None  # ancestor | patch-equivalent | tree-equal
    commits: set[str] = field(default_factory=set)  # beyond the merge-base

    @property
    def counts(self) -> Counter:
        return Counter(self.touched.values())


@dataclass
class SharedHistory:
    a: str
    b: str
    commits: int  # in common beyond the base
    residual: dict[Site, str]  # touched by both beyond their mutual merge-base -> name

    @property
    def residual_files(self) -> int:
        return len({path for path, _ in self.residual})

    @property
    def rows(self) -> list[tuple[str, str]]:
        """The residual as (path, name), by path then name."""
        return sorted((path, name) for (path, _), name in self.residual.items())


@dataclass
class OverlapResult:
    base: str
    base_sha: str
    reports: list[BranchReport]
    shared: dict[Site, list[tuple[str, str]]]  # -> [(branch, mark)]
    names: dict[Site, str]
    kinds: dict[Site, str]
    base_moved: dict[Site, str]  # shared site -> how the base tip changed it since the oldest fork
    colliding: dict[str, list[tuple[str, str, int, str]]]  # name -> [(branch, path, line, kind)]
    stacked: list[SharedHistory]
    scope: Scope = field(default_factory=Scope)


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


def branch_report(
    scanner: FileScanner, top: str, base: str, branch: str, scope: Scope
) -> BranchReport:
    base_of_branch = merge_base(top, base, branch)
    if base_of_branch is None:
        raise ValueError(f"no merge base between {base} and {branch}")
    report = BranchReport(branch, short(top, base_of_branch))
    report.ahead, report.behind = ahead_behind(top, base, branch)[::-1]
    report.in_base = _in_base(top, base, branch)
    report.commits = set((git_output(top, "rev-list", f"{base_of_branch}..{branch}") or "").split())
    _diff_structures(scanner, top, base_of_branch, branch, report, scope)
    return report


def _diff_structures(
    scanner: FileScanner,
    top: str,
    old_ref: str,
    new_ref: str,
    report: BranchReport,
    scope: Scope,
) -> None:
    """Every structure in scope whose own body, signature or presence differs
    between the refs, into the report. A file counts when it is in the
    scope's path and has structure; the kind narrows the structures, not
    the files (a file with none of that kind touched still changed)."""
    name_status = git_output(top, "diff", "--name-status", "-M", old_ref, new_ref) or ""
    for line in name_status.split("\n"):
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, old_path, new_path = parts[0], parts[1], parts[-1]
        old_in, new_in = scope.admits_path(old_path), scope.admits_path(new_path)
        if not old_in and not new_in:
            continue
        old = _records(scanner, top, old_ref, old_path) if not status.startswith("A") else {}
        new = _records(scanner, top, new_ref, new_path) if not status.startswith("D") else {}
        if old is None or new is None:
            continue
        if not old and not new:
            continue
        report.files += 1
        for key, record in new.items():
            if not new_in or not scope.admits(new_path, record.type):
                continue
            report.names[(new_path, key)] = record.name
            report.kinds[(new_path, key)] = record.type
            if key not in old:
                report.touched[(new_path, key)] = "+"
                if not record.private:  # a name someone chose, not one the language did
                    report.added_names.setdefault(
                        record.bare, (new_path, record.start, record.type)
                    )
            elif old[key].differs_from(record):
                report.touched[(new_path, key)] = "~"
        for key, record in old.items():
            if key not in new and old_in and scope.admits(old_path, record.type):
                report.touched[(old_path, key)] = "-"
                report.names[(old_path, key)] = record.name
                report.kinds[(old_path, key)] = record.type


def _records(scanner: FileScanner, top: str, ref: str, rel: str) -> dict[str, NodeRecord] | None:
    """None for a file type without a handler; the empty dict for no structure."""
    content = read_side(top, ref, rel)
    if content is None:
        return {}
    structures = scanner.scan_content(content, rel, include_metadata=False)
    if structures is None:
        return None
    return records(structures, content.split("\n"), language_of(scanner, rel))


def _mark(old: dict[str, NodeRecord], new: dict[str, NodeRecord], key: str) -> str | None:
    if key in new and key not in old:
        return "+"
    if key in old and key not in new:
        return "-"
    if key in old and key in new and old[key].differs_from(new[key]):
        return "~"
    return None


def _base_moved(
    scanner: FileScanner, top: str, base: str, shared: dict[Site, list[tuple[str, str]]]
) -> dict[Site, str]:
    """For each shared structure, how the base tip changed it since the
    oldest fork point among the branches touching it (the octopus merge-base
    of the base and those branches). Records are read once per (ref, path)."""
    base_sha = (git_output(top, "rev-parse", f"{base}^{{commit}}") or "").strip()
    since_of: dict[tuple[str, ...], str | None] = {}
    at: dict[tuple[str, str], dict[str, NodeRecord] | None] = {}
    moved: dict[Site, str] = {}
    for (path, key), hits in shared.items():
        branches = tuple(sorted(branch for branch, _ in hits))
        if branches not in since_of:
            fork = git_output(top, "merge-base", "--octopus", base, *branches)
            since_of[branches] = fork.strip() if fork else None
        since = since_of[branches]
        if since is None or since == base_sha:
            continue
        for ref in (since, base_sha):
            if (ref, path) not in at:
                at[(ref, path)] = _records(scanner, top, ref, path)
        old, new = at[(since, path)], at[(base_sha, path)]
        if old is None or new is None:
            continue
        mark = _mark(old, new, key)
        if mark:
            moved[(path, key)] = mark
    return moved


def _residual(
    scanner: FileScanner, top: str, a: str, b: str, scope: Scope
) -> tuple[dict[Site, str], set[str]]:
    """Structures both branches touch beyond their mutual merge-base (what
    stays shared once one of them is merged), and the new names both added
    beyond it: those are the only names the pair chose independently."""
    mutual = merge_base(top, a, b)
    if mutual is None:
        return {}, set()
    sides = []
    for branch in (a, b):
        side = BranchReport(branch, mutual)
        _diff_structures(scanner, top, mutual, branch, side, scope)
        sides.append(side)
    common = sides[0].touched.keys() & sides[1].touched.keys()
    both_added = sides[0].added_names.keys() & sides[1].added_names.keys()
    return {site: sides[0].names[site] for site in sorted(common)}, set(both_added)


def overlap(top: str, base: str, branches: list[str], scope: Scope | None = None) -> OverlapResult:
    scope = scope or Scope()
    scanner = FileScanner()
    reports = [branch_report(scanner, top, base, branch, scope) for branch in branches]

    by_structure: dict[Site, list[tuple[str, str]]] = {}
    names: dict[Site, str] = {}
    kinds: dict[Site, str] = {}
    for report in reports:
        names.update(report.names)
        kinds.update(report.kinds)
        for site, mark in report.touched.items():
            by_structure.setdefault(site, []).append((report.branch, mark))
    shared = {site: hits for site, hits in by_structure.items() if len(hits) > 1}
    base_moved = _base_moved(scanner, top, base, shared)

    stacked = []
    inherited: dict[tuple[str, str], set[str]] = {}  # (a, b) -> names b got from a's commits
    for i, a in enumerate(reports):
        for b in reports[i + 1 :]:
            common = len(a.commits & b.commits)
            if common:
                residual, independent = _residual(scanner, top, a.branch, b.branch, scope)
                stacked.append(SharedHistory(a.branch, b.branch, common, residual))
                shared_names = a.added_names.keys() & b.added_names.keys()
                inherited[(a.branch, b.branch)] = shared_names - independent

    by_name: dict[str, list[tuple[str, str, int, str]]] = {}
    for report in reports:
        for name, (path, line, kind) in report.added_names.items():
            by_name.setdefault(name, []).append((report.branch, path, line, kind))
    colliding = {}
    for name, hits in by_name.items():
        # a name that reached a stacked branch through the commits it shares
        # with an earlier one was added once, not independently: the later
        # branch's entry is dropped, the earlier one stays
        added_by = [hit[0] for hit in hits]
        dropped = {
            later
            for (earlier, later), names in inherited.items()
            if name in names and earlier in added_by and later in added_by
        }
        kept = [hit for hit in hits if hit[0] not in dropped]
        if len(kept) > 1:
            colliding[name] = kept

    return OverlapResult(
        base, short(top, base), reports, shared, names, kinds, base_moved, colliding, stacked, scope
    )


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _entanglement(result: OverlapResult) -> Counter:
    """Shared structures per branch that stay shared after merging: those
    shared with a branch it does not stack on, plus the residual with the
    ones it does. A stacked pair's common commits count on neither side."""
    stacked_with = {frozenset((s.a, s.b)) for s in result.stacked}
    sites: dict[str, set[Site]] = {}
    for site, hits in result.shared.items():
        branches = [branch for branch, _ in hits]
        for x in branches:
            if any(frozenset((x, y)) not in stacked_with for y in branches if y != x):
                sites.setdefault(x, set()).add(site)
    for s in result.stacked:
        for branch in (s.a, s.b):
            sites.setdefault(branch, set()).update(s.residual)
    return Counter({branch: len(found) for branch, found in sites.items()})


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
    head = f"<{', '.join(parts)}> base {result.base} ({result.base_sha})"
    if result.scope.label:
        head += f"  [{result.scope.label}]"
    lines = [head]

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

    for s in result.stacked:
        lines.append(
            f"shared history: {s.a} and {s.b} share {_count(s.commits, 'commit')} beyond the base; "
            "overlap between them is expected, not a conflict"
        )
        residual = (
            f"{_count(len(s.residual), 'structure')} in {_count(s.residual_files, 'file')}"
            if s.residual
            else "none"
        )
        lines.append(f"  residual beyond their shared commits: {residual}")
        lines.extend(f"    {path}::{name}" for path, name in s.rows[:RESIDUAL_CAP])
        if len(s.rows) > RESIDUAL_CAP:
            lines.append(f"    … {len(s.rows) - RESIDUAL_CAP} more")

    if result.shared:
        rows = sorted(
            (
                (f"{path}::{result.names[(path, key)]}", hits, result.base_moved.get((path, key)))
                for (path, key), hits in result.shared.items()
            ),
            key=lambda row: (-len(row[1]), row[0]),
        )
        shown = rows[:ROW_CAP]
        files_hit = len({path for path, _ in result.shared})
        header = f"overlap (structures touched by 2+ branches): {len(rows)} in {_count(files_hit, 'file')}"
        if result.base_moved:
            header += f", {len(result.base_moved)} also changed in base"
        lines.append(header)
        label_width = min(max(len(label) for label, _, _ in shown), LABEL_CAP)
        for label, hits, base_mark in shown:
            marks = "  ".join(f"{branch}({mark})" for branch, mark in sorted(hits))
            if base_mark:
                marks += f"  base({base_mark})"
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
                f"{branch}:{path}:{line}"
                for branch, path, line, _ in sorted(result.colliding[name])
            )
            lines.append(f"  {name:<{name_width}}   {sites}")
        if len(names) > len(shown_names):
            lines.append(f"  … and {len(names) - len(shown_names)} more")

    candidates = [r for r in reports if not r.in_base]
    if len(candidates) > 1:
        entangled = _entanglement(result)
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
        in_stack = {branch for s in result.stacked for branch in (s.a, s.b)}
        if any(r.branch in in_stack for r in candidates):
            reason += "; stacked pairs count only their residual beyond shared commits"
        lines.append(f"merge order (a hint, not a verdict): {chain}   ({reason})")
    return "\n".join(lines)


def overlap_to_json(result: OverlapResult) -> dict:
    return {
        "coverage": {
            "branches": len(result.reports),
            "with_structural_changes": sum(1 for r in result.reports if r.touched),
            "already_in_base": {r.branch: r.in_base for r in result.reports if r.in_base},
            "sharing_history": [
                {
                    "a": s.a,
                    "b": s.b,
                    "commits": s.commits,
                    "residual": {
                        "count": len(s.residual),
                        "files": s.residual_files,
                        "structures": [
                            {"path": path, "name": name} for path, name in s.rows[:RESIDUAL_CAP]
                        ],
                    },
                }
                for s in result.stacked
            ],
            "filters": {"path": result.scope.path, "kind": result.scope.kind},
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
                "kind": result.kinds[(path, key)],
                "base": result.base_moved.get((path, key)),
                "branches": [{"branch": b, "mark": m} for b, m in hits],
            }
            for (path, key), hits in result.shared.items()
        ],
        "colliding_names": {
            name: [{"branch": b, "path": p, "line": ln, "kind": k} for b, p, ln, k in hits]
            for name, hits in result.colliding.items()
        },
    }
