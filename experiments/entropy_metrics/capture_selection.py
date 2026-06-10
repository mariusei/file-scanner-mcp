"""Fang excerpt-utvalget (hvilke noder entropi-rankingen velger) for et sett
representative filer. Kjøres før og etter metrikkbytte for sammenligning:

    uv run python -u experiments/entropy_metrics/capture_selection.py selection_before.json
    # ... bytt metrikk ...
    uv run python -u experiments/entropy_metrics/capture_selection.py selection_after.json
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scantool.scanner import FileScanner  # noqa: E402

FILES = [
    "src/scantool/scanner.py",
    "src/scantool/preview.py",
    "src/scantool/code_map.py",
    "src/scantool/formatter.py",
    "src/scantool/entropy/core.py",
    "src/scantool/languages/python.py",
    "src/scantool/languages/base.py",
    "tests/go/samples/edge_cases.go",
    "tests/go/samples/basic.go",
    "tests/rust/samples/edge_cases.rs",
    "tests/typescript/samples/basic.ts",
    "tests/c_cpp/samples/edge_cases.cpp",
    "tests/ruby/samples/basic.rb",
    "tests/swift/samples/basic.swift",
]


def collect(structures, out):
    for node in structures or []:
        if node.code_excerpt is not None:
            out.append({
                "name": node.name,
                "type": node.type,
                "lines": [node.start_line, node.end_line],
                "saliency": round(getattr(node, "saliency", None)
                                  or getattr(node, "saliency_coverage", None) or 0, 3),
            })
        collect(node.children, out)


def main():
    out_name = sys.argv[1] if len(sys.argv) > 1 else "selection.json"
    scanner = FileScanner()
    result = {}
    for rel in FILES:
        path = PROJECT_ROOT / rel
        if not path.exists():
            print(f"  (hopper over {rel} — finnes ikke)")
            continue
        nodes = []
        collect(scanner.scan_file(str(path)), nodes)
        result[rel] = nodes
        names = ", ".join(n["name"] for n in nodes) or "(ingen)"
        print(f"{rel}: {len(nodes)} excerpts → {names}")

    out_path = Path(__file__).parent / out_name
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nLagret: {out_path}")


if __name__ == "__main__":
    main()
