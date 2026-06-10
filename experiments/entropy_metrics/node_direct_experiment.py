"""
EKSPERIMENT: Node-direkte saliency vs partisjonsbasert pipeline

HYPOTESE:
  Å score strukturnodene direkte (samme metrikker: shannon + betinget
  kompresjon + centrality på nodens byte-range) gir bedre utvalg enn
  partisjonering + coverage-mapping, fordi tapspunktet (≥50 %-terskelen
  mellom to urelaterte segmenteringer) forsvinner.

FALSIFISERBART:
  - Hvis scanner.py fortsatt velger trivielle gettere → arkitekturen var
    ikke problemet
  - Hvis lange kjernefunksjoner IKKE kommer inn → hel-node-scoring utvanner
    saliente kjerner (paradoks-utfall)
  - Likt utvalg → null-resultat (da er gevinsten kun enklere kode)

DESIGN:
  Kandidat-noder = løvnoder i strukturtreet (noder uten egne kandidat-barn),
  utenom skip-typer. Score per node på nodens bytes. Topp 20 % velges.
  Sammenlignes mot dagens utvalg (selection_after.json).
"""

import json
import re
import sys
import time
import zlib
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scantool.scanner import FileScanner  # noqa: E402
from scantool.entropy.core import _shannon_entropy  # noqa: E402

SKIP_TYPES = {"file-info", "imports", "section", "heading", "heading-1",
              "heading-2", "heading-3", "heading-4", "heading-5", "heading-6",
              "paragraph", "error", "parse-error"}

EMPTY_OVERHEAD = len(zlib.compress(b"", 6))
WINDOW = 16384


def candidate_nodes(structures):
    """Leaf-preference: a node is a candidate only if no descendant is."""
    def walk(nodes):
        found = []
        for n in nodes:
            from_children = walk(n.children) if n.children else []
            if from_children:
                found.extend(from_children)
            elif n.type not in SKIP_TYPES and n.name and n.end_line > n.start_line:
                found.append(n)
        return found
    return walk(structures)


def node_bytes(data: bytes, line_starts: list[int], node) -> tuple[bytes, int, int]:
    start = line_starts[node.start_line - 1] if node.start_line <= len(line_starts) else 0
    end = line_starts[node.end_line] if node.end_line < len(line_starts) else len(data)
    return data[start:end], start, end


def conditional(data: bytes, start: int, end: int) -> float:
    p = data[start:end]
    if not p:
        return 0.0
    ctx = data[max(0, start - WINDOW):start] + data[end:end + WINDOW]
    co = zlib.compressobj(level=6, zdict=ctx) if ctx else zlib.compressobj(level=6)
    return max(0, len(co.compress(p) + co.flush()) - EMPTY_OVERHEAD) / len(p)


def normalize(scores):
    arr = np.array(scores, dtype=float)
    if arr.max() > arr.min():
        return (arr - arr.min()) / (arr.max() - arr.min())
    return np.zeros_like(arr)


def select_node_direct(data: bytes, structures, top_percent=0.20):
    nodes = candidate_nodes(structures)
    if not nodes:
        return []

    line_starts = [0]
    for i, byte in enumerate(data):
        if byte == ord(b"\n"):
            line_starts.append(i + 1)

    text = data.decode("utf-8", errors="replace")
    call_counts = {}
    for m in re.finditer(r"\b(\w+)\s*\(", text):
        call_counts[m.group(1)] = call_counts.get(m.group(1), 0) + 1

    shannon, cond, centr = [], [], []
    for n in nodes:
        p, start, end = node_bytes(data, line_starts, n)
        shannon.append(_shannon_entropy(p))
        cond.append(conditional(data, start, end))
        centr.append(float(call_counts.get(n.name, 0)))

    saliency = (0.30 * normalize(shannon) + 0.50 * normalize(cond)
                + 0.20 * normalize(centr))
    order = np.argsort(saliency)[::-1]
    count = max(1, int(len(nodes) * top_percent))
    return [(nodes[i], float(saliency[i])) for i in order[:count]]


def main():
    after = json.loads((Path(__file__).parent / "selection_after.json").read_text())
    scanner = FileScanner()

    print("=" * 78)
    print("UTVALG: dagens partisjonsbaserte (etter metrikkbytte) vs node-direkte")
    print("=" * 78)
    t_total = 0.0
    for rel, current in after.items():
        path = PROJECT_ROOT / rel
        data = path.read_bytes()
        structures = scanner.scan_file(str(path))

        t0 = time.perf_counter()
        selected = select_node_direct(data, structures)
        t_total += time.perf_counter() - t0

        cur_names = [n["name"] for n in current]
        new_names = [n.name for n, _ in selected]
        n_cand = len(candidate_nodes(structures))
        print(f"\n{rel}  (kandidater: {n_cand})")
        print(f"  dagens ({len(cur_names)}): {', '.join(cur_names) or '(ingen)'}")
        print(f"  node-direkte ({len(new_names)}): {', '.join(new_names) or '(ingen)'}")

    print(f"\nTid node-direkte scoring, alle filer: {t_total * 1000:.1f}ms")


if __name__ == "__main__":
    main()
