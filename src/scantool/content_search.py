"""
FIL: content_search.py

PROBLEM:
  Spisset utforskning ender i grep: treffet (fil:linje) blir anker, og all
  strukturell forståelse — hvilken funksjon treffet bor i, hvor den sitter
  i arkitekturen — forkastes i øyeblikket den trengs mest.

LØSNING:
  Innholdssøk med grep-paritet på plassering (linjenumre beholdes), men
  hvert treff innfelles i sin strukturelle kontekst: nodekjeden det bor i
  (`CodeMap > analyze @656-727`) med signatur. Linjebasert mapping mot
  strukturtreet — språkagnostisk: et treff i markdown returnerer
  seksjonen, i SQL tabellen, i kode funksjonen.

SCOPE:
  ✓ Regex-søk i råinnhold, gruppert per containende node
  ✗ Ikke semantisk/embedding-søk
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Node types that never anchor a hit (a hit in an import still belongs
# to module level, not to the imports node)
_NON_ANCHOR_TYPES = {"file-info", "imports", "error", "parse-error"}

_MAX_HITS_PER_NODE = 4
_MAX_NODES = 40


@dataclass
class NodeHits:
    """All hits inside one structural node (or module level)."""

    file: str
    chain: str                       # e.g. "CodeMap > analyze"
    node_type: Optional[str]         # containing node's type, None at module level
    node_name: Optional[str]
    signature: Optional[str]
    start_line: int
    end_line: int
    hits: list[tuple[int, str]]      # (line number, line text)


def search_content(
    results: dict,
    pattern: str,
    ignore_case: bool = True,
) -> list[NodeHits]:
    """Find pattern hits across scanned files, grouped by containing node.

    Args:
        results: scan_directory output (file path -> StructureNode list)
        pattern: Regex searched in raw file content (any file type)
        ignore_case: Case-insensitive by default — concept searches rarely
            know the casing

    Returns:
        NodeHits per containing node, in file/line order
    """
    regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    found: list[NodeHits] = []

    for file_path in sorted(results):
        structures = results[file_path]
        try:
            lines = Path(file_path).read_text(errors="replace").split("\n")
        except OSError:
            continue

        by_node: dict[int, NodeHits] = {}  # id(node)/0 -> hits
        for line_no, line in enumerate(lines, start=1):
            if not regex.search(line):
                continue
            node, chain = _containing_node(structures, line_no)
            key = id(node) if node is not None else 0
            if key not in by_node:
                if node is not None:
                    by_node[key] = NodeHits(
                        file=file_path, chain=chain, node_type=node.type,
                        node_name=node.name, signature=node.signature,
                        start_line=node.start_line, end_line=node.end_line, hits=[],
                    )
                else:
                    by_node[key] = NodeHits(
                        file=file_path, chain="(module level)", node_type=None,
                        node_name=None, signature=None,
                        start_line=line_no, end_line=line_no, hits=[],
                    )
            by_node[key].hits.append((line_no, line.rstrip()))

        found.extend(by_node.values())

    # Relevance ranking: implementation before tests, then densest files
    # first, densest structures within — output caps then keep the RIGHT
    # structures instead of the alphabetically first (measured on
    # SWE-bench: broad queries in large repos truncated away the answer;
    # test directories dominated pure density ranking)
    file_totals: dict[str, int] = {}
    for node_hits in found:
        file_totals[node_hits.file] = file_totals.get(node_hits.file, 0) + len(node_hits.hits)
    found.sort(key=lambda n: (_is_test_path(n.file), -file_totals[n.file],
                              n.file, -len(n.hits), n.start_line))

    return found


def _is_test_path(file_path: str) -> bool:
    parts = Path(file_path).parts
    name = Path(file_path).name
    return (any(p in ("test", "tests", "testing") for p in parts)
            or name.startswith("test_") or name.endswith("_test.py"))


# ── spor: ett strukturelt hopp fra treff til definisjon ────────────────────

_CALL_IN_HIT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{4,})\s*\(")
_LEAD_MAX = 5
_LEAD_MAX_DEFINITIONS = 2  # navn definert i flere filer er for tvetydige


def find_leads(found: list[NodeHits], results: dict) -> list[tuple[str, str, int]]:
    """Identifiers called in hit lines but DEFINED in another scanned file —
    the structural hop a grep anchor hides. Measured rationale: concept
    searches often land in the caller while the answer lives one call away
    (SWE-bench pytest-7373).

    Returns (name, defining file, line), most-called first, capped.
    """
    definitions: dict[str, list[tuple[str, int]]] = {}
    for file_path, structures in results.items():
        def walk(nodes):
            for node in nodes or []:
                if node.name and node.type != "file-info":
                    definitions.setdefault(node.name, []).append(
                        (file_path, node.start_line))
                walk(node.children)
        walk(structures)

    # kall hentes fra hele den containende noden, ikke bare trefflinjene —
    # hoppet til nabofilen står ofte på linjen ved siden av treffet.
    # Kun fra de øverste viste IMPLEMENTASJONS-strukturene: spor skal følge
    # av det agenten ser, og testfilers hjelperkall er støy
    sources = [n for n in found if not _is_test_path(n.file)][:10]
    call_counts: dict[str, int] = {}
    hit_files: dict[str, set[str]] = {}
    block_cache: dict[str, list[str]] = {}
    for node_hits in sources:
        if node_hits.file not in block_cache:
            try:
                block_cache[node_hits.file] = Path(node_hits.file).read_text(
                    errors="replace").split("\n")
            except OSError:
                block_cache[node_hits.file] = []
        lines = block_cache[node_hits.file]
        block = "\n".join(lines[node_hits.start_line - 1:node_hits.end_line])
        for name in _CALL_IN_HIT.findall(block):
            call_counts[name] = call_counts.get(name, 0) + 1
            hit_files.setdefault(name, set()).add(node_hits.file)

    leads = []
    for name, count in sorted(call_counts.items(), key=lambda kv: -kv[1]):
        defined_in = definitions.get(name, [])
        if not 1 <= len(defined_in) <= _LEAD_MAX_DEFINITIONS:
            continue
        # kun hopp UT av treff-filene — definisjon i samme fil er allerede synlig
        external = [(f, line) for f, line in defined_in if f not in hit_files[name]]
        if not external:
            continue
        leads.append((name, external[0][0], external[0][1]))
        if len(leads) >= _LEAD_MAX:
            break
    return leads


def _containing_node(structures, line_no: int):
    """Deepest named node whose range contains the line, with its chain."""
    best = None
    best_chain = ""

    def walk(nodes, path):
        nonlocal best, best_chain
        for node in nodes or []:
            if (node.type not in _NON_ANCHOR_TYPES and node.name
                    and node.start_line <= line_no <= node.end_line):
                chain = path + [node.name]
                best = node
                best_chain = " > ".join(chain)
                walk(node.children, chain)
            else:
                walk(node.children, path)

    walk(structures, [])
    return best, best_chain


def format_hits(found: list[NodeHits], pattern: str,
                leads: Optional[list[tuple[str, str, int]]] = None) -> str:
    """Compact structural rendering: node chain + line-numbered hits,
    plus one-hop leads to definitions in other files."""
    if not found:
        return f"No content matches for /{pattern}/"

    total_hits = sum(len(n.hits) for n in found)
    shown = found[:_MAX_NODES]
    lines = [f"{total_hits} hits in {len(found)} structures for /{pattern}/"]

    current_file = None
    for node_hits in shown:
        if node_hits.file != current_file:
            current_file = node_hits.file
            lines.append(f"\n{current_file}")
        sig = f" {node_hits.signature}" if node_hits.signature else ""
        header = f"- {node_hits.chain}{sig} @{node_hits.start_line}-{node_hits.end_line}"
        if len(node_hits.hits) > 1:
            header += f"  ({len(node_hits.hits)} hits)"
        lines.append(header)
        for line_no, text in node_hits.hits[:_MAX_HITS_PER_NODE]:
            lines.append(f"   {line_no} | {text.strip()[:120]}")
        if len(node_hits.hits) > _MAX_HITS_PER_NODE:
            lines.append(f"   +{len(node_hits.hits) - _MAX_HITS_PER_NODE} more in this structure")

    if len(found) > _MAX_NODES:
        lines.append(f"\n+{len(found) - _MAX_NODES} more structures — narrow the pattern")
    if leads:
        # full sti — agenten skal kunne følge sporet med ett scan_file-kall
        lines.append("\nleads (called in hits, defined elsewhere): " + ", ".join(
            f"{name} → {file}@{line}" for name, file, line in leads))
    return "\n".join(lines)
