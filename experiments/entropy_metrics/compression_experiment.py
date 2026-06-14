"""
EXPERIMENT: Compression metric as a complexity proxy in saliency ranking

PROBLEM (measured 2026-06-10):
  The current _compression_ratio correlates r=-0.80 with log(partition size).
  zlib overhead dominates small partitions (ratio ~1.09) — the metric in
  practice measures size, not complexity, with 20-25 % weight in saliency.

CANDIDATES:
  A (current):   len(zlib(p)) / len(p)
  B (corrected): (len(zlib(p)) - len(zlib(b""))) / len(p)  — removes overhead
  C (conditional): len(zlib(p | zdict=rest of the file)) / len(p)
                 — measures NEW information given the context (complexity AND
                 uniqueness in one metric)

FALSIFIABLE PREDICTIONS (before running):
  - If |corr(log size, metric)| remains > 0.6 for B: overhead was not
    the main cause → the zlib-header hypothesis weakens
  - If C does not rank a unique function above near-identical copies:
    conditional compression does not capture uniqueness → reject C
  - Null outcome possible: A may discriminate fine despite the
    size correlation (correlation ≠ uselessness)
  - Paradox possible: C may be slower than the entire current analysis → impractical

MEASUREMENTS:
  1. Size confounding: corr(log size, metric) on real files
  2. Discrimination: synthetic file with known ground truth
     (a) unique logic + 6 near-identical boilerplate functions
     (b) repeated high-entropy blob vs unique low-level logic
  3. Cost: time per file
"""

import sys
import time
import zlib
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scantool.entropy.core import (  # noqa: E402
    _find_indentation_blocks,
    _partition_by_patterns,
)

EMPTY_OVERHEAD = len(zlib.compress(b"", 9))


def metric_a(p: bytes, before: bytes, after: bytes) -> float:
    return len(zlib.compress(p, 9)) / len(p)


def metric_b(p: bytes, before: bytes, after: bytes) -> float:
    return max(0, len(zlib.compress(p, 9)) - EMPTY_OVERHEAD) / len(p)


def metric_c(p: bytes, before: bytes, after: bytes) -> float:
    ctx = (before + after)[-32768:]
    co = zlib.compressobj(level=9, zdict=ctx) if ctx else zlib.compressobj(level=9)
    out = co.compress(p) + co.flush()
    return max(0, len(out) - EMPTY_OVERHEAD) / len(p)


CANDIDATES = [("A current", metric_a), ("B corrected", metric_b), ("C conditional", metric_c)]


def real_file_partitions(path: Path) -> list[tuple[bytes, bytes, bytes]]:
    data = path.read_bytes()
    parts = _partition_by_patterns(data, _find_indentation_blocks(data))
    return [
        (p["data"], data[: p["offset"]], data[p["offset"] + p["size"]:])
        for p in parts
    ]


def main():
    print("=" * 78)
    print("MEASUREMENT 1: Size confounding — corr(log size, metric)")
    print("=" * 78)
    files = ["src/scantool/preview.py", "src/scantool/languages/python.py",
             "src/scantool/code_map.py", "tests/go/samples/edge_cases.go"]
    print(f"{'file':44s}" + "".join(f"{name:>14s}" for name, _ in CANDIDATES))
    for f in files:
        triples = real_file_partitions(PROJECT_ROOT / f)
        sizes = np.log([len(p) for p, _, _ in triples])
        row = f"{f:44s}"
        for _, fn in CANDIDATES:
            vals = np.array([fn(p, b, a) for p, b, a in triples])
            r = np.corrcoef(sizes, vals)[0, 1] if len(triples) > 2 else float("nan")
            row += f"{r:14.3f}"
        print(row)

    print()
    print("=" * 78)
    print("MEASUREMENT 2a: Discrimination — unique logic among 6 boilerplate copies")
    print("=" * 78)
    unique = b"""def reconcile(ledger, txns, fx_rates):
    drift = sum(t.amount * fx_rates[t.ccy] for t in txns) - ledger.total
    buckets = {}
    for t in sorted(txns, key=lambda t: abs(t.amount), reverse=True):
        buckets.setdefault(t.ccy, []).append(t)
        if abs(drift) < 0.01:
            break
        drift -= t.amount * (fx_rates[t.ccy] - 1.0)
    return drift, buckets
"""
    boiler = [
        (b"def get_field_%d(self):\n"
         b"    if self._field_%d is None:\n"
         b"        self._field_%d = load_default(%d)\n"
         b"    return self._field_%d\n") % (i, i, i, i, i)
        for i in range(6)
    ]
    blocks = boiler[:3] + [unique] + boiler[3:]
    labels = ["boiler"] * 3 + ["UNIQUE"] + ["boiler"] * 3
    file_data = b"\n".join(blocks)

    for name, fn in CANDIDATES:
        scores = []
        offset = 0
        for block in blocks:
            before = file_data[:offset]
            after = file_data[offset + len(block):]
            scores.append(fn(block, before, after))
            offset += len(block) + 1
        order = np.argsort(scores)[::-1]  # highest first
        rank_of_unique = int(np.where(order == 3)[0][0]) + 1
        print(f"  {name:12s} unique logic ranked #{rank_of_unique}/7   "
              f"scores: " + " ".join(
                  f"{'*' if i == 3 else ''}{s:.3f}" for i, s in enumerate(scores)))

    print()
    print("=" * 78)
    print("MEASUREMENT 2b: Repeated high-entropy blob vs unique logic")
    print("=" * 78)
    rng_blob = bytes(np.random.RandomState(42).randint(33, 127, 300, dtype=np.uint8))
    blocks = [rng_blob, unique, rng_blob, rng_blob]
    labels = ["blob", "UNIQUE-logic", "blob-copy", "blob-copy"]
    file_data = b"\n".join(blocks)
    for name, fn in CANDIDATES:
        scores = []
        offset = 0
        for block in blocks:
            before = file_data[:offset]
            after = file_data[offset + len(block):]
            scores.append(fn(block, before, after))
            offset += len(block) + 1
        ranked = [labels[i] for i in np.argsort(scores)[::-1]]
        print(f"  {name:12s} ranking (highest first): {ranked}")
        print(f"  {'':12s} scores: " + " ".join(
            f"{l}={s:.3f}" for l, s in zip(labels, scores)))

    print()
    print("=" * 78)
    print("MEASUREMENT 3: Cost per file (all partitions)")
    print("=" * 78)
    for f in ["src/scantool/preview.py", "src/scantool/languages/python.py"]:
        triples = real_file_partitions(PROJECT_ROOT / f)
        row = f"  {f} ({len(triples)} partitions): "
        for name, fn in CANDIDATES:
            t0 = time.perf_counter()
            for _ in range(5):
                for p, b, a in triples:
                    fn(p, b, a)
            row += f"{name.split()[0]}={1000 * (time.perf_counter() - t0) / 5:.1f}ms  "
        print(row)


if __name__ == "__main__":
    main()
