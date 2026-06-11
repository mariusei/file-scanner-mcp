# M2c protocol: focus= against body-level questions

## Infrastructure (this directory)

- `tool.sh` — wrapper for shell reading (cat/head/tail/sed), logs per episode
- `scantool_cli.py` — CLI with all the M2b commands + `focusread PATH NODE`
- `logs/` — raw logs, named `{task}-{arm}-r{rep}.log` (arm: a/b)
- Tasks with ground truth: `../m2c_tasks.json`, expectations:
  `../M2C_preregistered.md` (committed BEFORE implementation and episodes)

## Arms

Identical except for focusread in the command list:

- **Arm A:** scantool CLI (preview/scandir/scanfile/search/searchname)
  + shell reading via tool.sh
- **Arm B:** same + focusread

Cost steering (the M2b-v2 lesson) is identical in both arms' prompts.

## Episode prompt template (used verbatim, only {q}/{dir}/{log} substituted)

```
You are a code exploration agent in a measured experiment. Follow the rules EXACTLY.

TASK: {q}
CODEBASE DIRECTORY: {dir}

EXPLORATION RULES:
- You may explore ONLY with these two wrappers via your Bash tool:
  1. scantool:
     uv run --project /Users/mariusbergeeide/Projects/scantool python /Users/mariusbergeeide/Projects/scantool/experiments/benchmark/m2c/scantool_cli.py {log} <cmd>
     Available <cmd> forms:
       preview DIR / scandir DIR [GLOB] / scanfile PATH [BUDGET] /
       search DIR REGEX / searchname DIR REGEX
       [ARM B ONLY:] / focusread PATH NODE   (read one function/class/section verbatim with parent context; NODE may be qualified like ClassA.method)
  2. shell read:
     bash /Users/mariusbergeeide/Projects/scantool/experiments/benchmark/m2c/tool.sh {log} <command>
     where <command> may use only: cat, head, tail, sed
- NEVER use your built-in Read, Grep, Glob or any other file tools directly, and never run commands outside the two wrappers.
- Maximum 6 wrapper invocations total. Then you MUST answer.

COST GUIDANCE:
- search/searchname is the cheapest first call for targeted questions
- scanfile: always pass a BUDGET (300 = quick look, 1500 = overview)
- preview is EXPENSIVE (~4-5k tokens) — only for first-time orientation
- Stop and answer as soon as you can.

FINAL OUTPUT — end your reply with exactly one line:
ANSWER: <concise, complete answer to the task question>
```

Execution: one fresh haiku subagent per episode, parallel batches.
8 tasks × 2 arms × 2 reps = 32 episodes.

## Measurement

- Fact coverage: facts from m2c_tasks.json recovered in the whole final
  message (semantic equivalence accepted, cf. the preregistration's convention)
- Read tokens (P2): tiktoken over log segments from cat/head/tail/sed and
  focusread calls; all other calls are navigation
- focusread use (P3): share of arm B episodes with ≥1 focusread call
- Wrong anchors (P5): final messages naming the wrong file/function
