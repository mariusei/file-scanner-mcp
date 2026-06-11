# M2 benchmark: information-delivery efficiency

**The question:** can scantool in practice be matched by grep + file reading?
Measured as tokens and tool calls until all ground-truth facts for a task are
visible in accumulated tool output, under canonical (documented, criticizable)
strategies per toolset. Run: `uv run --with tiktoken python
experiments/benchmark/harness.py`

## Results (internal-backend backend, 2026-06-10)

| Task | scantool | grep baseline | Margin |
|---|---|---|---|
| T1 concept: cache invalidation | **378 tok / 1 call** | 9,370 / 4 | scantool **25×** |
| T2 concept: token expiry | **955 / 1** | 1,101 / 1 | ~tie |
| T3 structure: indicator rules | **140 / 1** | 1,898 / 1 | scantool **14×** |
| T4 literal: grid TTL | 4,144 / 3 | **3,068 / 4** | grep 1.4× |
| T5 overview: backend architecture | 4,466 / 1 | **2,763 / 2** | grep 1.6× |
| **Sum** | **10,083 / 7** | 18,200 / 12 | scantool 1.8× |

## Interpretations

1. **The moat is exactly where it was predicted**: targeted concept and
   structure searches ("where is the cache invalidated", "which rule types
   exist") — 14–25× fewer tokens, because the hits are delivered with the
   enclosing function, signature and range in a single call, while the grep
   agent must open files to get the context.
2. **Grep wins literal lookups** (T4, as designed — the credibility test
   passed) and this overview task (T5): `cat README + main.py` is cheap
   when the ground truth lives in the top-level files. Preview delivers
   qualitatively more (centrality, health, git activity), but the T5 ground
   truth did not require it.
3. **Calls count too**: 7 vs 12 calls = fewer round trips, lower latency and
   less context fragmentation — not priced into the token numbers.

## Honest limitations

- **Scripted strategies, not real agents** — this measures information
  delivery (necessary, not sufficient). M2b = real agent episodes with the
  same tasks.
- The baseline is deliberately generous (±40-line windows around hit
  clusters, top-3 files): the first version with top-2 failed T4 because the
  answer lived in the file with the fewest hits — realistic grep pain, but we
  gave the baseline the benefit.
- Substring ground truth can in principle be hit by chance; the facts are
  chosen to be distinct.
- One repo, five tasks. The v1.0 gate requires the same margin on repos we
  have not tuned against, with more tasks per category.

## The SWE-bench suite (externally anchored, 2026-06-10)

Six instances from SWE-bench Lite (flask, requests, pytest — the repos used
for LLM agent testing in practice), checked out at the instance's
base_commit. **Ground truth = the files and functions the gold patch actually
touched** (mechanically extracted; names the patch added are excluded — they
do not exist at base). Prepare: `prepare_swebench.py`, run: `harness.py
--swebench`.

| Instance | scantool | grep | Margin |
|---|---|---|---|
| flask-4045 (blueprint validation) | **3,221 / 1** | 11,212 / 1 | **3.5×** |
| flask-5063 (routes/domains) | 5,205 / 2 | **3,119 / 3** | grep 1.7× |
| requests-1963 (resolve_redirects) | 326 / 1 | 134 / 1 | ~tie |
| requests-2674 (urllib3 exceptions) | **2,691 / 1** | 4,480 / 1 | **1.7×** |
| pytest-5221 (fixture scope) | **2,295 / 1** | 9,532 / 1 | **4.2×** |
| pytest-7373 (skipif caching) | **3,731 / 3 (100%)** | 0% after 13,450 | **scantool solves, grep fails** |

**After lead-following (leads): scantool 6/6, grep 5/6.** The leads footer in
the content search ("called in the hits, defined in another file") solved
pytest-7373: the leads pointed straight at `mark/evaluate.py`
(`MarkEvaluator@34`, `istrue@57`), and the canonical strategy follows the
first lead. Side effect on internal-backend: T4 (the literal task designed for a grep
win) now tips to scantool (2,892 vs 3,068) because the lead points directly
at the definition — the mechanism is explainable, and T5 stands as the honest
loss.

**The benchmark drove two product fixes** (the point of M2): broad searches
in large repos revealed that (1) the structure cap truncated in file order
instead of by relevance — the densest files/structures are now ranked first,
and (2) test directories dominated pure density ranking — implementation is
now ranked ahead of tests. Before the fixes scantool covered 3/6 tasks;
after: 5/6.

Findings along the way, documented for honesty's sake: the first query choice
for flask-5063 ("subdomain") did not exist in the code at base —
feature-request instances require terms that exist BEFORE the fix; and fact
extraction must exclude '+' lines (the patch's new names are unfindable at
base). The remaining weakness (pytest-7373, 67%): the canonical strategy does
not follow import leads to the neighboring file — a real agent would have
made the fourth call.

## Next (M2b/M2c)

- More repos (clone unfamiliar open projects) and 3–5 tasks per category
- Real agent episodes: same tasks, agent with only baseline tools vs only
  scantool, measure tokens-to-correct-answer and answer quality
- The T5 finding is a product signal: preview should have a cheaper default
  mode or better token discipline in its sections
