# Backlog toward v1.0.0

Status as of 2026-06-11. The frontier work has been delivered (condensation,
node-direct saliency, git signals, health, budget, delta, scan_diff,
content search with traces, modes, benchmark M2/M2c/M2b). This document
makes the remaining work actionable: what, why (evidence), acceptance criterion.

## The v1.0 gate (the definition)

v1.0.0 is set when: (1) the output contract is frozen with golden tests,
(2) the benchmark margin holds on repos we have not tuned against —
**reformulated after M2b**: the margin that must hold is ANSWER QUALITY
(fact coverage in real agent episodes, measured 88 % vs 73 %), with
token parity or better under budget pressure. Evidence: harness 6/6 vs 5/6
(experiments/benchmark/README.md), M2b (experiments/benchmark/M2B.md).

## M1 queue (maintenance, prioritized)

1. ~~**Consumption steering for agents**~~ **DELIVERED 2026-06-11**:
   cost-transparent tool descriptions in server.py; acceptance criterion
   met — token gap 2.8× → 1.2× with quality 86 % vs grep 67 %
   (M2B.md addendum). Remaining nuance: open architecture questions lose
   slightly from economizing (sg-T5) — consider task-conditioned steering later.

2. ~~**Dogfooding refactor**~~ **DELIVERED 2026-06-11**: 36 method copies
   removed across 16 language plugins (−548/+56 lines); BaseLanguage got
   defaults with hooks (_extract_definitions_regex,
   _extract_calls_tree_sitter/_regex, _handle_import, _get_ancestors).
   Acceptance criterion met: CODE HEALTH on src/scantool shows zero
   duplicate groups — including _extract_keyframes (css/scss) which was
   hidden behind the display cap of 5 groups; 877/877 tests green.
   Genuine overrides preserved: swift (_structures_to_definitions_swift),
   java (is_cross_file marking), rust ("use statements"),
   sql/scss/generic/config (own logic).

3. ~~**Golden output tests / format contract**~~ **DELIVERED 2026-06-11**:
   19 snapshots (18 languages via scan_file + a dedicated fixture directory
   for scan_directory) in tests/golden/, enforced by tests/test_golden.py;
   updates only via `UPDATE_GOLDEN=1`. Frozen layer:
   scanner+formatter with defaults — file-info omitted (mtime follows
   the checkout), git signals/delta live in the server layer and are out of
   scope. Determinism measured: 19/19 byte-identical on repeated runs, 19/19
   green in a copy without .git with fresh mtimes. The contract is documented
   in README ("Output Contract"). **Sequencing decision vs item 4**: frozen
   now; item 4 goes through the contract's own mechanism (deliberate change →
   deliberate snapshot update).

4. ~~**Docstring tiering + parameter consistency**~~ **DELIVERED 2026-06-11**:
   all 7 tools in server.py follow the same tier template in Args
   (Common → Cost & slicing → Semantics & display; empty tiers are omitted).
   mode added to scan_directory (server + FileScanner.scan_directory,
   default "balanced") with a regression test for propagation; scan_file's
   undocumented mode param got an Args line. Acceptance criterion
   met via the contract: the golden tests stayed green (default output
   unchanged), 895/895 total.

5. ~~**Small items**~~ **DELIVERED 2026-06-11** (three sub-items, each with a measurement):
   - *Size gate for more languages*: **FALSIFIED** — tree-sitter is
     faster than the regex fallback at 2 MB for java/ts/swift/sql (0.1–0.3x);
     Python's 144x deviation was a quadratic `_get_ancestors` (DFS from root per
     node), rewritten to a parent chain: 284 s → 0.4 s at 2 MB (660x).
     The markdown gate confirmed (2.8x) and kept. See experiments/size_gate/.
   - *Swift skeleton noise*: `init_declaration` and friends are now recognized
     in `_SIGNIFICANT_NODE` (constructor/destructor/init/deinit/subscript);
     multi-line init headers are kept whole instead of `…` + `) {`.
   - *sg-T4/glimpse comment*: trailing comments are reattached to kept
     lines in Python skeletons (tokenize-based; the generic skeleton already
     had this property). Measured +0.42 %/+0.93 % tokens on scantool and the
     internal backend (sg), the sg-T4 trailing-comment line is covered. Preceding
     comment lines deliberately out of scope. See experiments/trailing_comments/.
   The golden tests stayed green through all three — the default surface's
   only changes are the skeleton improvements themselves. Suite: 897.

## Open research tracks (post-1.0)

- M2c: more SWE-bench instances (django/sympy for scale), more runs
  per cell, inter-rater grading
- Per-node churn into directory weighting (requires a cheaper blame strategy)
- Delta mode across processes (persisted memory with consent)

## The evidence archive

- experiments/condensation/ — the skeleton/condensation measurements
- experiments/entropy_metrics/ — the metric, architecture, depth, dedup and
  glimpse experiments with all the null results
- experiments/benchmark/ — harness, SWE-bench suite, M2b with raw logs
- The commit history b703458..HEAD — every change carries its measurement
