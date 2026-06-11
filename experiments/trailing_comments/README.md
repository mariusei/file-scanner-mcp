# Trailing comments in Python skeletons (the sg-T4 nuance)

## Background

M2b sg-T4: the skeleton showed a kept `return None` line and the agents
had to guess what TTL=None means ("caches forever" vs "does not cache").
The source carried the answer in three places: the preceding full-line
comment, the trailing comment on the kept line, and docstring line 2.
(The sg repo is a private production backend; its excerpts are redacted
in this document.)

The generic skeleton (`_skeleton_lines`) keeps raw lines and therefore
trailing comments already. Python's AST-based condensation
(`_skeleton_stmts`) loses them — ast.unparse has no comments.

## Hypothesis

Reattaching trailing comments to kept skeleton lines (via
tokenize, only comments with code before them on the same line) disambiguates
value-bearing lines at low token cost.

## Preregistered decision rules (written BEFORE the measurement)

Measured on all .py files in scantool/src and the internal backend (sg)
(real, untuned code — the sg-T4 source):

1. **Integrate** if the total skeleton token increase is < 3 % at repo level AND
   the coverage is real (> 0 affected lines in both repos) AND
   the sg-T4 trailing-comment line is actually captured.
2. **Assess manually** at an increase of 3–5 % (look at what the comments actually
   say — staleness/noise counts against).
3. **Do not integrate** at an increase > 5 %, or if the coverage is ~0
   (a null finding is a valid outcome: then sg-T4 was an isolated case).

Preceding comment lines (full-line) are kept OUT of scope — they were measured
away earlier in the condensation design (test_keeps_control_flow_and_calls
asserts that they are dropped) and carry higher noise risk. Trailing only.

## Measurement (2026-06-11)

A/B per function/method: `_skeleton_stmts(body, 0, None)` vs
`_skeleton_stmts(body, 0, _trailing_comments(source))`, tokens via
`scanner._estimate_tokens`.

| Repo | functions | affected functions | affected lines | skeleton tokens |
|---|---|---|---|---|
| scantool/src | 724 | 38 | 62 | 92 165 → 92 555 (**+0.42 %**) |
| internal backend (sg) | 156 | 31 | 41 | 28 881 → 29 149 (**+0.93 %**) |

The sg-T4 line is captured exactly — every branch in the TTL function is
disambiguated by its trailing comment. (The verbatim excerpt is redacted;
the sg source is private.)

Examples of captured content (both repos): value explanations — unit
conversions, size constants, selection thresholds — precisely
disambiguation, not prose noise.

## Decision

Rule 1 satisfied (< 3 % on both repos, real coverage, sg-T4 covered):
**INTEGRATED** in the `PythonLanguage` condensation
(`_trailing_comments` + `emit(text, row)` in `_skeleton_stmts`).
The generic skeleton (`_skeleton_lines` in the base) keeps raw lines and
had the property already. The golden tests remained green — basic.py has
no trailing comments on kept lines, so the default surface
did not drift.

Preceding comment lines remain out of scope (preregistered delimitation);
the docstring-line-2 track (sg-T4's third carrier) is not assessed here.
