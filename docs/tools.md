# MCP tools

The MCP server exposes the same capabilities as [`sct`](sct.md), for clients
that call tools rather than a shell. Every tool takes named parameters; the
tables below list each parameter with its default. Every answer opens with a
coverage line saying what was seen, shown and left out, and `output_format`
switches any tool between `"tree"` (default, for the agent to read) and
`"json"`. Both forms are frozen by golden tests.

## `preview_directory`: orientation

Entry points, the most-called functions, central files, the call-graph map
and file archetypes. The first call on an unknown codebase, roughly 3 to 5k
tokens; for targeted questions use `search_structures`.

| Parameter | Default | Meaning |
|---|---|---|
| `directory` | | The directory to analyse |
| `depth` | `"deep"` | `"quick"`: file counts and sizes; `"normal"`: imports, entry points, clusters; `"deep"`: adds hot functions and the call graph |
| `max_files` | `10000` | Safety limit |
| `max_entries` | `20` | Entries per section |
| `respect_gitignore` | `True` | Honour `.gitignore` |

Example output (`depth="deep"`, trimmed):

```
━━━ ENTRY POINTS ━━━
  server.py:main() @1658
  cli.py:main() @562

━━━ CORE FILES (by centrality) ━━━
  languages/models.py: imports 0, used by 33 files
     class StructureNode [called by 178]

━━━ HOT FUNCTIONS (most called) ━━━
  TaskQueue.pop (method): called by 1, calls 0 @app.py
```

## `scan_file`: one file's skeleton, or one node verbatim

The structure of one file with signatures, decorators and docstrings, and
each function as a condensed skeleton. `focus=` reads one node verbatim
instead of guessing a line range. `ref=` reads the file at a git ref.

| Parameter | Default | Meaning |
|---|---|---|
| `file_path` | | The file |
| `focus` | `None` | One node verbatim by name: `"query"`, `"DatabaseManager.query"`, or a markdown heading. The rest of the file stays as a one-level outline |
| `budget` | `None` | Approximate token cap; the least salient functions degrade first (full depth, outline, header only) |
| `depth` | `None` | Alias for `budget`: `"quick"`, `"normal"` or `"deep"` |
| `condense` | `True` | Skeletons; `False` gives line-numbered verbatim excerpts for the top tier |
| `show_signatures` | `True` | Function signatures with types |
| `show_decorators` | `True` | `@decorator` annotations |
| `show_docstrings` | `True` | First line of each docstring |
| `show_complexity` | `False` | Complexity metrics |
| `delta` | `True` | A re-scan shows only what changed since your previous scan of the file; a shallower budget never shortens the answer |
| `caller` | `None` | Your own id. Delta memory is kept per caller, so pass the same id on every call |
| `mode` | `"balanced"` | Saliency weight profile, `"balanced"` or `"active"` |
| `include_metadata` | `True` | File size and mtime, git churn, `[N edits/90d]` labels; `False` gives checkout-independent output |
| `ref` | `None` | Read the file at a git ref |
| `output_format` | `"tree"` | `"tree"` or `"json"` |

Example output:

```
example.py (1-57)
- file-info: 1.4KB modified: 2 hours ago
- imports: import statements (3-5)
- class: DatabaseManager (8-26)
    "Manages database connections and queries."
  - method: __init__ (self, connection_string: str) (11-13)
  - method: connect (self) (15-17)
      "Establish database connection."
  - method: query (self, sql: str) -> list (24-26)
      "Execute a SQL query."
      return self.cursor.execute(sql).fetchall()
- function: main () (53-57)
    "Main entry point."
```

Skeleton lines carry no line numbers; verbatim lines always carry `N |`.
That is how the two are told apart. Markers are plain ASCII because
box-drawing glyphs cost 2 to 3 BPE tokens each.

With `focus="DatabaseManager.query"`:

```
focus: DatabaseManager.query @24-26
example.py (1-57)
- module docstring @1 # Example Python file for testing the scanner.
- import statements @3
- DatabaseManager @8 # Manages database connections and queries.
  - __init__ (self, connection_string: str) @11
  - connect (self) @15 # Establish database connection.
  - disconnect (self) @19 # Close database connection.
  - query (self, sql: str) -> list @24 # Execute a SQL query.
     24 |     def query(self, sql: str) -> list:
     25 |         """Execute a SQL query."""
     26 |         return []
- UserService @29 # Handles user-related operations.
- validate_email (email: str) -> bool @48 # Validate email format.
- main () @53 # Main entry point.
```

Names resolve in three tiers: exact match, qualified path, then
case-insensitive substring. An ambiguous name returns the qualified candidate
list instead of guessing. Measured on real agent episodes
(`experiments/benchmark/M2C.md`): equal answer quality at 75% fewer read
tokens than line-range guessing with cat and sed.

## `scan_file_content`: the same reader on content given directly

For remote files, API responses, a git blob or stdin. The extension of
`filename` selects the parser and the name appears in the output. Same
`focus`, `budget`, `depth`, `condense`, `show_*`, `mode`, `include_metadata`
and `output_format` as `scan_file`; only the on-disk metadata, git signals,
`delta`, `caller` and `ref` are absent.

| Parameter | Default | Meaning |
|---|---|---|
| `content` | | The text to scan |
| `filename` | | A name with the right extension, e.g. `"example.py"` |

## `scan_directory`: the file tree with a gist per file

Every file with its line count, size, age and the names of its classes and
functions on one line. Replaces `ls`, `find` and `Glob` for all file types.

| Parameter | Default | Meaning |
|---|---|---|
| `directory` | | The directory |
| `pattern` | `"**/*"` | Glob; `"**/*.py"` for one type, `"**/*.{py,ts}"` for several, `"*/*"` for one level |
| `max_files` | `None` | Cap on files processed |
| `respect_gitignore` | `True` | Honour `.gitignore` |
| `exclude_patterns` | `None` | Additional exclusions, e.g. `["tests/**", "docs/**"]` |
| `delta`, `caller`, `mode`, `depth`, `include_metadata`, `ref`, `output_format` | as `scan_file` | |

Example output:

```
src/ (22 files, 15 classes, 127 functions, 89 methods)
├─ languages/
│  ├─ python.py (1-329) [11.9KB, 2 hours ago] - PythonLanguage
│  ├─ typescript.py (1-505) [18.9KB, 1 day ago] - TypeScriptLanguage
│  └─ rust.py (1-481) [17.6KB, 3 days ago] - RustLanguage
├─ scanner.py (1-232) [8.8KB, 5 mins ago] - FileScanner
└─ server.py (1-735) [27.2KB, just now] - scan_file, scan_directory, ...
```

## `search_structures`: find text or names in their structural context

`content_pattern` finds text and returns each hit with the function, class
or section it sits in, plus leads: names called in the hits that are defined
elsewhere. The other filters find structures by name, type, decorator or
size. The best first call for a targeted question; use it instead of grep.

| Parameter | Default | Meaning |
|---|---|---|
| `directory` | | Where to search |
| `content_pattern` | `None` | Regex over file content |
| `name_pattern` | `None` | Regex over structure names, e.g. `"^test_"` or `".*Manager$"` |
| `type_filter` | `None` | `"function"`, `"class"`, `"method"`, ... |
| `has_decorator` | `None` | e.g. `"@staticmethod"` |
| `min_complexity` | `None` | Structures of at least this many lines |
| `limit`, `offset` | `40`, `0` | Paging |
| `include_metadata` | `True` | As `scan_file` |
| `ref` | `None` | Search at a git ref |
| `output_format` | `"tree"` | `"tree"` or `"json"` |

## `list_directories`: folders only

| Parameter | Default | Meaning |
|---|---|---|
| `directory` | | The root |
| `max_depth` | `3` | Levels to show |
| `respect_gitignore` | `True` | Honour `.gitignore` |

## `scan_diff`: what changed, structurally

Per file: `+` added, `~` changed (signature, value or body), `=` renamed
(paired by identical body), `-` removed; new files as skeletons. Use it
instead of `git diff` for review and "what changed" questions.

| Parameter | Default | Meaning |
|---|---|---|
| `directory` | | The repository |
| `ref` | `"HEAD"` | Compared against the working tree when `ref2` is absent |
| `ref2` | `None` | The second ref; the two are compared at their merge-base |
| `no_merge_base` | `False` | Compare the tips instead |
| `review` | `False` | Append the peer-divergence section for the changed functions |
| `budget` | `1500` | Approximate token cap |
| `output_format` | `"tree"` | `"tree"` or `"json"` |

## `surface`: a package's public names

Every exported name with its signature, how it is exported and where it is
defined after re-exports. `against` prints the surface diff between two refs.

| Parameter | Default | Meaning |
|---|---|---|
| `package_dir` | | The package directory |
| `ref` | `None` | Read at a git ref |
| `against` | `None` | The ref to diff against |
| `output_format` | `"tree"` | `"tree"` or `"json"` |

## `overlap`: several branches against one base

Structures touched by two or more branches, names introduced independently,
commits two branches share beyond the base, whether each branch is already
in the base and by which criterion, and a merge-order hint.

| Parameter | Default | Meaning |
|---|---|---|
| `base` | | The base ref |
| `branches` | | The branches, as a list |
| `repo` | `None` | Repository path; default is the current one |
| `path` | `""` | Restrict to a path |
| `kind` | `""` | Restrict to a structure kind |
| `output_format` | `"tree"` | `"tree"` or `"json"` |

## `callers`: actual call sites

Definitions first, then every call site with its enclosing function and
`path:line`. Mentions in comments, docstrings and strings are not calls.

| Parameter | Default | Meaning |
|---|---|---|
| `name` | | The function or method name |
| `directory` | `"."` | Where to look |
| `ref` | `None` | Look at a git ref |
| `output_format` | `"tree"` | `"tree"` or `"json"` |

## `resolve`: an address carried between refs

The enclosing structure with its start and end at `ref_from`, and where it
is at `ref_to`: same place, renamed with an identical body, or gone with the
nearest names.

| Parameter | Default | Meaning |
|---|---|---|
| `location` | | `path:line` or `path::name` |
| `ref_from` | `None` | The ref the address is from |
| `ref_to` | `"WORKTREE"` | The ref to carry it to |
| `repo` | `None` | Repository path |
| `output_format` | `"tree"` | `"tree"` or `"json"` |

## `find_divergence`: functions out of step with their siblings

Sites that break a call pattern their peers follow: callers of X also call
Y, this one does not. The gate is self-levelling against the corpus's own
distribution, so a consistent codebase returns nothing. A finding is a
place to read, not a verified defect.

| Parameter | Default | Meaning |
|---|---|---|
| `directory` | | The directory to audit |
| `respect_gitignore` | `True` | Honour `.gitignore` |
| `max_findings` | `20` | Cap on findings |

## `history`: the commits that changed one structure

| Parameter | Default | Meaning |
|---|---|---|
| `location` | | `path::name` or `path:line` |
| `ref` | `None` | Start from a git ref |
| `repo` | `None` | Repository path |
| `output_format` | `"tree"` | `"tree"` or `"json"` |

## Response size

Claude Desktop caps an MCP tool response at 25,000 tokens; Claude Code's cap
is the `MAX_MCP_OUTPUT_TOKENS` environment variable. `budget` and `depth` on
`scan_file`, `pattern` and `max_files` on `scan_directory`, and scanning a
subdirectory keep answers under it. `.gitignore` is respected by default, so
`node_modules/` and `.venv/` never count. The coverage line says what a cap
left out and, when a budget cut something, one trailer names the call that
recovers the most.
