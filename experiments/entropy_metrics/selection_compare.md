# Excerpt selection before/after the metric switch (2026-06-10)

Raw data: `selection_before.json` / `selection_after.json`
(generated with `capture_selection.py`, 14 representative files).

The switch: `_compression_ratio` (r=−0.80 against size, inverted rankings)
+ `_structural_uniqueness` (O(n²)) → `_conditional_compression`
(zlib with 16 KB of context per side as dictionary). Weights: 0.30 shannon +
0.50 conditional + 0.20 centrality. Cost: 14.6 → 11.2 ms/file (faster).

## Changes per file

| File | Before | After | Assessment |
|---|---|---|---|
| code_map.py | 1: `_format_file_size` | 4: +`_discover_files`, `_calculate_centrality`, `_format_age` | Core logic in |
| languages/base.py | 1: `_fragment_prefix` | 7: +`condense_excerpt`, `_should_use_fallback`, `find_entry_points`, … | Core logic in |
| languages/python.py | 10 | 15: +`condense_excerpt`, `extract_definitions`, `_has_substance` | More method content |
| ruby/basic.rb | 1: `initialize` (boilerplate) | 2: `validate_email`, `main` | Logic over init |
| c_cpp/edge_cases.cpp | 16 (w. `insert`×2, `NonCopyable`×4) | 12 (duplicates reduced, +`lambda_example`) | The dedup effect works |
| go/edge_cases.go | 2 (w. `Add` — repetitive generics) | 1: `ProcessWithIgnored` | Repetition out |
| go/basic.go | `Query`, `FormatTimestamp`, `main` | `ValidateEmail`, `FormatTimestamp` | Shift, neutral/better |
| rust/edge_cases.rs | 7 (w. `Container`, `User` structs) | 6: +`process`, `raw_pointer_access`, `ffi_function` | Logic over structs |
| preview.py | 4 (w. 28-line literal `__init__`) | 4 (`__init__` out, `format_size` in) | Boilerplate out |
| swift/basic.swift | 10 (w. `init`, `query`) | 6 (+`formatTimestamp`; `query` out) | Mixed — `query` was arguably interesting |
| scanner.py | 2 trivial getters | unchanged | **Null finding** |
| typescript/basic.ts | 5 | unchanged | Null finding |
| entropy/core.py | 4 | unchanged | Null finding |
| formatter.py | 0 | 0 | — |

## Observations (patterns, not ground truth)

- **Duplicates and repetition are deprioritized**: the C++ copies (`NonCopyable`×4→2,
  `insert`×2→1) and Go generics boilerplate disappeared — exactly the effect
  conditional compression predicted.
- **Unique logic comes in**: `_discover_files`, `_calculate_centrality`,
  `condense_excerpt`, `validate_email` — functions one actually wants to see.
- **Three null findings**: scanner.py, typescript, entropy/core.py unchanged.
  scanner.py still picks two trivial getters — the remaining weakness
  likely lies in the partitioning/coverage mapping, not the metric.
- **One debatable**: Swift lost `query` (a 4-line stub returning
  `[]` — low new-information is technically correct, but the name is central).

## Conclusion

The switch moves the selection systematically from repetition/boilerplate toward unique
logic, at lower cost. Not perfect (the null findings show the metric is
not the whole picture), but unambiguously better than inverted.
