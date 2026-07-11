# M3 preregistered expectations (written BEFORE any episode has been run)

Date: 2026-07-11. The connectivity tail is already shipped on scan_file
(server layer, `_connectivity_note`), but its value AT THE POINT OF USE is
unmeasured. This measurement decides — per research/value-synthesis.md —
whether connectivity reach onto the workhorses is kept/extended, or gated
back to the audit surfaces (find_divergence, preview_directory).

Registration status: outcome thresholds and decision rules are fixed in
this document NOW. The concrete task list (`m3_tasks.json`) must be
curated and each ground-truth fact verified (see "Task verification")
BEFORE the first episode; the task file is appended to this registration
by a commit that precedes all episode runs.

## What is being tested

The corpus-wide connectivity hint (candidate dead / orphan / drift,
self-levelling, silent when clean) appended to scan_file output. The
hypothesis is that this is the *whole-corpus prior the agent cannot
cheaply see* — it should change outcomes on tasks whose ground truth is a
corpus fact, and cost nothing on tasks where it is irrelevant.

## Design

- 2 arms, identical CLI harness (M2b infrastructure) except one thing:
  - **Arm A (baseline):** `scanfile` renders scanner+formatter output only
    (the current CLI behaviour — no connectivity tail)
  - **Arm B (connectivity):** `scanfile` appends the production
    `connectivity_tail`; the CLI help gains ONE line describing it,
    mirroring the production tool description ("candidates to look at,
    not verdicts")
- 3 task classes in `m3_tasks.json`:
  - **Class C (corpus-fact tasks, ~6):** maintenance-shaped questions whose
    ground truth is corpus-wide: "is X safe to delete?", "which handler in
    M is never reached?", "is template T rendered anywhere?". Ground truth
    made unambiguous by planted knock-outs (remove the sole caller/reference
    in a repo checkout) plus any independently verified real finds.
  - **Class D (decoy/trap tasks, ~2):** the note FIRES but the ground truth
    is a legitimate exception (reached via framework registration, entry
    point, or dynamic dispatch). Tests whether agents treat the hint as a
    verdict.
  - **Class N (neutral tasks, ~5):** M2b/M2c-style structural and body-level
    questions on the same repos where connectivity is irrelevant. Measures
    the noise/attention cost of the tail.
- 2 repetitions per cell → (13 tasks × 2 arms × 2 reps) = 52 episodes,
  one fresh haiku subagent per episode, max 6 tool calls, all tool output
  logged at construction (M2b conventions).
- Grading: facts from m3_tasks.json found in the whole final message
  (M2c convention: descriptive criteria, semantic equivalence accepted).
  Class D is graded on *calibration*: full credit only if the answer treats
  the signal as a candidate and identifies (or checks for) the legitimate
  reference; asserting "dead/unused" flatly is a miss.

## Task verification (before registration of the task file)

For every class-C and class-D task: run arm-B `scanfile` on the target file
at the pinned commit and record that the note fires and names the planted
node. A task where the note does not fire is excluded (that is a recall
finding for connectivity.py, reported separately, not silently patched
around). For class N: verify the note does NOT fire on the files the task
naturally leads to — if it fires, the task moves to class C/D or is dropped.

## Preregistered outcomes

**P1 — expected (primary, class C):** Arm B fact coverage ≥ 15 percentage
points above arm A on class-C facts. Secondary trace: arm B reaches the
corpus fact in fewer tool calls (median). A difference < 5 pp is null given n.

**P2 — cost guard (class N):** Arm B stays within noise of arm A on neutral
tasks: coverage within ±5 pp AND logged read tokens within +10%. A breach
here is a NOISE COST finding and weighs against reach regardless of P1.

**P3 — null (ignored hint):** If, in arm-B class-C episodes where the note
fired, fewer than 50% of final messages use or mention it, the finding is
steering/description, not capability. One re-run with a single added
steering line (documented as v2, cf. M2b→M2b-v2, M2c-v2); BOTH runs reported.

**P4 — null (grep-equivalence):** If arm A reaches ≥ 85% of class-C facts,
the corpus fact is cheaply derivable without the tail (the agent greps for
callers itself), and point-of-use connectivity is redundant — a valid,
valuable outcome: tier-1 + niche audit is the honest scope.

**P5 — paradox (false authority, class D):** Arm B scores LOWER than arm A
on decoys — the hint anchors the agent into asserting dead code that is
alive. This is the trust-framing failure ("look here" read as "this is a
bug"). If P5 occurs while P1 holds, the tail's wording (not its existence)
is the suspect; a wording v2 may be run, both runs reported.

## Decision rule (fixed now)

- P1 holds AND P2 holds AND no P5 → keep the tail on scan_file; extend
  opt-in reach to search_structures next (with its own measurement).
- P4, or P2 breached, or P1 null → gate the tail back to the audit
  surfaces / behind an opt-in flag; tier-1 + audit is the honest scope.
  This outcome is accepted in advance.

## Assumptions (explicit)

- Planted knock-outs are representative of real abandoned code; the two
  independently verified real finds (route + template class) anchor realism
- Haiku agents read tails at all — if the tail is systematically absent
  from their reasoning even after v2 steering, that is a consumption
  finding about hint placement (tail vs inline), a product finding, not noise
- 2 reps do not separate noise from small effects; anything below 5 pp is
  reported as "not distinguishable from null", not as a direction

## What would surprise the most

That arm B wins class C *and* loses class D badly — the same signal that
delivers the corpus fact also manufactures false confidence. That would
mean the binding constraint is not reach but *calibration language*, and
the next work is wording/verification affordances, not more surfaces.
