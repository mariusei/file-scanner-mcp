"""
FIL: ref_diff.py

PROBLEM:
  "Hva er endret siden main/HEAD~5/forrige release?" besvares i dag med
  linjediff — presist på tegn, blindt for struktur. En reviewer trenger
  HVILKE funksjoner som er nye/endrede/fjernet, med metoden synlig.

LØSNING:
  Strukturell diff mellom arbeidstreet og en git-ref: filer fra
  `git diff --name-status <ref>`, gammel tilstand via `git show ref:path`,
  begge sider scannes og node-diffes med samme primitiv som sesjons-delta
  (delta.node_hashes/diff_nodes). Endrede/nye noder vises med skjelett,
  uendrede kun som tall, whitespace-endringer rapporteres som
  "ingen strukturell endring".

SCOPE:
  ✓ Arbeidstre vs ref (inkluderer ucommittede endringer — review-flyt)
  ✗ Ikke ref-vs-ref (sjekk ut først), ikke linjediff (bruk git diff)
"""

import os
from pathlib import Path
from typing import Optional

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
        return f"{directory}: ikke i et git-repo — strukturell ref-diff krever git"
    toplevel = toplevel.strip()

    if _run_git(directory, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is None:
        return f"Ukjent ref: {ref!r}"

    name_status = _run_git(directory, "diff", "--name-status", "-M", ref, "--", ".")
    if name_status is None:
        return f"git diff mot {ref!r} feilet"

    # untracked nye filer er en del av arbeidstreet — review må se dem
    untracked = _run_git(directory, "ls-files", "--others", "--exclude-standard") or ""
    for rel_path in untracked.strip().split("\n"):
        if rel_path:
            name_status += f"\nA\t{rel_path}"

    if not name_status.strip():
        return f"Ingen endringer mot {ref}"

    scanner = FileScanner()
    formatter = TreeFormatter()
    sections: list[str] = []
    unstructured: list[str] = []   # endret, men ingen strukturell endring
    deleted: list[str] = []
    n_changed_files = 0

    for line in name_status.strip().split("\n"):
        parts = line.split("\t")
        status = parts[0]
        rel_path = parts[-1]  # ved rename (R...) er siste felt ny sti
        abs_path = os.path.join(toplevel, rel_path)

        if status.startswith("D"):
            deleted.append(rel_path)
            continue
        if not Path(abs_path).is_file():
            continue

        structures = _scan_quietly(scanner, abs_path, budget)
        if structures is None:
            unstructured.append(f"{rel_path} (ikke strukturert filtype)")
            continue
        n_changed_files += 1

        if status.startswith("A"):
            sections.append(f"\n{rel_path} [ny fil]\n"
                            + formatter.format(abs_path, structures))
            continue

        renamed = f" [omdøpt fra {parts[1]}]" if status.startswith("R") else ""
        old_content = _run_git(directory, "show", f"{ref}:{parts[1] if status.startswith('R') else rel_path}")
        if old_content is None:
            sections.append(f"\n{rel_path} [endret{renamed}]\n"
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
            unstructured.append(f"{rel_path} (endret uten strukturell endring)")
            continue

        removed = f"\n  fjernet: {', '.join(diff.removed)}" if diff.removed else ""
        header = (f"\n{rel_path} [endret{renamed}: {changed} ny/endret, "
                  f"{unchanged} uendret]{removed}")
        sections.append(header + "\n" + formatter.format(abs_path, structures))

    summary = [f"Strukturell diff mot {ref}: {n_changed_files} filer med endringer"]
    if deleted:
        summary.append(f"slettet: {', '.join(deleted)}")
    if unstructured:
        summary.append("uten strukturell endring: " + ", ".join(unstructured))
    return "\n".join(summary) + "\n" + "\n".join(sections)


def _scan_quietly(scanner: FileScanner, path: str, budget: Optional[int]):
    try:
        return scanner.scan_file(path, budget=budget)
    except Exception:
        return None
