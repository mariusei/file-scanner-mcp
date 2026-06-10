# Entropi-maskineriet: metrikk- og arkitektur-eksperimenter

> **Historikk:** `compression_experiment.py` målte mot den partisjonsbaserte
> pipelinen og kan ikke kjøres mot dagens kode (partisjonsfunksjonene er
> fjernet) — sjekk ut commit før node-direkte-omleggingen for å reprodusere.

## Node-direkte arkitektur (integrert 2026-06-10)

`node_direct_experiment.py` testet å score strukturnodene direkte i stedet
for innrykkspartisjoner + ≥50 % coverage-mapping. To iterasjoner:

1. **Per-byte-scoring**: kjernelogikk kom inn (`preview_directory`), men
   småtode-bias besto — trivielle gettere (`return 10`) scoret høyt fordi
   per-byte-metrikker belønner tetthet, ikke substans.
2. **Log-absolutt ny informasjon** (`log1p(komprimert størrelse gitt
   kontekst)`): «hvem tilfører filen mest metode». scanner.py gikk fra
   trivielle gettere til `scan_file`; code_map til `analyze`+`format_tree`.

**Falsifiseringssjekk** (er log-abs bare «velg største node»?): 56 % overlapp
med ren størrelsesranking, rangkorrelasjon 0,39–0,88 — størrelse bidrar
(lengre unik kode = mer informasjon), men metrikken diskriminerer reelt
(scanner.py velger ikke største node; Rust 0/4 overlapp).

Arkitekturgevinsten: partisjonering, coverage-terskel, `min_size`-hull,
linje-mapping og hele `callgraph.py` (entiteter = nodene selv) forsvant.
Tab-fiksen ble overflødig — innrykk brukes ikke lenger. Utvalgene per
generasjon ligger i `selection_before.json` (opprinnelig metrikk),
`selection_after.json` (betinget kompresjon, partisjonsbasert) og
`selection_node_direct.json` (dagens).

## Kryssfil-dedup av skjeletter (målt 2026-06-10 — NULL-FUNN, ikke integrert)

`dedup_experiment.py` målte potensialet i å vise repeterte skjelettmønstre
én gang + referanser, på to nivåer: A = eksakte duplikater (tapsfri),
B = form-duplikater med normaliserte identifikatorer (tapsfull — skjuler
medlemmenes kall-navn, dvs. selve fakta-innholdet).

| Repo | Nivå A (tapsfri) | Nivå B (tapsfull) |
|---|---|---|
| scantool/src (kunstig gunstig: 20 like språkfiler) | 3,0 % | 5,1 % |
| isowords (ekte iOS/SwiftUI, 388 filer, 1609 noder) | **0,2 %** | 3,4 % |

Selv i det mest dedup-vennlige repoet tenkelig er tapsfri besparelse 3 %;
på ekte iOS-kode 0,2 %. Form-mønstrene i isowords er dessuten degenererte
(flerlinje-init-signaturer som folder til `…` + `) {`), ikke meningsfulle
mønstre. Forklaringen er at pipelinen allerede har skvist redundansen:
skjelettene folder boilerplate *innad* i noder, betinget kompresjon
nedprioriterer duplikater i *utvalget*, og dybde-2-outlines er så små
(20–30 tokens) at referansekostnaden spiser gevinsten.

**Konklusjon: ikke verdt kompleksiteten.** Målt hierarki av gevinster:
notasjonsfrekvens (ASCII-bytte: −26 %) ≫ arkitektur (node-direkte/S6) ≫
kryssfil-dedup (≤3 %).

Bifunn: generisk skjelett på Swift med flerlinje-signaturer produserer
støylinjer (`…` + `) {`) — forbedringskandidat i `_skeleton_lines`.

## Skjelett-dybde etter saliency (målt og integrert 2026-06-10 som S6)

> **Integrert:** scanner-annoteringen gir nå alle kandidatnoder
> dybde-2-skjelett (`FileScanner.BROAD_TIER_DEPTH`), topp 20 % får full
> dybde + verbatim-excerpt. `limit_skeleton_depth()` i `languages/base.py`
> mapper innrykksbredder til nivåer per rang (virker for 1-space-AST,
> tabs og 2/4-space). Compact-strategi (deklarativt innhold) dybdekuttes
> aldri; skjeletter som etter kutt kun består av `…` droppes.
> Målt total scan_file-output på 10 src-filer: 20,1k → 31,5k tokens
> (+56 %, 39 % av full kilde) for 56,4 % vs 32,8 % fakta-dekning.

`skeleton_depth_experiment.py` testet om gradert dybde (mer salient = dypere
skjelett) gir flere synlige metode-fakta (unike kall-navn) per token.
10 Python-filer i src/, dybdekutt på AST-skjelettets innrykksnivå.

Forhåndssjekk (null-hypotesen overlevde ikke, men nyansert): 60 % av
skjelettlinjene ligger på dybde ≤ 1, 81 % på ≤ 2 — dybdekutt har moderat,
ikke stor, sparemasse.

| Strategi | Noder | Tokens | Fakta-dekning | Fakta/1k tok |
|---|---|---|---|---|
| S1 dagens (topp 20 % full) | 27 | 9 385 | 32,8 % | 23,3 |
| S2 gradert (20 full/15 d2/15 d1) | 73 | 11 692 | 43,0 % | 24,5 |
| **S7 alle noder dybde 2** | 146 | 10 708 | **47,4 %** | **29,5** |
| S6 topp 20 % full + alle d2 | 146 | 15 712 | 56,4 % | 23,9 |
| S8 alle full (referanse) | 146 | 18 548 | 63,4 % | 22,8 |

**Hovedfunn (uventet):** hypotesen «saliency-gradert dybde» er bare svakt
støttet (S2: +5 % effektivitet). Det reelle funnet er at *grunne skjeletter
er fakta-tette*: dybde-2 for ALLE noder (S7) dominerer både dagens og
gradert — +14 % tokens mot dagens gir +14,6 pp dekning og høyest
effektivitet. Saliency-rangeringens verdi for *dybde-tildeling* er liten;
verdien ligger i å velge hvem som får *full* dybde.

**Anbefalingskandidat:** S6 = universelt dybde-2-skjelett + full dybde for
topp 20 % (saliency beholder rollen «hvem fortjener hele metoden» — de mest
salient nodene har per definisjon dyp unik logikk, som er det dybdekuttet
fjerner). Prisen er +67 % skjelett-tokens mot dagens; S7 er
effektivitetsvalget hvis budsjettet er hellig.

**Forbehold:** fakta-metrikken teller unike kall-navn, ikke lesbarhet;
dybdekutt etterlater `if x:` fulgt av `…` — outline, ikke metode. Gjelder
Python-AST-skjeletter; generisk skjelett må normalisere innrykk først.

---

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
