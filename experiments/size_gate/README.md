# Size gate for more languages than markdown (measured 2026-06-11 — FALSIFIED)

Hypothesis (BACKLOG M1 item 5): markdown's tree-sitter gate at 1 MB
(`MarkdownLanguage._TREE_SITTER_BYTE_LIMIT`, regex fallback above) should be
lifted to more languages.

## Measurement 1: parse+extract vs regex fallback on ~2 MB synthetic files

Synthetic files: `tests/<lang>/samples/basic.*` repeated to ~2 MB.
Measured per language: the tree-sitter path (`parser.parse` + `_extract_structure`)
against `_fallback_extract` on the same bytes.

| ext | tree-sitter | fallback | ratio |
|---|---|---|---|
| .py | 283 939 ms | 1 968 ms | 144x |
| .java | 375 ms | 2 845 ms | 0.1x |
| .ts | 411 ms | 1 566 ms | 0.3x |
| .swift | 538 ms | 2 114 ms | 0.3x |
| .md | 300 ms | 106 ms | 2.8x |
| .sql | 291 ms | 4 211 ms | 0.1x |

**For java/ts/swift/sql, tree-sitter is FASTER than the regex fallback** —
a gate would have given both slower and structurally worse output
(flat fallback). The markdown gate is confirmed (2.8x; consistent with the
original rationale in markdown.py). The Python number was not a
gate argument but a bug:

## Measurement 2: the Python pathology was a quadratic `_get_ancestors`

cProfile on 250 kB: 57.7 million calls to `find_path` for 1 760 functions —
`BaseLanguage._get_ancestors` did a full DFS from the root per function node
(O(n) per call → O(n²) total; measured 4x time per doubling of file size).

Rewritten to `parent`-chain walking (O(depth) per call):

| bytes | before | after |
|---|---|---|
| 125 k | 1 139 ms | 21 ms |
| 250 k | 4 449 ms | 59 ms |
| 500 k | 17 733 ms | 80 ms |
| 2 M | ~284 000 ms | 431 ms |

## Conclusion

- **No general size gate.** The need existed only for Python, and
  there the cause was a quadratic algorithm — now fixed in
  `BaseLanguage._get_ancestors`.
- Markdown keeps its gate (separate measurement, generated content dominates
  above 1 MB).
- Falsified idea that should not be revived uncritically: a byte gate in
  the base's `scan()` pipeline.

Reproduction: run the measurements in this document with the snippet below.

```python
import time
from pathlib import Path
from scantool.languages import get_language

base = Path("tests/python/samples/basic.py").read_bytes()
lang = get_language(".py")
for target in (125_000, 250_000, 500_000, 2_000_000):
    big = base * (target // len(base) + 1)
    t0 = time.perf_counter()
    res = lang._extract_structure(lang.parser.parse(big).root_node, big)
    print(f"{len(big)} bytes: {(time.perf_counter()-t0)*1000:.0f}ms, {len(res)} noder")
```
