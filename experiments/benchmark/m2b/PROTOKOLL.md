# M2b-protokoll: reproduksjon av agent-episodene

## Infrastruktur (denne mappen)

- `tool.sh` — wrapper for grep-baseline: logger all output per episode
- `scantool_cli.py` — CLI-eksponering av scantool-verktøyene med logging
- `logs/` — råloggene fra alle 22 episodene (bevismaterialet bak tallene
  i ../M2B.md; `smoke.log` er røyk-testen)
- Oppgaver med fasit: `../m2b_tasks.json`, forventninger:
  `../M2B_preregistrert.md`

## Episodeprompt-maler (brukt ordrett, kun {q}/{dir}/{log} substituert)

### grep-baseline

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
(samme ramme, men:)
- You may explore ONLY by running scantool via your Bash tool, exactly like this:
    uv run --project <scantool-repo> python .../scantool_cli.py {log} <cmd>
  Available <cmd> forms:
    preview DIR / scandir DIR [GLOB] / scanfile PATH [BUDGET] /
    search DIR REGEX / searchname DIR REGEX
```

Kjøring: én fersk haiku-subagent per episode, parallelle batcher à 5–6.

## Gradering per episode (fakta fra m2b_tasks.json funnet i agentens
   sluttmelding; konvensjon: hele sluttmeldingen, ikke kun ANSWER-linjen)

| Episode | grep | scantool | Notat |
|---|---|---|---|
| sg-T1 cache-invalidering | 3/5 | **5/5** | grep manglet run_model_calculation, delete_model |
| sg-T2 token-utløp | **4/4** | 3/4 | scantool nevnte ikke expires_delta |
| sg-T3 indikator-regler | 5/5 | 5/5 | |
| sg-T4 grid-TTL | 2/2 | 2/2 | semantisk tvetydighet: None = «evig» vs «ingen caching» |
| sg-T5 arkitektur | 2/5 | **5/5** | grep manglet startup_validation, get_pool, health_check |
| sb-flask-4045 | 1/2 | **2/2** | grep manglet add_url_rule |
| sb-flask-5063 | **1/2** | 0/2 | scantool-agent valgte wrappers.py — feil fil |
| sb-requests-1963 | 2/2 | 2/2 | |
| sb-requests-2674 | 0/1 | **1/1** | grep ankret i models.py; gullpatch = adapters.py |
| sb-pytest-5221 | 2/2 | 2/2 | |
| sb-pytest-7373 | 2/3 | 2/3 | grep manglet _istrue; scantool manglet cached_eval |
| **SUM** | **24/33 (73 %)** | **29/33 (88 %)** | |

## Kjente avvik

- sb-flask-4045-scan: første forsøk døde på API-feil; loggen inneholder
  ~2 kall fra det døde forsøket (re-kjørt, samme loggfil)
- Én gradering (ingen inter-rater), én kjøring per celle
