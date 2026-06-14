"""
FILE: ref_diff.py

PROBLEM:
  "What changed since main/HEAD~5/the last release?" is answered today with
  a line diff — precise on characters, blind to structure. A reviewer needs
  WHICH functions are new/changed/removed, with the method visible.

SOLUTION:
  Structural diff between the working tree and a git ref: files from
  `git diff --name-status <ref>`, old state via `git show ref:path`,
  both sides scanned and node-diffed with the same primitive as session
  delta (delta.node_hashes/diff_nodes). Changed/new nodes are shown with
  skeletons, unchanged ones only as counts, whitespace changes reported as
  "no structural change".

SCOPE:
  ✓ Working tree vs ref (includes uncommitted changes — review flow)
  ✗ Not ref-vs-ref (check out first), not line diff (use git diff)
"""

import os
from pathlib import Path
from typing import Optional

from .consensus import find_divergences, format_divergences
from .delta import apply_node_delta, diff_nodes, node_hashes
from .formatter import TreeFormatter
from .git_signals import _run_git
from .scanner import FileScanner


def diff_against_ref(
    directory: str,
    ref: str = "HEAD",
    budget: Optional[int] = 1500,
) -> str:
    """Structural diff of the working tree against a git ref.

    Returns a review-oriented view: per changed file, the new/changed
    nodes with skeletons, removed nodes by name, unchanged as a count.
    """
    toplevel = _run_git(directory, "rev-parse", "--show-toplevel")
    if toplevel is None:
        return f"{directory}: not in a git repo — structural ref diff requires git"
    toplevel = toplevel.strip()

    if _run_git(directory, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
        return f"Unknown ref: {ref!r}"

    name_status = _run_git(directory, "diff", "--name-status", "-M", ref, "--", ".")
    if name_status is None:
        return f"git diff against {ref!r} failed"

    # untracked new files are part of the working tree — review must see them
    untracked = _run_git(directory, "ls-files", "--others", "--exclude-standard") or ""
    for rel_path in untracked.strip().split("\n"):
        if rel_path:
            name_status += f"\nA\t{rel_path}"

    if not name_status.strip():
        return f"No changes against {ref}"

    scanner = FileScanner()
    formatter = TreeFormatter()
    sections: list[str] = []
    unstructured: list[str] = []   # changed, but no structural change
    deleted: list[str] = []
    changed_files: set[str] = set()  # structured files touched — divergence suspects
    n_changed_files = 0

    for line in name_status.strip().split("\n"):
        parts = line.split("\t")
        status = parts[0]
        rel_path = parts[-1]  # on rename (R...) the last field is the new path
        abs_path = os.path.join(toplevel, rel_path)

        if status.startswith("D"):
            deleted.append(rel_path)
            continue
        if not Path(abs_path).is_file():
            continue

        structures = _scan_quietly(scanner, abs_path, budget)
        if structures is None:
            unstructured.append(f"{rel_path} (unstructured file type)")
            continue
        n_changed_files += 1
        changed_files.add(rel_path)

        if status.startswith("A"):
            sections.append(f"\n{rel_path} [new file]\n"
                            + formatter.format(abs_path, structures))
            continue

        renamed = f" [renamed from {parts[1]}]" if status.startswith("R") else ""
        old_content = _run_git(directory, "show", f"{ref}:{parts[1] if status.startswith('R') else rel_path}")
        if old_content is None:
            sections.append(f"\n{rel_path} [changed{renamed}]\n"
                            + formatter.format(abs_path, structures))
            continue

        old_structures = scanner.scan_content(old_content, rel_path,
                                              include_metadata=False) or []
        new_lines = Path(abs_path).read_text(errors="replace").split("\n")
        diff = diff_nodes(
            node_hashes(old_structures, old_content.split("\n")),
            node_hashes(structures, new_lines),
        )
        changed, unchanged = apply_node_delta(structures, diff)

        if changed == 0 and not diff.removed:
            unstructured.append(f"{rel_path} (changed without structural change)")
            continue

        removed = f"\n  removed: {', '.join(diff.removed)}" if diff.removed else ""
        header = (f"\n{rel_path} [changed{renamed}: {changed} new/changed, "
                  f"{unchanged} unchanged]{removed}")
        sections.append(header + "\n" + formatter.format(abs_path, structures))

    summary = [f"Structural diff against {ref}: {n_changed_files} files with changes"]
    if deleted:
        summary.append(f"deleted: {', '.join(deleted)}")
    if unstructured:
        summary.append("without structural change: " + ", ".join(unstructured))
    body = "\n".join(summary) + "\n" + "\n".join(sections)

    review = _connectivity_section(toplevel, changed_files)
    if review:
        body += "\n\n" + review
    return body


def _connectivity_section(toplevel: str, changed_files: set[str]) -> str:
    """Review-mode connectivity on the changed code: the loose ends a change
    introduced. Three subsections, scoped to the changed files:
      - orphan : a route/template you touched that is referenced nowhere
      - dead   : a definition you touched that now has no inbound caller
      - drift  : a touched function that breaks a sibling call-pattern
    The repo is the corpus, the diff is the scope. "Candidates, not verdicts."
    Never raises into the diff — a corpus build failure just means no section."""
    if not changed_files:
        return ""
    try:
        from .code_map import CodeMap
        from .connectivity import corpus_dead_orphans

        result = CodeMap(toplevel).analyze()
        blocks: list[str] = []

        # dead + orphan introduced in the changed files
        dead_all, orphans_all, dyn = corpus_dead_orphans(toplevel, result)
        orphan = [(t, k, p) for loc, t, k, p in orphans_all if loc in changed_files]
        dead = sorted((f, qual) for f, qual in dead_all if f in changed_files)
        if orphan or dead:
            lines = ["── REVIEW: connectivity in changed files (candidates, not verdicts) ──"]
            if orphan:
                lines.append("  orphan (referenced nowhere — candidate dead):")
                for tag, key, pid in orphan[:20]:
                    lines.append(f"    {tag} {key}  ({pid})")
            if dead:
                note = " [dynamic dispatch — down-weighted]" if dyn else ""
                lines.append(f"  candidate-dead (no inbound caller){note}:")
                for f, qual in dead[:20]:
                    lines.append(f"    {qual}  ({f})")
            blocks.append("\n".join(lines))

        # peer divergence on the changed functions (the repo is the peer corpus,
        # the diff is the suspect set — review-mode precision)
        suspects = {(d.file, d.name) for d in result.definitions if d.file in changed_files}
        if suspects:
            file_clusters = {
                f: cluster for cluster, files in result.clusters.items() for f in files
            }
            findings = find_divergences(
                result.definitions, result.calls, suspects=suspects,
                file_clusters=file_clusters,
            )
            if findings:
                blocks.append(format_divergences(findings))

        return "\n\n".join(blocks)
    except Exception:
        return ""


def _scan_quietly(scanner: FileScanner, path: str, budget: Optional[int]):
    try:
        return scanner.scan_file(path, budget=budget)
    except Exception:
        return None
