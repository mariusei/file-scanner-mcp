# M2c-protokoll: focus= mot kroppsnivå-spørsmål

## Infrastruktur (denne mappen)

- `tool.sh` — wrapper for shell-lesing (cat/head/tail/sed), logger per episode
- `scantool_cli.py` — CLI med alle M2b-kommandoene + `focusread STI NODE`
- `logs/` — rålogger, navngitt `{task}-{arm}-r{rep}.log` (arm: a/b)
- Oppgaver med fasit: `../m2c_tasks.json`, forventninger:
  `../M2C_preregistrert.md` (committet FØR implementasjon og episoder)

## Armer

Identiske bortsett fra focusread i kommandolisten:

- **Arm A:** scantool-CLI (preview/scandir/scanfile/search/searchname)
  + shell-lesing via tool.sh
- **Arm B:** samme + focusread

Kostnadsstyring (M2b-v2-lærdommen) er identisk i begge armers prompt.

## Episodeprompt-mal (brukt ordrett, kun {q}/{dir}/{log} substituert)

```
You are a code exploration agent in a measured experiment. Follow the rules EXACTLY.

TASK: {q}
CODEBASE DIRECTORY: {dir}

EXPLORATION RULES:
- You may explore ONLY with these two wrappers via your Bash tool:
  1. scantool:
     uv run --project /Users/dev/Projects/scantool python /Users/dev/Projects/scantool/experiments/benchmark/m2c/scantool_cli.py {log} <cmd>
     Available <cmd> forms:
       preview DIR / scandir DIR [GLOB] / scanfile PATH [BUDGET] /
       search DIR REGEX / searchname DIR REGEX
       [KUN ARM B:] / focusread PATH NODE   (read one function/class/section verbatim with parent context; NODE may be qualified like ClassA.method)
  2. shell read:
     bash /Users/dev/Projects/scantool/experiments/benchmark/m2c/tool.sh {log} <command>
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

Kjøring: én fersk haiku-subagent per episode, parallelle batcher.
8 oppgaver × 2 armer × 2 reps = 32 episoder.

## Måling

- Fakta-dekning: fakta fra m2c_tasks.json gjenfunnet i hele sluttmeldingen
  (semantisk ekvivalens godtas, jf. preregistreringens konvensjon)
- Lese-tokens (P2): tiktoken over loggsegmenter fra cat/head/tail/sed- og
  focusread-kall; øvrige kall er navigasjon
- focusread-bruk (P3): andel arm B-episoder med ≥1 focusread-kall
- Feilankre (P5): sluttmeldinger som navngir feil fil/funksjon
