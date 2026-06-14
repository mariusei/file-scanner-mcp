# The entropy machinery: metric and architecture experiments

> **History:** `compression_experiment.py` measured against the partition-based
> pipeline and cannot be run against today's code (the partition functions have
> been removed) — check out a commit prior to the node-direct restructuring to reproduce.

## Node-direct architecture (integrated 2026-06-10)

`node_direct_experiment.py` tested scoring the structure nodes directly instead
of indentation partitions + ≥50 % coverage mapping. Two iterations:

1. **Per-byte scoring**: core logic came in (`preview_directory`), but the
   small-node bias persisted — trivial getters (`return 10`) scored high because
   per-byte metrics reward density, not substance.
2. **Log-absolute new information** (`log1p(compressed size given
   context)`): "who contributes the most method to the file". scanner.py went from
   trivial getters to `scan_file`; code_map to `analyze`+`format_tree`.

**Falsification check** (is log-abs just "pick the largest node"?): 56 % overlap
with pure size ranking, rank correlation 0.39–0.88 — size contributes
(longer unique code = more information), but the metric genuinely discriminates
(scanner.py does not pick the largest node; Rust 0/4 overlap).

The architectural gain: partitioning, the coverage threshold, the `min_size` gap,
line mapping and all of `callgraph.py` (entities = the nodes themselves) disappeared.
The tab fix became redundant — indentation is no longer used. The selections per
generation are in `selection_before.json` (original metric),
`selection_after.json` (conditional compression, partition-based) and
`selection_node_direct.json` (today's).

## Cross-file dedup of skeletons (measured 2026-06-10 — NULL FINDING, not integrated)

`dedup_experiment.py` measured the potential of showing repeated skeleton patterns
once + references, at two levels: A = exact duplicates (lossless),
B = shape duplicates with normalized identifiers (lossy — hides the
members' call names, i.e. the factual content itself).

| Repo | Level A (lossless) | Level B (lossy) |
|---|---|---|
| scantool/src (artificially favorable: 20 similar language files) | 3.0 % | 5.1 % |
| isowords (real iOS/SwiftUI, 388 files, 1609 nodes) | **0.2 %** | 3.4 % |

Even in the most dedup-friendly repo imaginable, the lossless saving is 3 %;
on real iOS code 0.2 %. The shape patterns in isowords are moreover degenerate
(multi-line init signatures that fold to `…` + `) {`), not meaningful
patterns. The explanation is that the pipeline has already squeezed out the redundancy:
the skeletons fold boilerplate *within* nodes, conditional compression
deprioritizes duplicates in the *selection*, and the depth-2 outlines are so small
(20–30 tokens) that the reference cost eats the gain.

**Conclusion: not worth the complexity.** Measured hierarchy of gains:
notation frequency (ASCII switch: −26 %) ≫ architecture (node-direct/S6) ≫
cross-file dedup (≤3 %).

Side finding: the generic skeleton on Swift with multi-line signatures produces
noise lines (`…` + `) {`) — an improvement candidate in `_skeleton_lines`.

## Skeleton depth by saliency (measured and integrated 2026-06-10 as S6)

> **Integrated:** the scanner annotation now gives all candidate nodes a
> depth-2 skeleton (`FileScanner.BROAD_TIER_DEPTH`); the top 20 % get full
> depth + verbatim excerpt. `limit_skeleton_depth()` in `languages/base.py`
> maps indentation widths to levels per rank (works for 1-space AST,
> tabs and 2/4-space). The compact strategy (declarative content) is never
> depth-cut; skeletons that consist only of `…` after the cut are dropped.
> Measured total scan_file output on 10 src files: 20.1k → 31.5k tokens
> (+56 %, 39 % of full source) for 56.4 % vs 32.8 % fact coverage.

`skeleton_depth_experiment.py` tested whether graded depth (more salient = deeper
skeleton) yields more visible method facts (unique call names) per token.
10 Python files in src/, depth cut at the AST skeleton's indentation level.

Pre-check (the null hypothesis did not survive, but nuanced): 60 % of the
skeleton lines lie at depth ≤ 1, 81 % at ≤ 2 — depth cutting has moderate,
not large, savings mass.

| Strategy | Nodes | Tokens | Fact coverage | Facts/1k tok |
|---|---|---|---|---|
| S1 current (top 20 % full) | 27 | 9 385 | 32.8 % | 23.3 |
| S2 graded (20 full/15 d2/15 d1) | 73 | 11 692 | 43.0 % | 24.5 |
| **S7 all nodes depth 2** | 146 | 10 708 | **47.4 %** | **29.5** |
| S6 top 20 % full + all d2 | 146 | 15 712 | 56.4 % | 23.9 |
| S8 all full (reference) | 146 | 18 548 | 63.4 % | 22.8 |

**Main finding (unexpected):** the hypothesis "saliency-graded depth" is only weakly
supported (S2: +5 % efficiency). The real finding is that *shallow skeletons
are fact-dense*: depth 2 for ALL nodes (S7) dominates both the current approach and
the graded one — +14 % tokens versus the current gives +14.6 pp coverage and the highest
efficiency. The value of the saliency ranking for *depth allocation* is small;
the value lies in choosing who gets *full* depth.

**Recommendation candidate:** S6 = universal depth-2 skeleton + full depth for the
top 20 % (saliency keeps the role "who deserves the whole method" — the most
salient nodes by definition have deep unique logic, which is what the depth cut
removes). The price is +67 % skeleton tokens versus the current; S7 is the
efficiency choice if the budget is sacred.

**Caveat:** the fact metric counts unique call names, not readability;
the depth cut leaves `if x:` followed by `…` — an outline, not a method. Applies to
Python AST skeletons; the generic skeleton must normalize indentation first.

---

# Compression metric experiment: conditional compression vs the current ratio

## Background

Measured 2026-06-10: the current `_compression_ratio` correlates r=−0.80 with
log(partition size) — zlib overhead dominates small partitions, so
the metric measures size, not complexity (20–25 % weight in saliency).

## Candidates

- **A (current):** `len(zlib(p)) / len(p)`
- **B (overhead-corrected):** subtracts the empty-compression baseline
- **C (conditional):** `len(zlib(p, zdict=rest of the file)) / len(p)` — measures
  how much *new* information the partition contributes given the context

## Results (run `compression_experiment.py`)

**Size confounding** — corr(log size, metric), 4 files:

| | A current | B corrected | C conditional |
|---|---|---|---|
| preview.py | −0.80 | −0.61 | −0.15 |
| languages/python.py | −0.69 | −0.44 | −0.23 |
| code_map.py | −0.66 | −0.38 | −0.16 |
| go/edge_cases.go | −0.72 | −0.36 | −0.52 |

**Discrimination (known ground truth):** a unique complex function among 6
near-identical boilerplate copies:
- A and B rank the unique function **#7/7 — last**. The current metric is
  not just noisy; it is *inverted* on this task (boilerplate
  compresses slightly worse in isolation than varied logic).
- C ranks it **#1/7** with a 3× margin (0.55 vs 0.18).

Repeated high-entropy blob vs unique logic: A/B put the blob copies on top
(0.94); C puts the logic first and the copies near zero (0.03) — conditional
compression captures uniqueness and complexity in a single metric.

**Cost** (languages/python.py, 320 partitions):

| | time/file | discrimination | confounding |
|---|---|---|---|
| A | 1.7 ms | #7/7 | −0.69 |
| C level 6 | 10.0 ms | #1/7 | −0.30 |
| C level 9 | 13.8 ms | #1/7 | −0.23 |
| `_structural_uniqueness` (current, O(n²)) | 10.8 ms | — | — |

## Conclusion — integrated 2026-06-10

C replaced **both** `_compression_ratio` and `_structural_uniqueness` in
`entropy/core.py` (`_conditional_compression`, zlib level 6, 16 KB context
per side). New weighting: 0.30 shannon + 0.50 conditional + 0.20 centrality
(0.35/0.65 without centrality). Net faster: 14.6 → 11.2 ms/file.

Effect on the excerpt selection: see `selection_compare.md` — duplicates and
boilerplate out (C++ copies, literal `__init__`), unique core logic in
(`_discover_files`, `condense_excerpt`, `validate_email`). Three null findings
where the selection was unchanged.

## Caveats

- Synthetic ground truth: two constructed tests, not human-judged ground truth
- The Go file retains −0.52 confounding for C — may be legitimate (larger
  functions genuinely contribute more unique information) or a small-file artifact
- The zdict window is 32 KB — for files > 32 KB the context only sees the nearest
  neighborhood
