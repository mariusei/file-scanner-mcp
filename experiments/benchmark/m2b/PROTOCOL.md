# M2b protocol: reproducing the agent episodes

## Infrastructure (this directory)

- `tool.sh` — wrapper for the grep baseline: logs all output per episode
- `scantool_cli.py` — CLI exposure of the scantool tools with logging
- `logs/` — the raw logs from all 22 episodes (the evidence behind the
  numbers in ../M2B.md; `smoke.log` is the smoke test)
- Tasks with ground truth: `../m2b_tasks.json`, expectations:
  `../M2B_preregistered.md`

## Episode prompt templates (used verbatim, only {q}/{dir}/{log} substituted)

### grep baseline

```
You are a code exploration agent in a measured experiment. Follow the rules EXACTLY.

TASK: {q}
CODEBASE DIRECTORY: {dir}

EXPLORATION RULES:
- You may explore ONLY by running this exact wrapper via your Bash tool:
    bash .../tool.sh {log} <command>
  where <command> may use only: grep, find, cat, head, tail, sed, ls, wc
- NEVER use your built-in Read, Grep, Glob or any file tools directly, and never run commands outside the wrapper.
- Maximum 6 wrapper invocations. Then you MUST answer.

FINAL OUTPUT — end your reply with exactly one line:
ANSWER: <file path(s)> :: <function/class name(s)> :: <one short explanation>
```

### scantool

```
(same frame, but:)
- You may explore ONLY by running scantool via your Bash tool, exactly like this:
    uv run --project <scantool-repo> python .../scantool_cli.py {log} <cmd>
  Available <cmd> forms:
    preview DIR / scandir DIR [GLOB] / scanfile PATH [BUDGET] /
    search DIR REGEX / searchname DIR REGEX
```

Execution: one fresh haiku subagent per episode, parallel batches of 5–6.

## Grading per episode (facts from m2b_tasks.json found in the agent's
   final message; convention: the whole final message, not only the ANSWER line)

| Episode | grep | scantool | Note |
|---|---|---|---|
| sg-T1 cache invalidation | 3/5 | **5/5** | grep missed run_model_calculation, delete_model |
| sg-T2 token expiry | **4/4** | 3/4 | scantool did not mention expires_delta |
| sg-T3 indicator rules | 5/5 | 5/5 | |
| sg-T4 grid TTL | 2/2 | 2/2 | semantic ambiguity: None = "forever" vs "no caching" |
| sg-T5 architecture | 2/5 | **5/5** | grep missed startup_validation, get_pool, health_check |
| sb-flask-4045 | 1/2 | **2/2** | grep missed add_url_rule |
| sb-flask-5063 | **1/2** | 0/2 | scantool agent chose wrappers.py — wrong file |
| sb-requests-1963 | 2/2 | 2/2 | |
| sb-requests-2674 | 0/1 | **1/1** | grep anchored in models.py; gold patch = adapters.py |
| sb-pytest-5221 | 2/2 | 2/2 | |
| sb-pytest-7373 | 2/3 | 2/3 | grep missed _istrue; scantool missed cached_eval |
| **SUM** | **24/33 (73%)** | **29/33 (88%)** | |

## Known deviations

- sb-flask-4045-scan: the first attempt died on an API error; the log
  contains ~2 calls from the dead attempt (re-run, same log file)
- One grader (no inter-rater), one run per cell
