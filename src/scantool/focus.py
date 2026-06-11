"""
FIL: focus.py

PROBLEM:
  Lesesteget etter scan: agenter vil lese «denne funksjonen», ikke gjette
  linje-ranges med Read/sed. Linjenumre er flyktige; nodenavn er stabile.

LØSNING:
  Slå opp en node via navn eller kvalifisert sti (ClassA.method, heading-
  tekst), render fil-skjelettet på dybde 1 med stien til noden utvidet
  (parent-kontekst), og selve noden verbatim med linjenumre. Gjenbruker
  TreeFormatter: verbatim-visningen ER formatterens code_excerpt-mekanisme.

SCOPE:
  ✓ Eksakt navn, kvalifisert sti, substring-fallback (markdown-headings)
  ✓ Tvetydighet → feilmelding med kvalifiserte kandidater
  ✗ Ingen delta/git-integrasjon — en fokusert lesing er ikke et scan
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
            if all(seg in it for seg in parents):  # subsekvens, i rekkefølge
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
        return (f"focus '{focus}' er tvetydig ({len(matches)} treff) — "
                f"bruk kvalifisert sti:\n{listed}")
    available = ", ".join(n.name for n, a in _walk(structures) if not a)
    return (f"focus '{focus}' matcher ingen node. "
            f"Toppnivå-noder: {available}")


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
