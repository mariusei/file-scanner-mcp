# Størrelsesgate for flere språk enn markdown (målt 2026-06-11 — FALSIFISERT)

Hypotese (BACKLOG M1 punkt 5): markdowns tree-sitter-gate ved 1 MB
(`MarkdownLanguage._TREE_SITTER_BYTE_LIMIT`, regex-fallback over) burde
løftes til flere språk.

## Måling 1: parse+extract vs regex-fallback på ~2 MB syntetiske filer

Syntetiske filer: `tests/<lang>/samples/basic.*` repetert til ~2 MB.
Målt per språk: tree-sitter-stien (`parser.parse` + `_extract_structure`)
mot `_fallback_extract` på samme bytes.

| ext | tree-sitter | fallback | ratio |
|---|---|---|---|
| .py | 283 939 ms | 1 968 ms | 144x |
| .java | 375 ms | 2 845 ms | 0,1x |
| .ts | 411 ms | 1 566 ms | 0,3x |
| .swift | 538 ms | 2 114 ms | 0,3x |
| .md | 300 ms | 106 ms | 2,8x |
| .sql | 291 ms | 4 211 ms | 0,1x |

**For java/ts/swift/sql er tree-sitter RASKERE enn regex-fallbacken** —
en gate ville gitt både tregere og strukturelt dårligere output
(flat fallback). Markdown-gaten er bekreftet (2,8x; i tråd med den
opprinnelige begrunnelsen i markdown.py). Python-tallet var ikke et
gate-argument men en bug:

## Måling 2: Python-patologien var kvadratisk `_get_ancestors`

cProfile på 250 kB: 57,7 mill. kall til `find_path` for 1 760 funksjoner —
`BaseLanguage._get_ancestors` gjorde full DFS fra roten per funksjonsnode
(O(n) per kall → O(n²) totalt; målt 4x tid per dobling av filstørrelse).

Omskrevet til `parent`-kjede-vandring (O(dybde) per kall):

| bytes | før | etter |
|---|---|---|
| 125 k | 1 139 ms | 21 ms |
| 250 k | 4 449 ms | 59 ms |
| 500 k | 17 733 ms | 80 ms |
| 2 M | ~284 000 ms | 431 ms |

## Konklusjon

- **Ingen generell størrelsesgate.** Behovet fantes bare for Python, og
  der var årsaken en kvadratisk algoritme — nå fikset i
  `BaseLanguage._get_ancestors`.
- Markdown beholder sin gate (egen måling, generert innhold dominerer
  over 1 MB).
- Falsifisert idé som ikke skal gjenopptas ukritisk: byte-gate i
  basens `scan()`-pipeline.

Reproduksjon: kjør målingene i dette dokumentet med snutten under.

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
