"""
FILE: focus.py

PROBLEM:
  The read step after a scan: agents want to read "this function", not guess
  line ranges with Read/sed. Line numbers are ephemeral; node names are stable.

SOLUTION:
  Look up a node by name or qualified path (ClassA.method, heading text),
  render the file skeleton at depth 1 with the path to the node expanded
  (parent context), and the node itself verbatim with line numbers. Reuses
  TreeFormatter: the verbatim view IS the formatter's code_excerpt mechanism.

SCOPE:
  ✓ Exact name, qualified path, substring fallback (markdown headings)
  ✓ Ambiguity → error message with qualified candidates
  ✗ No delta/git integration — a focused read is not a scan
"""

from dataclasses import replace

from .formatter import TreeFormatter
from .languages import StructureNode


def format_focus(file_path: str, structures: list[StructureNode],
                 source_lines: list[str], focus: str) -> str:
    """Render skeleton-with-context + verbatim body for the focused node."""
    matches = _resolve(structures, focus)
    if len(matches) != 1:
        return _resolution_error(structures, focus, matches)

    target, ancestors = matches[0]
    path_ids = {id(node) for node in (*ancestors, target)}
    pruned = _prune(structures, target, path_ids, source_lines)

    qualified = ".".join(node.name for node in (*ancestors, target))
    header = f"focus: {qualified} @{target.start_line}-{target.end_line}"
    return header + "\n" + TreeFormatter().format(file_path, pruned)


def _walk(structures: list[StructureNode], ancestors: tuple = ()):
    for node in structures:
        if node.type == "file-info":
            continue
        yield node, ancestors
        yield from _walk(node.children, (*ancestors, node))


def _resolve(structures: list[StructureNode],
             focus: str) -> list[tuple[StructureNode, tuple]]:
    """Match tiers: exact name, qualified path, case-insensitive substring."""
    nodes = list(_walk(structures))

    exact = [(n, a) for n, a in nodes if n.name == focus]
    if exact:
        return exact

    if "." in focus:
        *parents, leaf = focus.split(".")
        qualified = []
        for node, ancestors in nodes:
            if node.name != leaf:
                continue
            names = [a.name for a in ancestors]
            it = iter(names)
            if all(seg in it for seg in parents):  # subsequence, in order
                qualified.append((node, ancestors))
        if qualified:
            return qualified

    needle = focus.lower()
    return [(n, a) for n, a in nodes if needle in n.name.lower()]


def _resolution_error(structures: list[StructureNode], focus: str,
                      matches: list[tuple[StructureNode, tuple]]) -> str:
    if matches:
        listed = "\n".join(
            f"  {'.'.join(node.name for node in (*anc, n))} @{n.start_line}"
            for n, anc in matches[:10])
        return (f"focus '{focus}' is ambiguous ({len(matches)} matches) — "
                f"use a qualified path:\n{listed}")
    available = ", ".join(n.name for n, a in _walk(structures) if not a)
    return (f"focus '{focus}' matches no node. "
            f"Top-level nodes: {available}")


def _prune(structures: list[StructureNode], target: StructureNode,
           path_ids: set[int], source_lines: list[str]) -> list[StructureNode]:
    """Depth-1 copies; the ancestor path stays expanded, the target verbatim."""
    pruned = []
    for node in structures:
        if node.type == "file-info":
            pruned.append(node)
        elif id(node) == id(target):
            excerpt = source_lines[node.start_line - 1:node.end_line]
            pruned.append(replace(node, children=[], code_skeleton=None,
                                  code_excerpt=excerpt))
        elif id(node) in path_ids:
            shallow = replace(node, code_skeleton=None, code_excerpt=None)
            shallow.children = _prune(node.children, target, path_ids,
                                      source_lines)
            pruned.append(shallow)
        else:
            pruned.append(replace(node, children=[], code_skeleton=None,
                                  code_excerpt=None))
    return pruned
