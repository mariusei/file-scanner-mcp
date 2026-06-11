"""
EXPERIMENT: Skeleton depth as a function of saliency

PROBLEM:
  Node-direct selection shows whole nodes: a long function is shown in full
  (full skeleton) or not at all. Question: does graded depth
  (more salient = deeper skeleton) yield more visible method facts per token,
  by spending the saved budget on showing MORE nodes more shallowly?

FALSIFIABLE PREDICTIONS (before running):
  - Null outcome: if ~80 % of the skeleton lines lie at depth <= 1, depth
    cutting saves almost nothing -> the idea is rejected (measured FIRST)
  - Paradox: depth 1 loses the conditions/calls that carry the method ->
    fact coverage collapses for shallow tiers
  - Expected: graded (S2) > current (S1) on facts per token at
    comparable total token cost

STRATEGIES (shares of saliency-ranked candidates):
  S1 current:      top 20 % full skeleton
  S2 graded:       0-20 % full, 20-35 % depth 2, 35-50 % depth 1
  S3 broad-full:   top 35 % full skeleton
  S4 broad-shallow: top 50 % depth 1

UNITS OF MEASUREMENT:
  tokens = tiktoken cl100k on the skeleton lines (headers are equal for all)
  facts  = unique called function names visible in shown text, against all calls
           in every candidate node in the file

Python files only: the AST skeleton uses 1 space per depth level, so
depth cutting can be done on line indentation. (The generic skeleton keeps original
indentation and must be normalized before the same trick.)
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scantool.entropy import select_salient_nodes  # noqa: E402
from scantool.languages import get_language  # noqa: E402

FILES = [
    "src/scantool/scanner.py",
    "src/scantool/preview.py",
    "src/scantool/code_map.py",
    "src/scantool/formatter.py",
    "src/scantool/directory_formatter.py",
    "src/scantool/entropy/core.py",
    "src/scantool/languages/python.py",
    "src/scantool/languages/base.py",
    "src/scantool/server.py",
    "src/scantool/call_graph.py",
]

CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
KEYWORDS = {"if", "elif", "while", "for", "return", "with", "assert", "raise",
            "def", "class", "except", "in", "not", "and", "or", "lambda", "print"}

# (name, [(share-from, share-to, depth)]) — depth None = full skeleton
STRATEGIES = [
    ("S1 current (20% full)", [(0.00, 0.20, None)]),
    ("S2 graded (50%)", [(0.00, 0.20, None), (0.20, 0.35, 2), (0.35, 0.50, 1)]),
    ("S3 broad-full (35%)", [(0.00, 0.35, None)]),
    ("S4 broad-shallow (50% d1)", [(0.00, 0.50, 1)]),
]


def calls_in(text: str) -> set[str]:
    return {m for m in CALL_RE.findall(text) if m not in KEYWORDS}


def depth_limit(skeleton: list[str], max_depth: int) -> list[str]:
    """Cut skeleton lines deeper than max_depth (1 space = 1 level)."""
    out = []
    for line in skeleton:
        indent = len(line) - len(line.lstrip())
        if indent < max_depth:
            out.append(line)
        else:
            marker = " " * max_depth + "…"
            if not out or out[-1] != marker:
                out.append(marker)
    return out


def main():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        count = lambda t: len(enc.encode(t))
        note = "tiktoken cl100k_base"
    except ImportError:
        count = lambda t: max(1, len(t) // 4)
        note = "fallback len//4"

    # Per file: ranked candidates with (skeleton, facts in the node's source)
    ranked_per_file = []
    depth_line_counts: dict[int, int] = {}
    lang = get_language(".py")

    for rel in FILES:
        path = PROJECT_ROOT / rel
        data = path.read_bytes()
        source_lines = data.decode("utf-8", errors="replace").split("\n")
        structures = lang.scan(data)
        ranked = select_salient_nodes(data, structures, top_percent=1.0)

        nodes = []
        for node, score in ranked:
            excerpt = source_lines[node.start_line - 1:node.end_line]
            skeleton = lang.condense_excerpt(excerpt)
            if skeleton is None:
                skeleton = [line.strip() for line in excerpt]  # verbatim fallback
            for line in skeleton:
                d = len(line) - len(line.lstrip())
                depth_line_counts[d] = depth_line_counts.get(d, 0) + 1
            nodes.append({
                "name": node.name,
                "skeleton": skeleton,
                "facts": calls_in("\n".join(excerpt)),
            })
        ranked_per_file.append((rel, nodes))

    print("=" * 78)
    print(f"OBSERVATIONS (tokenizer: {note})")
    print("=" * 78)

    total_lines = sum(depth_line_counts.values())
    print("\nPRE-CHECK (the null hypothesis): skeleton lines per depth level")
    cum = 0
    for d in sorted(depth_line_counts):
        cum += depth_line_counts[d]
        print(f"  depth {d}: {depth_line_counts[d]:5d} lines "
              f"({100 * depth_line_counts[d] / total_lines:.0f}%, "
              f"cumulative {100 * cum / total_lines:.0f}%)")

    print("\nSTRATEGY COMPARISON (sum over all files):")
    print(f"  {'strategy':26s} {'nodes':>6s} {'tokens':>8s} "
          f"{'fact coverage':>14s} {'facts/1k tok':>13s}")

    for name, tiers in STRATEGIES:
        tot_tokens = 0
        tot_nodes = 0
        visible_facts = 0
        all_facts = 0
        for rel, nodes in ranked_per_file:
            n = len(nodes)
            file_all = set().union(*(nd["facts"] for nd in nodes)) if nodes else set()
            file_visible = set()
            for lo, hi, depth in tiers:
                for nd in nodes[int(lo * n):max(int(lo * n) + 1, int(hi * n))]:
                    skel = nd["skeleton"] if depth is None else depth_limit(nd["skeleton"], depth)
                    text = "\n".join(skel)
                    tot_tokens += count(text)
                    tot_nodes += 1
                    file_visible |= calls_in(text) & file_all
            visible_facts += len(file_visible)
            all_facts += len(file_all)
        coverage = 100 * visible_facts / all_facts if all_facts else 0
        per_1k = 1000 * visible_facts / tot_tokens if tot_tokens else 0
        print(f"  {name:26s} {tot_nodes:6d} {tot_tokens:8d} "
              f"{visible_facts:5d}/{all_facts} ({coverage:4.1f}%) {per_1k:13.1f}")

    print("\nFORK: interpretation is done after observation — see the analysis outside the script.")


if __name__ == "__main__":
    main()
