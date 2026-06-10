# Kompresjonsmetrikk-eksperiment: betinget kompresjon vs dagens ratio

## Bakgrunn

Målt 2026-06-10: dagens `_compression_ratio` korrelerer r=−0,80 med
log(partisjonsstørrelse) — zlib-overhead dominerer små partisjoner, så
metrikken måler størrelse, ikke kompleksitet (20–25 % vekt i saliency).

## Kandidater

- **A (dagens):** `len(zlib(p)) / len(p)`
- **B (overhead-korrigert):** trekker fra tom-kompresjon-baseline
- **C (betinget):** `len(zlib(p, zdict=resten av filen)) / len(p)` — måler
  hvor mye *ny* informasjon partisjonen tilfører gitt konteksten

## Resultater (kjør `compression_experiment.py`)

**Størrelses-konfundering** — korr(log size, metrikk), 4 filer:

| | A dagens | B korrigert | C betinget |
|---|---|---|---|
| preview.py | −0,80 | −0,61 | −0,15 |
| languages/python.py | −0,69 | −0,44 | −0,23 |
| code_map.py | −0,66 | −0,38 | −0,16 |
| go/edge_cases.go | −0,72 | −0,36 | −0,52 |

**Diskriminering (kjent fasit):** unik kompleks funksjon blant 6
nær-identiske boilerplate-kopier:
- A og B rangerer den unike funksjonen **#7/7 — sist**. Dagens metrikk er
  ikke bare støyete; den er *invertert* på denne oppgaven (boilerplate
  komprimerer litt dårligere isolert enn variert logikk).
- C rangerer den **#1/7** med 3× margin (0,55 vs 0,18).

Repetert høyentropi-blob vs unik logikk: A/B setter blob-kopiene øverst
(0,94); C setter logikken først og kopiene nær null (0,03) — betinget
kompresjon fanger unikhet og kompleksitet i én metrikk.

**Kostnad** (languages/python.py, 320 partisjoner):

| | tid/fil | diskriminering | konfundering |
|---|---|---|---|
| A | 1,7 ms | #7/7 | −0,69 |
| C level 6 | 10,0 ms | #1/7 | −0,30 |
| C level 9 | 13,8 ms | #1/7 | −0,23 |
| `_structural_uniqueness` (dagens, O(n²)) | 10,8 ms | — | — |

## Konklusjon — integrert 2026-06-10

C erstattet **både** `_compression_ratio` og `_structural_uniqueness` i
`entropy/core.py` (`_conditional_compression`, zlib level 6, 16 KB kontekst
per side). Ny vekting: 0,30 shannon + 0,50 betinget + 0,20 centrality
(0,35/0,65 uten centrality). Netto raskere: 14,6 → 11,2 ms/fil.

Effekt på excerpt-utvalget: se `selection_compare.md` — duplikater og
boilerplate ut (C++-kopier, literal-`__init__`), unik kjernelogikk inn
(`_discover_files`, `condense_excerpt`, `validate_email`). Tre null-funn
der utvalget var uendret.

## Forbehold

- Syntetisk fasit: to konstruerte tester, ikke menneskevurdert ground truth
- Go-filen beholder −0,52 konfundering for C — kan være legitim (større
  funksjoner tilfører genuint mer unik informasjon) eller liten-fil-artefakt
- zdict-vinduet er 32 KB — for filer > 32 KB ser konteksten bare nærmeste
  omegn
