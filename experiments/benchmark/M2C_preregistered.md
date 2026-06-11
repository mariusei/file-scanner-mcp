# M2c preregistered expectations (written BEFORE focus= is implemented)

Date: 2026-06-11. Written and committed before the first line of the
`focus=` implementation and before any episode has been run.

## What is being tested

`scan_file(focus=NODE)`: file skeleton at depth 1 + the focused node verbatim
with line numbers. The hypothesis is that structural addressing of the read
step ("read this function") gives more correct body-level answers than
line/range guessing with sed/cat.

## Design

- 8 tasks (`m2c_tasks.json`) where the ground-truth facts live **inside
  function bodies** (conditions, return values, exception mapping) —
  verified present at base_commit/current commit before preregistration
- 2 arms, identical except for focus:
  - **Arm A (before):** scantool CLI (preview/scandir/scanfile/search/searchname,
    v2 descriptions) + sed/cat/head/tail via wrapper
  - **Arm B (after):** same + `focusread PATH NODE`
- 2 repetitions per cell → 32 episodes, one fresh haiku subagent per
  episode, max 6 tool calls, all output logged at construction
- Grading: facts from m2c_tasks.json found in the whole final message
  (semantic equivalence accepted, e.g. "303" = "see_other"). The convention
  deviates from M2b: the facts are descriptive criteria, not name tokens,
  because body-level facts are not greppable single words.

## Preregistered outcomes

**P1 — expected (primary, correctness):** Arm B has fact coverage ≥ 10
percentage points above arm A. (28 facts × 2 reps = 56 gradable per arm.)
A difference < 5 pp counts as null given n.

**P2 — secondary (read tokens):** Logged tokens from the *read step*
(sed/cat/focusread output) are ≥ 20% lower in arm B. M2b lesson: total
tokens are an unreliable margin; only the read step is the hypothesis's
domain.

**P3 — null (discoverability):** If focusread is used in < 50% of the
arm B episodes, the finding is a steering/description problem, not a
capability finding. In that case arm B is re-run once with an adjusted
command description (documented as v2, cf. M2b → M2b-v2), and BOTH
runs are reported.

**P4 — null (redundancy):** If arm A reaches ≥ 85% coverage, the
skeleton+sed flow proves sufficient for body-level questions, and
focus= should be shelved regardless of P1. A valid and valuable outcome.

**P5 — paradox (tunnel vision):** Arm B may get *lower* coverage if precise
node reading tempts the agent to skip the skeleton context and anchor
wrongly (the flask-5063 pattern from M2b). Recognized by: more
wrong anchors (wrong file/function in the final message) in arm B than A.

## Assumptions (explicit)

- Haiku agents manage to produce node paths (ClassA.method) from
  scanfile/search output — if not, that is a real product finding, not noise
- The ground truth is unambiguous; semantic ambiguities à la sg-T4 (TTL=None)
  are noted and excluded from the difference if they arise
- 2 reps do not separate noise from a small effect; anything below 5 pp is
  reported as "not distinguishable from null", not as a direction

## What would surprise the most

That arm B uses focusread diligently AND gets lower coverage than arm A —
that would falsify the very premise that precise reading is the bottleneck,
and point to *selection* (which node to read) being the real
bottleneck.

---

# M2c-v2 preregistered (2026-06-11, written BEFORE the v2 episodes)

Tests the STEERING EFFECT of the new read-step steering (commit 5a0300e)
in isolation: arm B is re-run with one added steering line in the episode
prompt mirroring the production instructions ("read one function → focusread,
never whole-file cat/sed guessing"). Everything else identical to arm B v1.
Channel caveat: the prompt is a proxy for MCP server instructions —
the experiment measures the text's effect, not the injection channel.

16 episodes (8 tasks × 2 reps). Baseline (arm B v1): focusread in
9/16 episodes, 13,523 read tokens, 53/53 facts.

**V1 — expected:** focusread share ≥ 12/16 (75%), read tokens ≤ the v1
level, coverage holds (≥ 95%).

**V2 — null (redundancy in steering):** share within 9/16 ± 2 — one
extra line of steering does not change behavior when the command list
already mentions the tool; in that case the discoverability bottleneck is a
capability/task trait, not a text problem.

**V3 — paradox (over-steering):** focusread is also used where search
already showed the body → more calls and HIGHER total tokens than v1
(> +20%). Steering that is not task-conditional has a cost (the sg-T5
lesson from M2b-v2).

**Noise floor:** n=16; only shifts of ≥ 3 episodes in share are
distinguishable from noise. Coverage is graded with the same convention
as M2c.
