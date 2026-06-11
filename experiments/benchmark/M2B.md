# M2b: Real agent episodes — results (2026-06-11)

22 episodes: 11 tasks × 2 toolsets, one fresh haiku subagent per episode,
max 6 tool calls, all tool output logged through a wrapper (measured at
construction). Preregistered expectations in `/tmp/m2b/PREREGISTRERT.md`,
written before the first episode.

## Headline numbers

| | grep agents | scantool agents |
|---|---|---|
| Fact coverage in answers | 24/33 (**73%**) | 29/33 (**88%**) |
| Tool calls total | 64 | 60 |
| Logged tool tokens | **61,027** | 91,128 |
| Total agent tokens | **249,872** | 329,092 |

## Expectation 1 FALSIFIED — and that is the main finding

Preregistered: "scantool agents with ≥2× fewer logged tokens". Result: the
scantool agents used **1.5× MORE**. The explanation is the difference
between what the harness measures and what agents do:

- The harness measures tokens UNTIL the facts are visible (early stop)
- Real agents stop at *subjective certainty*, not at fact coverage — and
  scantool's rich outputs (preview ≈ 4–5k tokens, scandir ≈ 2k) INVITE
  consumption. Nothing pushes the agent to use the budget dial; the
  canonical funnel exists in the tool descriptions, but the CLI prompt did
  not enforce it

## Expectation 2 CONFIRMED: correctness

The scantool agents gave measurably better answers (88% vs 73% fact
coverage):

- **sg-T1**: scantool named both trigger functions with line numbers
  (run_model_calculation@381, delete_model@878) + a precise negative
  observation (datasets/indicators use TTL, not invalidation); the
  grep agent gave only the file and prose
- **sg-T5 (architecture)**: scantool 5/5 facts (startup_validation, get_pool,
  health_check named); grep 2/5
- **requests-2674**: scantool answered adapters.py (= the gold patch);
  grep anchored in models.py — wrong file
- **Honest loss, flask-5063**: the scantool agent followed the structure of
  wrappers.py (plausible but wrong); grep found cli.py

## Conclusions

1. **The margin that survives real agents is CORRECTNESS, not tokens.**
   The "cannot be matched" claim must be reformulated: scantool gives more
   correct and more complete answers (fewer wrong anchors, named functions
   and line numbers), but the token advantage is only realized with early
   stopping or budget pressure — unconstrained agents consume what they are
   served.
2. **Product signal**: rich defaults need consumption steering for agents —
   preview (4–5k) as the first choice is expensive in agents' hands; budget
   presets and a glance-first flow must be what the tool descriptions nudge
   toward. (Token allocation affects perceived importance — and output
   richness affects consumption.)
3. **Model level**: haiku agents followed the rules (log-verified in spot
   checks; not fully automated per episode — documented weakness) and
   handled both toolsets well; the tool difference showed up in answer
   quality, not in the ability to use the tools.

## Deviations and weaknesses

- flask-4045-scan crashed (API error) and was re-run; the log contains
  ~2 calls from the dead attempt (the scan numbers marginally inflated)
- Grading on the whole final message (not only the ANSWER line), one grader
  (no inter-rater), one run per cell
- sg-T4 uncovered a semantic ambiguity both toolsets inherited:
  TTL=None is interpreted as "caches forever" (grep agent) vs "does not
  cache" (scantool agent) — the ground truth does not distinguish

## Addendum: consumption steering (M2b-v2, 2026-06-11)

Acceptance criterion from BACKLOG item 1: re-run the episodes with
cost-transparent tool descriptions (the same steering that now lives in the
production docstrings: search as the first choice, a budget mandate on
scanfile, preview marked expensive, "stop when you can answer").

| 6 episodes | grep | scan-v1 | scan-v2 |
|---|---|---|---|
| Tool tokens | 19,113 | 53,264 | **23,551 (−56%)** |
| Fact coverage | 14/21 (67%) | 19/21 (90%) | **18/21 (86%)** |

The token gap closed from 2.8× to 1.2× with no real quality loss.
pytest-7373 was solved FULLY (3/3, up from 2/3) at 654 tokens:
search → lead → answer. Honest nuance: sg-T5 (architecture) fell 5/5 → 3/5 —
the steering made the agent economize exactly where richness was right
(open overview questions). Lesson: cost steering must be task-conditional
— the descriptions now say "preview for first-time orientation", and that
is the right direction, but the tension is real and documented.
