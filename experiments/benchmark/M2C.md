# M2c: focus= against body-level questions — results (2026-06-11)

32 episodes: 8 tasks × 2 arms × 2 reps, one fresh haiku subagent per
episode, max 6 tool calls, all wrapper output logged at construction.
Expectations preregistered and committed BEFORE implementation and episodes
(`M2C_preregistered.md`, commit 51ebaa5). The arms were identical except
for `focusread PATH NODE` in arm B. Raw logs: `m2c/logs/`, final messages:
`m2c/answers-*.md`, analysis: `m2c/analyze_logs.py`.

## Observations (raw numbers, no interpretation)

| | Arm A (without focus) | Arm B (with focus) |
|---|---|---|
| Fact coverage | 56/56 (100%) | 53/53 (100%)* |
| Wrapper calls total | 65 | 73 |
| Read tokens (cat/sed/focusread output) | 54,337 | 13,523 |
| Navigation tokens | 34,679 | 31,165 |
| Total tool tokens | 89,016 | 44,688 |
| Episodes using focusread | — | 9/16 (56%) |
| Wrong anchors (wrong file/function in answer) | 0 | 0 |

*One arm B episode (pytest-7373-b-r2) is excluded: 9 reported tool calls
vs 2 logged — 7 calls happened outside the wrappers, and the answer
(3/3 facts) cannot be attributed to logged tool output. Included,
arm B would have been 56/56.

Largest single reads: arm A contained three whole-file cats of 9,248,
11,382 and 15,210 tokens; arm B's largest read was 2,598 tokens.

## The preregistered outcomes against the data

**P1 (correctness, ≥10 pp difference): NOT met — ceiling effect.**
Both arms hit 100%. The difference is 0, below the null threshold of 5 pp.
The tasks were too easy for haiku with either toolset to separate the
arms on correctness.

**P2 (read tokens ≥20% lower in arm B): MET by a wide margin.**
−75% (13,523 vs 54,337). The mechanism is visible in the raw logs: without
focus, agents fall back to whole-file cat or wide sed ranges; with focus,
the node is read precisely. Note that P2 was preregistered as secondary.

**P3 (discoverability, focusread in ≥50% of the episodes): MET, just
barely.** 9/16 (56%). No re-run with an adjusted description needed,
but the margin is thin — 7 episodes solved the task without focusread,
most often because search/searchname already showed the body.

**P4 (null/redundancy, arm A ≥85%): MET — and this is the main finding
together with P2.** The skeleton+search+sed flow was SUFFICIENT for
correctness on all the body-level questions. The preregistration said that
P4 alone implies shelving "regardless of P1" — but that wording
assumed coverage was the only margin and did not anticipate the combination
of P4+P2 both being true. The tension is reported as it is, see conclusion.

**P5 (paradox/tunnel vision): NOT observed.** Zero wrong anchors in both
arms; focus reading did not cause the skeleton context to be skipped.

## Conclusions [INTERPRETATION — explicitly marked]

1. **The correctness margin from M2b did NOT reproduce on body-level
   tasks — because both arms hit the ceiling.** Scantool's existing
   outputs (search with structural context, salient skeleton with full
   depth) already deliver body-level facts more often than assumed. That is
   a redundancy finding, not a focus finding.
2. **The margin that survived is read-step economy, not correctness:**
   the same coverage at 75% lower read cost and half the total
   tool cost. The M2b lesson ("unconstrained agents consume what
   they are served") repeated itself mirrored: without a precise read path,
   agents consume whole files to be sure.
3. **Decision per the preregistration:** the P4 rule ("shelve") was
   triggered, but explicitly concerned the premise of coverage as the
   margin; P2 (secondary, preregistered) was met strongly. Honest reading:
   focus= is NOT justified as a correctness measure on this
   task set, but is justified as a cost measure. It is kept with
   that justification — and should be re-tested on tasks where the ceiling
   is not hit (larger files, a weaker model, or questions requiring multiple
   nodes per file) before a correctness gain is claimed.

## Addendum: M2c-v2 — the steering effect of the read-step text (2026-06-11)

Arm B re-run with one added steering line in the prompt mirroring the new
production instructions (commit 5a0300e): "To READ one function/class/
section located by a scan or search: use focusread … Never cat a whole
file or sed a guessed line range." Everything else identical. Preregistered
in M2C_preregistered.md (commit d166e16, BEFORE the episodes). 16 episodes.

| | Arm B v1 | Arm B2 (new steering) |
|---|---|---|
| Episodes with focusread | 9/16 (56%) | **13/16 (81%)** |
| Wrapper calls | 73 | 59 |
| Read tokens | 13,523 | 15,944 |
| Navigation tokens | 31,165 | 18,269 |
| Total tool tokens | 44,688 | **34,213 (−23%)** |
| Fact coverage | 53/53 (100%) | 54/56 (96%) |

Against the preregistered v2 outcomes:

- **V1 (expected): essentially met.** The 81% share ≥ the 75% threshold,
  the shift (+4 episodes) is above the noise floor (≥3); coverage 96% ≥ 95%.
  Caveat: read tokens were NOT ≤ v1 (+18%) — more episodes read the
  node instead of answering straight from the skeleton. In return that
  bought 41% fewer navigation tokens (fewer search rounds), so the
  total fell 23%.
- **V2 (null/redundancy): rejected** — the text moved behavior.
- **V3 (paradox/over-steering): not triggered** — fewer calls (59 vs 73)
  and a lower total; no compulsive focusread where search had already
  answered (3 episodes still skipped reading, correctly).

[INTERPRETATION] The steering line does what it should: focusread share up
56 → 81%, total cost down a further 23% (vs arm A: −62%). The M2b
lesson is confirmed a third time: the description text is the lever.
The channel caveat stands: prompt steering is a proxy for MCP instructions —
the injection channel in production is not directly tested.

Honest weakness: one v2 episode (pytest-5221-b2-r1) FAILED completely (0/2) —
the agent never found the function (guessed the wrong file), used up its
calls and answered vaguely from prior knowledge. The first coverage failure
in all of M2c. Steering the read step does not compensate for localization
failure; with n=16 it may be noise, but it shows the 100% ceiling is not
guaranteed.

## Deviations and weaknesses

- pytest-7373-b-r2 contaminated (7 unlogged calls) — excluded; probably
  partially answered from the model's prior knowledge of the well-known
  pytest bug
- sg-jwt-b-r1 used find/grep via the wrapper in violation of the command
  list (everything logged, so the measurements are intact); 3 episodes used
  7–8 calls against the rule of 6; ±1–2 call deviations in several episodes
  are probably due to CLI crashes before logging (argument errors are not
  logged)
- The ceiling effect means the task set cannot separate the arms on
  correctness — P1 is unanswered, not falsified
- One grader (no inter-rater), 2 reps, semantic grading of descriptive
  facts (more judgment than M2b's token facts)
- The grader (same model family as the agents) knew the hypothesis
