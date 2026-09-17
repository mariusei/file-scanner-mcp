# `sct`: the reader in the shell

Agents read most code through their shell, not through MCP tools. `sct` is
scantool's reader as a shell command. It runs the same tool functions the
MCP server exposes, under the same interpreter, and the server writes it
into uv's tool bin directory when it starts (see
[install.md](install.md#the-sct-launcher) for where, and how to opt out).

```
sct <dir> [--part ID] [--lines N]
sct scan     <path>... [--ref REF] [--budget N] [--depth quick|normal|deep] [--lines N]
sct scan     - [...]                     paths from stdin, one per line
sct scan     - --as <path> [...]         stdin content scanned as <path>
sct focus    <path> <name|heading> [--ref REF] [--body] [--lines N] [--json]
sct focus    <path>::<name>[@REF]        the address form, one argument
sct focus    - --as <path> <name>        stdin content, one node
sct search   <dir> <pattern> [--ref REF] [--names] [--type TYPE] [--limit N] [--offset N] [--lines N]
sct search   <dir> <pattern> --names --decorator RE   one row per structure, decorators on the row
sct diff     <refA> [<refB>] [--repo DIR] [--path PATH] [--no-merge-base] [--review]
sct surface  <package-dir> [--ref REF] [--against REF] [--part ID]
sct overlap  <base> <branch>... [--repo DIR] [--path P] [--kind K] [--part ID]
sct callers  <name|file> [--dir DIR] [--ref REF]
sct resolve  <path:line | path::name> --from REF --to REF [--repo DIR]
sct divergence <dir> [--max-findings N]
sct history  <path::name | path:line> [--ref REF] [--repo DIR]
sct <command> --help                             the full help; --json on every command but <dir> and divergence, --ascii anywhere
```

`sct <command> --help` carries each command's full description; the text
there, the MCP tool descriptions and this table are generated from one
source in `capabilities.py`, and a test keeps them in agreement.

If the bin directory is not on the agent's PATH, every tool description
carries the absolute fallback, `"<python>" -m scantool.cli`, with the
interpreter the server runs under.

## Addresses: output is valid input

A `focus` answer opens with the node's address, `path::Qualified.name (a-b)`,
and `sct focus path::Qualified.name` is one argument that reads it again.
With `--ref` the address carries it: `path::Qualified.name@origin/main (a-b)`.
From a scan, the file line and a structure under it compose the same
address. Headings are addressed by their ID tag when they have one
(`notes.md::DEV-L17`), else quoted (`notes.md::"Quick Start"`). When a budget
cut something, one trailer names the call that recovers the most:
`next: sct focus <address>`. Search leads and hits are `path:line`.

## The commands

**`sct <dir>`** is orientation: size and language mix, entry points, hot
functions and the call-graph map, in roughly 3 to 5k tokens. It is for the
first look at an unknown codebase, not for targeted questions; the file tree
is the tier below (`scan`). The answer has parts, and line one is its table
of contents: every part's id and line count in body order, then the form
that fetches one part (`sct <dir> --part core`), so a `| head -40` loses
content but not the knowledge of what was lost. The ids are `core`, `entry`,
`structure`, `archetypes`, `architecture`, `deps`, `hot`, `inventory`,
`next` and `git` (plus `divergence` when the peer-divergence audit has
something to say); `--part` takes several, repeated or as a comma list, and
renders them in that order under the same first line, which then also says
`showing …`.

**`sct scan`** is the skeleton of one or more files with `path:line` for
every structure. `--depth quick` is headers only; `--budget N` caps the
answer at roughly N tokens and degrades the least salient functions first.
`-` reads paths from stdin, and `- --as <path>` scans stdin content as if it
were that path.

`--lines N` (on `<dir>`, `scan`, `focus` and `search`) is the N most
informative lines of the answer, in document order: the coverage and file
lines, every structure row and its decorator lines first, then the skeleton,
gist and verbatim `N | text` lines until the budget is spent (a cut block
stops where the budget ends), and one trailer, `… +K lines (--lines N)`,
saying how many lines were cut. Where `| head -N` stops inside a skeleton and
says nothing, this keeps the rows; a `focus --lines N` is the header, the
outline rows and as much body as fits. An answer shorter than N is
unchanged; `--json` ignores it.

**`sct focus`** reads one function, class, method or heading verbatim with
line numbers, the rest of the file as a one-level outline. Names resolve in
three tiers: exact match, qualified path (`ClassA.method`, works for
markdown headings too), then case-insensitive substring; an ambiguous name
returns the qualified candidate list instead of guessing. `--body` prints
the header and the node's numbered lines alone, no outline and no parent
context (what `grep "^ +[0-9]+ |"` over the full answer used to extract).

**`sct search`** finds a regex in a directory and returns each hit with its
enclosing function, class or section, plus leads: names called in the hits
that are defined elsewhere, with their location. `--names` searches
structure names instead of content; `--type` filters by structure type.
`--decorator RE`, with `--names`, keeps only structures with a decorator
matching the regex and answers as a table: one row per structure with its
decorators on the row (`- create_item (item: Item) -> dict @18 [async]
@router.post("/items")`), so a route table is one row per route.

**`sct diff`** is the structural diff between two refs, or one ref and the
working tree: per file, `+` added, `~` changed (`signature: old → new`,
`value: old → new`, or `body: N code / M doc lines`), `=` renamed (paired by
identical body; unchanged members of a renamed class follow it as a count),
`-` removed; three or more functions with the same signature delta fold into
one row; new files as skeletons. Two refs compare against their merge-base by
default and say so in a note (`--no-merge-base` compares the tips). The
coverage line counts files changed without structural rows and names the
reason for each. `--review` appends the peer-divergence section for the
changed functions.

**`sct surface`** is the public surface of a package: every exported name
with its signature, how it is exported (`__all__`, a lazy-import table, a
re-export, `TYPE_CHECKING`) and where it is defined after following the
re-exports, with members inherited from bases inside the package marked.
`--against REF` prints the surface diff; the header states the direction
and names the diff's parts (`added`, `changed`, `moved`, `removed`) with
their line counts, and `--part ID` prints one part alone.

**`sct overlap`** takes N branches against one base, each at its own
merge-base: structures touched by two or more branches (as addresses), new
names introduced independently by two or more branches, commits two branches
share beyond the base (a stack, so their overlap is expected), and per branch
whether it is already in the base and by which criterion (ancestor,
patch-equivalent, tree-equal; patch-equivalence proves the branch can be
deleted, not that its content is in the current tree). It ends with a
merge-order hint, not a verdict. The first line names the report's parts
(`branches`, `history`, `shared`, `colliding`, `order`) with their line
counts, so a `| head -N` cut still says what lies below it; `--part ID`
(a comma list or repeated) prints only those parts after the same first
line.

**`sct callers`** lists the actual call sites of a function or method across
a directory, each with its enclosing function and `path:line`, with the
definitions first. Mentions in docstrings, comments and strings are not
calls and never appear. Given a file instead of a name, it lists the files
that import it with the import line, from the same statically resolved
import graph as the preview's `used by`.

**`sct resolve`** translates `path:line` or `path::name` from one ref to
another: the enclosing structure with its start and end at `--from`, and
where it is at `--to`, renamed with an identical body, or gone with the
nearest names.

**`sct divergence`** audits a directory for peer divergence: functions that
break a call pattern their siblings follow (peers calling X also call Y,
this one does not). The gate is self-levelling against the corpus's own
distribution, so a consistent codebase prints nothing. A finding is a place
to read, never a verdict.

**`sct history`** lists the commits that changed one structure, by address
or by `path:line`.

## Reading at a git ref

`--ref REF` reads at a git ref (branch, tag, SHA) without a checkout: a file
or one node through `git show`, a directory or a search through `git archive`
into a temporary directory, with every path in the answer written the way
you typed it and `@REF` at the end of the coverage line (in JSON,
`coverage.ref`).

## Output forms

`--json` is available on every command but `<dir>` and `divergence`, and the
JSON form is frozen by the same golden tests as the tree form. `--ascii`
replaces the box-drawing and ellipsis glyphs anywhere.
