# Excerpt-utvalg før/etter metrikkbytte (2026-06-10)

Rådata: `selection_before.json` / `selection_after.json`
(generert med `capture_selection.py`, 14 representative filer).

Bytte: `_compression_ratio` (r=−0,80 mot størrelse, inverterte rangeringer)
+ `_structural_uniqueness` (O(n²)) → `_conditional_compression`
(zlib med 16 KB kontekst per side som ordbok). Vekter: 0,30 shannon +
0,50 betinget + 0,20 centrality. Kostnad: 14,6 → 11,2 ms/fil (raskere).

## Endringer per fil

| Fil | Før | Etter | Vurdering |
|---|---|---|---|
| code_map.py | 1: `_format_file_size` | 4: +`_discover_files`, `_calculate_centrality`, `_format_age` | Kjernelogikk inn |
| languages/base.py | 1: `_fragment_prefix` | 7: +`condense_excerpt`, `_should_use_fallback`, `find_entry_points`, … | Kjernelogikk inn |
| languages/python.py | 10 | 15: +`condense_excerpt`, `extract_definitions`, `_has_substance` | Mer metode-innhold |
| ruby/basic.rb | 1: `initialize` (boilerplate) | 2: `validate_email`, `main` | Logikk fremfor init |
| c_cpp/edge_cases.cpp | 16 (m. `insert`×2, `NonCopyable`×4) | 12 (duplikater redusert, +`lambda_example`) | Dedup-effekten virker |
| go/edge_cases.go | 2 (m. `Add` — repetitiv generikk) | 1: `ProcessWithIgnored` | Repetisjon ut |
| go/basic.go | `Query`, `FormatTimestamp`, `main` | `ValidateEmail`, `FormatTimestamp` | Skifte, nøytralt/bedre |
| rust/edge_cases.rs | 7 (m. `Container`, `User` structs) | 6: +`process`, `raw_pointer_access`, `ffi_function` | Logikk fremfor structs |
| preview.py | 4 (m. 28-linjers literal-`__init__`) | 4 (`__init__` ut, `format_size` inn) | Boilerplate ut |
| swift/basic.swift | 10 (m. `init`, `query`) | 6 (+`formatTimestamp`; `query` ut) | Blandet — `query` var arguably interessant |
| scanner.py | 2 trivielle gettere | uendret | **Null-funn** |
| typescript/basic.ts | 5 | uendret | Null-funn |
| entropy/core.py | 4 | uendret | Null-funn |
| formatter.py | 0 | 0 | — |

## Observasjoner (mønstre, ikke fasit)

- **Duplikater og repetisjon nedprioriteres**: C++-kopiene (`NonCopyable`×4→2,
  `insert`×2→1) og Go-generikk-boilerplate forsvant — nøyaktig effekten
  betinget kompresjon predikerte.
- **Unik logikk kommer inn**: `_discover_files`, `_calculate_centrality`,
  `condense_excerpt`, `validate_email` — funksjoner man faktisk vil se.
- **Tre null-funn**: scanner.py, typescript, entropy/core.py uendret.
  scanner.py velger fortsatt to trivielle gettere — gjenstående svakhet
  ligger trolig i partisjonering/coverage-mapping, ikke metrikken.
- **Én diskutabel**: Swift mistet `query` (4-linjers stub som returnerer
  `[]` — lav ny-informasjon er teknisk korrekt, men navnet er sentralt).

## Konklusjon

Skiftet flytter utvalget systematisk fra repetisjon/boilerplate mot unik
logikk, til lavere kostnad. Ikke perfekt (null-funnene viser at metrikken
ikke er hele bildet), men entydig bedre enn invertert.
