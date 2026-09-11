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

import re
from dataclasses import replace

from .formatter import TreeFormatter
from .languages import StructureNode


def format_focus(
    file_path: str,
    structures: list[StructureNode],
    source_lines: list[str],
    focus: str,
    addressed: bool = False,
) -> str:
    """Render skeleton-with-context + verbatim body for the focused node.

    addressed=True opens with the node's structural address instead of the
    `focus:` line: `path::Qualified.name (a-b)`, the form `focus` accepts
    back as one argument (`@` is reserved for a ref, so the range stays in
    parentheses)."""
    matches = _resolve(structures, focus)
    if len(matches) != 1:
        return _resolution_error(structures, focus, matches)

    target, ancestors = matches[0]
    path_ids = {id(node) for node in (*ancestors, target)}
    pruned = _prune(structures, target, path_ids, source_lines)

    if addressed:
        name = address_name(structures, target, ancestors)
        header = f"{file_path}::{name} ({target.start_line}-{target.end_line})"
    else:
        qualified = ".".join(node.name for node in (*ancestors, target))
        header = f"focus: {qualified} @{target.start_line}-{target.end_line}"
    return header + "\n" + TreeFormatter().format(file_path, pruned)


# A heading that opens with a bracketed tag ([DEV-L17] Contracts …) is
# addressed by the tag; the study's documents used exactly this convention.
_ID_TAG = re.compile(r"^\[([A-Za-z][A-Za-z0-9]*-[A-Za-z0-9]+)\]")


def _is_heading(node: StructureNode) -> bool:
    return node.type.startswith("heading") or node.type == "section"


def address_name(structures: list[StructureNode], target: StructureNode, ancestors: tuple) -> str:
    """The name part of `path::name`: the dotted qualified name for code; for
    a heading its ID tag when it has one, else the heading text quoted — the
    leaf alone when that is unique in the file, the dotted path otherwise."""
    if not _is_heading(target):
        return ".".join(node.name for node in (*ancestors, target))
    tag = _ID_TAG.match(target.name)
    if tag:
        return tag.group(1)
    same_name = [n for n, _ in _walk(structures) if n.name == target.name]
    if len(same_name) == 1:
        return f'"{target.name}"'
    return '"' + ".".join(node.name for node in (*ancestors, target)) + '"'


def _walk(structures: list[StructureNode], ancestors: tuple = ()):
    for node in structures:
        if node.type == "file-info":
            continue
        yield node, ancestors
        yield from _walk(node.children, (*ancestors, node))


def _resolve(structures: list[StructureNode], focus: str) -> list[tuple[StructureNode, tuple]]:
    """Match tiers: exact name, qualified path, case-insensitive substring.
    A quoted name (a heading address) is matched without its quotes."""
    if len(focus) >= 2 and focus[0] == focus[-1] == '"':
        focus = focus[1:-1]
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


def _resolution_error(
    structures: list[StructureNode], focus: str, matches: list[tuple[StructureNode, tuple]]
) -> str:
    if matches:
        listed = "\n".join(
            f"  {'.'.join(node.name for node in (*anc, n))} @{n.start_line}"
            for n, anc in matches[:10]
        )
        return (
            f"focus '{focus}' is ambiguous ({len(matches)} matches) — "
            f"use a qualified path:\n{listed}"
        )
    available = ", ".join(n.name for n, a in _walk(structures) if not a)
    return f"focus '{focus}' matches no node. Top-level nodes: {available}"


def _prune(
    structures: list[StructureNode],
    target: StructureNode,
    path_ids: set[int],
    source_lines: list[str],
) -> list[StructureNode]:
    """Depth-1 copies; the ancestor path stays expanded, the target verbatim."""
    pruned = []
    for node in structures:
        if node.type == "file-info":
            pruned.append(node)
        elif id(node) == id(target):
            excerpt = source_lines[node.start_line - 1 : node.end_line]
            pruned.append(replace(node, children=[], code_skeleton=None, code_excerpt=excerpt))
        elif id(node) in path_ids:
            shallow = replace(node, code_skeleton=None, code_excerpt=None)
            shallow.children = _prune(node.children, target, path_ids, source_lines)
            pruned.append(shallow)
        else:
            pruned.append(replace(node, children=[], code_skeleton=None, code_excerpt=None))
    return pruned
