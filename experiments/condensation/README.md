# Condensation: abstractive skeleton representation of salient code

## Idea

Today's entropy pipeline is **extractive**: it selects which lines are shown
(`scanner._annotate_salient_code`), but reprints them verbatim
(`formatter.py`, the code_excerpt block). This experiment tests an
**abstractive** representation: intent and method are distilled deterministically
from the AST, without an LLM.

- **Intent** = name + signature + docstring (already present in the structure header)
- **Method** = skeleton of the body: control flow with conditions, calls,
  arithmetic, return/raise — trivial statements are folded to `…`

## Running

```bash
uv run --with tiktoken python -u experiments/condensation/condense_experiment.py --smart-trunc
```

## Results (measured 2026-06-10, 5 core files, tiktoken cl100k_base)

| Representation | Tokens | % of full source |
|---|---|---|
| A: full source code | 23 585 | 100 % |
| B: today's scan_file (verbatim excerpts) | 6 006 | 25.5 % |
| C: same structure, skeletons instead of excerpts | ~4 355 | 18.5 % |

- Per excerpt node: skeleton uses **47 %** of the verbatim tokens (ratio 0.47,
  range 0.12–0.76; largest gains on long functions and literal-heavy
  `__init__`).
- Retention measured against the function body's AST: **100 % of called function
  names**, 10/15 numeric constants (the losses were `0`, `1`, `0.0` from folded
  trivial assignments and lambda elision).

### Methodological pitfall that was uncovered

The first retention measurement (66.7 % of calls retained) used regex against the
excerpt text as the reference — it counted the function's own `def` name and
pseudo-calls in docstrings/comments (`H(X)`, `p(x)`) as "lost calls". With the
AST as the reference set, nearly all of the loss disappeared. Lesson: the
reference set must be semantic (AST), not textual.

## Skeleton rules (deterministic)

Kept: `if/elif/else`, `for`, `while`, `with`, `try/except/finally`
(with conditions), call expressions, assignments where the RHS contains calls or
arithmetic/comparison/comprehension, `return`/`raise`/`assert`/`break`/
`continue`. Folded to `…`: literal assignments, docstring expressions,
imports, `pass`. Long expressions: lambda → `λ`, long strings are shortened,
arguments in nested calls are elided (the call name always survives).

## Generic coverage for all languages (measured 2026-06-10)

`generic_condense_experiment.py` measured a tree-sitter-based line marking
on the test samples for all languages. Critical finding from the first iteration:
**fold-by-default is destructive for declarative languages** — the CSS ratio of 0.57 and
SQL ratio of 0.34 were caused by the content (selectors, column definitions) being
folded away, not condensed. In declarative languages the "trivial" lines ARE
the content. The solution is strategy differentiation (`CONDENSE_STRATEGY` in
`BaseLanguage`):

| Strategy | Languages | Principle | Measured ratio |
|---|---|---|---|
| AST override | Python | normalized statements, folding, elision | 0.19–0.47 |
| `skeleton` | C/C++, C#, Go, Java, PHP, Ruby, Rust, Swift, Zig, TS | fold-by-default: keep lines where significant nodes start | 0.52–0.87 |
| `compact` | CSS, SCSS, SQL, HTML | keep-by-default: drop only blanks, comments, closing braces | 0.87–0.96 |
| `None` | config, text, markdown, generic | verbatim — every line is content | — |

PHP required `_fragment_prefix()` (`<?php\n`) — detached excerpts otherwise parse
as HTML text (100 % error rate without, 0 % with). Guard: if nothing is folded,
`None` is returned — verbatim with line numbers is then strictly better.

## Limitations / open questions
- cl100k_base is a proxy; the Anthropic tokenizer may give different absolute numbers
  (the ratios are likely robust).
- "Comprehensibility for an LLM" is not measured — only proxy retention of calls and
  constants. A real test would be an LLM benchmark: answering questions
  about the code given verbatim vs skeleton.
- Constant loss in folded `__init__` assignments is a deliberate trade-off;
  could be solved by showing folded assignments as `x, y, z = literals…`.

## Possible integration

1. `condense_excerpt()` in `BaseLanguage` with tree-sitter traversal,
   overridable per language (same pattern as `extract_calls`).
2. `formatter.py`: skeleton rendering of `code_excerpt` behind a
   `condense` parameter on `scan_file`/`scan_directory` (default off until
   validated more broadly).
3. Entropy budget: with 53 % cheaper excerpts, `top_percent` can be increased
   (e.g. 0.20 → 0.35) so that *more* of the method is shown for the same token price.
