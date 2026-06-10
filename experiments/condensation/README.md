# Kondensering: abstraktiv skjelett-representasjon av salient kode

## Idé

Dagens entropi-pipeline er **ekstraktiv**: den velger hvilke linjer som vises
(`scanner._annotate_salient_code`), men reprinter dem ordrett
(`formatter.py`, code_excerpt-blokken). Dette eksperimentet tester en
**abstraktiv** representasjon: intent og metode destilleres deterministisk
fra AST, uten LLM.

- **Intent** = navn + signatur + docstring (finnes allerede i strukturheaderen)
- **Metode** = skjelett av kroppen: kontrollflyt med betingelser, kall,
  aritmetikk, return/raise — trivielle setninger foldes til `…`

## Kjøring

```bash
uv run --with tiktoken python -u experiments/condensation/condense_experiment.py --smart-trunc
```

## Resultater (målt 2026-06-10, 5 kjernefiler, tiktoken cl100k_base)

| Representasjon | Tokens | % av full kilde |
|---|---|---|
| A: full kildekode | 23 585 | 100 % |
| B: dagens scan_file (verbatim excerpts) | 6 006 | 25,5 % |
| C: samme struktur, skjelett i stedet for excerpts | ~4 355 | 18,5 % |

- Per excerpt-node: skjelett bruker **47 %** av verbatim-tokens (ratio 0,47,
  spenn 0,12–0,76; størst gevinst på lange funksjoner og literal-tunge
  `__init__`).
- Bevaring målt mot funksjonskroppens AST: **100 % av kalte funksjonsnavn**,
  10/15 numeriske konstanter (tapene var `0`, `1`, `0.0` fra foldede
  trivial-tilordninger og lambda-elisjon).

### Metodisk fallgruve som ble avdekket

Første bevaringsmåling (66,7 % kall bevart) brukte regex mot excerpt-tekst
som referanse — den telte funksjonens eget `def`-navn og pseudo-kall i
docstrings/kommentarer (`H(X)`, `p(x)`) som «tapte kall». Med AST som
referansesett forsvant nesten hele tapet. Lærdom: referansesettet må være
semantisk (AST), ikke tekstuelt.

## Skjelett-regler (deterministiske)

Beholdes: `if/elif/else`, `for`, `while`, `with`, `try/except/finally`
(med betingelser), kall-uttrykk, tilordninger der RHS inneholder kall eller
aritmetikk/sammenligning/comprehension, `return`/`raise`/`assert`/`break`/
`continue`. Foldes til `…`: literal-tilordninger, docstring-uttrykk,
imports, `pass`. Lange uttrykk: lambda → `λ`, lange strenger kortes,
argumenter i nøstede kall elideres (kall-navnet overlever alltid).

## Generisk dekning for alle språk (målt 2026-06-10)

`generic_condense_experiment.py` målte en tree-sitter-basert linjemarkering
på testsamplene for alle språk. Kritisk funn fra første iterasjon:
**fold-by-default er destruktivt for deklarative språk** — CSS-ratio 0,57 og
SQL-ratio 0,34 skyldtes at innholdet (selektorer, kolonnedefinisjoner) ble
foldet bort, ikke kondensert. I deklarative språk ER de «trivielle» linjene
innholdet. Løsningen er strategi-differensiering (`CONDENSE_STRATEGY` i
`BaseLanguage`):

| Strategi | Språk | Prinsipp | Målt ratio |
|---|---|---|---|
| AST-override | Python | normaliserte setninger, folding, elisjon | 0,19–0,47 |
| `skeleton` | C/C++, C#, Go, Java, PHP, Ruby, Rust, Swift, Zig, TS | fold-by-default: behold linjer der signifikante noder starter | 0,52–0,87 |
| `compact` | CSS, SCSS, SQL, HTML | keep-by-default: dropp kun blanke, kommentarer, lukkeklammer | 0,87–0,96 |
| `None` | config, text, markdown, generic | verbatim — hver linje er innhold | — |

PHP krevde `_fragment_prefix()` (`<?php\n`) — løsrevne excerpts parses ellers
som HTML-tekst (100 % feilrate uten, 0 % med). Guard: hvis ingenting foldes,
returneres `None` — verbatim med linjenumre er da strengt bedre.

## Begrensninger / åpne spørsmål
- cl100k_base er proxy; Anthropic-tokenizer kan gi andre absoluttall
  (ratioene er trolig robuste).
- «Forståelighet for LLM» er ikke målt — kun proxy-bevaring av kall og
  konstanter. En reell test ville være en LLM-benchmark: svar på spørsmål
  om koden gitt verbatim vs skjelett.
- Konstant-tap i foldede `__init__`-tilordninger er en bevisst trade-off;
  kan løses ved å vise foldede tilordninger som `x, y, z = literaler…`.

## Mulig integrasjon

1. `condense_excerpt()` i `BaseLanguage` med tree-sitter-traversering,
   overstyrbar per språk (samme mønster som `extract_calls`).
2. `formatter.py`: skjelett-rendering av `code_excerpt` bak en
   `condense`-parameter på `scan_file`/`scan_directory` (default av inntil
   validert bredere).
3. Entropi-budsjett: med 53 % billigere excerpts kan `top_percent` økes
   (f.eks. 0,20 → 0,35) slik at *mer* av metoden vises for samme token-pris.
