"""
FILE: cli.py

PROBLEM:
  Agents read code through their shell. In a 24-day field study scantool
  served 4.5 % of reads; grep, sed line ranges and git show served the rest,
  and the agents rebuilt scan_file by hand (2 525 `grep "^def\\|^class"`).
  The MCP door is the wrong door for a shell-first agent.

SOLUTION:
  `sct`: a second door into the same tool functions the MCP server exposes.
  No second logic, no second formatter — the output contract is the same,
  asked for without the checkout's decorations (include_metadata=False: no
  size, mtime or churn; delta=False: no session memory). Agents live in pipes, so `-` reads a path list from stdin and `- --as <path>` scans
  stdin content under its real name (`git show REF:path | sct scan - --as path`).

SCOPE:
  ✓ <dir> (orientation), scan, focus, search; --json, --ascii; stdin
  ✓ UTF-8 and LF on stdout on every platform
  ✗ git refs, diff, overlap, surface, resolve, callers: later steps
"""

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence

from .gitref import RefError, blob, materialised, ref_kind, repo_and_rel, spec

HELP = """\
sct — structure-first reader for code and documents

  sct <dir>                 orientation: entry points, hot functions, call-graph map
  sct scan <path>...        skeleton: every structure with path:line, condensed excerpts
  sct focus <path> <name>   one function, class or section verbatim with parent context

Reads code (Python, TypeScript, Go, Rust, Java, …) and documents (Markdown,
HTML, CSS, SQL, config) as STRUCTURE — functions, classes, headings,
sections, signatures, call relations — with path:line on everything. Ask by
name, heading or question; never by line number.

USAGE
  sct <dir>
  sct scan     <path>... [--ref REF] [--budget N] [--depth quick|normal|deep]
  sct scan     - [...]                     paths from stdin, one per line
  sct scan     - --as <path> [...]         stdin content scanned as <path>
  sct focus    <path> <name|heading> [--ref REF]
  sct focus    <path>::<name>[@REF]        the address form, one argument
  sct focus    - --as <path> <name>        stdin content, one node
  sct search   <dir> <pattern> [--ref REF] [--names] [--type TYPE] [--limit N] [--offset N]
  sct diff     <refA> [<refB>] [--repo DIR] [--path PATH] [--no-merge-base]
  sct surface  <package-dir> [--ref REF] [--against REF]
  sct overlap  <base> <branch>... [--repo DIR]
  sct callers  <name> [--dir DIR] [--ref REF]
  sct resolve  <path:line | path::name> --from REF --to REF [--repo DIR]
  sct <command> --help
  any command: --json, --ascii

COMMANDS
  <dir>     No command on a directory = orientation: size and language mix,
            entry points, hot functions, the call-graph map. ~3–5k tokens.
            The file tree is the tier below (scan).
  scan      Skeleton of files or a directory: every structure with path:line,
            signature or title, condensed excerpt within the budget.
            Directory → tree with one-line gists. --depth quick ≈ 300
            tokens/file, normal ≈ 1500, deep = everything (files only).
            Elided content is marked ⟨…⟩ +N; ask with focus to see it.
  focus     One structure verbatim with parent context. Name, qualified name
            (Class.method), heading, or a substring of a heading. Several
            matches → the list, exit 1. None → the top-level names, exit 1.
            Answers open with the node's address, `path::Qualified.name (a-b)`.
  search    Text across a directory with structural context: each hit shows
            its enclosing structure, plus leads to where matched names are
            defined; when no lead exists it says so. --names matches
            structure names instead of text. The pattern is a Python regex;
            grep's `\\|` is read as alternation with a note. --type filters
            WHICH structures are reported, not where the text is. Files come
            in path order; 40 structures per page, --limit/--offset for the
            rest, and the page is stated.
  diff      Structural diff between refs. One ref = that ref vs the working
            tree. Two refs = A...B against their merge-base by default
            (--no-merge-base compares the tips; a note says which). Per
            file: + added, ~ changed (signature: old → new; or body: N code
            / M doc lines), = renamed (paired by identical body; children
            follow a renamed class), - removed; identical signature deltas
            in 3+ functions fold into one row; new files as skeletons. The
            coverage line counts files changed without structural rows and
            names the reason for each.
  surface   The public surface of a Python package at a ref: every exported
            name with its signature, how it is exported (__all__, lazy table,
            re-export, TYPE_CHECKING) and where it is defined after following
            re-exports; inherited members marked. --against REF prints the
            surface diff; the header states the direction (A → B).
  overlap   N branches against one base, each at its own merge-base:
            structures touched by 2+ branches, new names introduced
            independently by 2+ branches, commits two branches share (a
            stack: overlap between them is expected), and per branch whether
            it is already in the base and by which criterion (ancestor /
            patch-equivalent / tree-equal; patch-equivalence proves it can be
            deleted, not that its content is in the current tree). Ends with
            a merge-order hint, not a verdict.
  callers   Actual call sites of a function or method (not docstring
            mentions), each with its enclosing function and path:line,
            across the directory; where the name is defined comes first.
  resolve   Translate path:line or path::name from one ref to another: the
            enclosing structure with start AND end at --from, where it is at
            --to (same place, renamed with an identical body), or that it is
            gone, with the nearest names.

OPTIONS
  --ref REF      Read at a git ref (branch, tag, SHA) instead of the working
                 tree. No checkout; the repository is found from the path.
                 The coverage line ends with @REF.
  --repo DIR     Repository for diff, overlap and resolve (default: the one
                 the current directory is inside; required when it is not).
  --dir DIR      Directory callers scans (default: the current directory).
  --path PATH    Restrict diff to a file or directory, relative to the repo.
  --budget N     Approximate output size in tokens (scan, files only).
  --as PATH      The name stdin content is scanned under (its extension picks
                 the parser; the name appears in the output).
  --json         Same content as JSON (scan, search).
  --ascii        scantool's own glyphs as ASCII; file content is untouched.

CONVENTIONS
  Addresses: <file line>::<Qualified.name> — the file line of a scan and a
  structure under it compose the address focus accepts; in a directory
  listing, prefix the entry with the directory you scanned. Headings are
  addressed by their ID tag ([DEV-L17] → path::DEV-L17), else quoted
  (path::"Quick Start"). @REF at the end of the name carries the ref.
  Search leads and hits are path:line. Exit 0 ok, 1 not found, 2 usage
  error. Plain text; one fact per line. Errors on stderr.
"""

COMMANDS = ("scan", "focus", "search", "diff", "surface", "overlap", "callers", "resolve")
STDIN = "-"

# The glyphs scantool's own formatters emit; --ascii maps these and nothing
# else, so non-ASCII text from the scanned files survives.
GLYPHS = {
    "⟨": "<",
    "⟩": ">",
    "→": "->",
    "←": "<-",
    "⇒": "=>",
    "…": "...",
    "—": "--",
    "━": "-",
    "─": "-",
    "═": "=",
    "│": "|",
    "├": "|-",
    "└": "`-",
    "✓": "ok",
    "✗": "x",
    "×": "x",
    "≈": "~",
    "≥": ">=",
    "−": "-",
    "·": ".",
    "⚠": "!",
    "✅": "",
    "💡": "",
    "🏛": "",
    "🔧": "",
    "🚀": "",
    "📦": "",
    "💤": "",
    "📄": "",
    "📂": "",
    "\ufe0f": "",  # variation selector after the emoji above
}

# Texts the tool functions return instead of raising when there is nothing
# to show. They stay on stdout (the ambiguity list IS the answer) with exit 1.
NOT_FOUND_PREFIXES = (
    "Error",
    "Unsupported file type",
    "No content matches",
    "No structures found",
    "No supported files",
    "focus '",
)


class UsageError(Exception):
    """A usage error found after argparse: printed like argparse's, exit 2."""


def _relabel(text: str, scratch_path: str, shown: str) -> str:
    """Every spelling of the temporary directory becomes the path the caller
    typed: the tools resolve paths, so the real path is replaced too."""
    for spelling in {os.path.realpath(scratch_path), scratch_path}:
        text = text.replace(spelling, shown).replace(spelling.replace(os.sep, "/"), shown)
    return text


def _stamp_ref(text: str, ref: str, as_json: bool) -> str:
    """Every address the answer prints carries the ref it was read at: `@REF`
    on the coverage line, in a focus header before the range, on the
    `next:` trailer; coverage.ref in JSON."""
    if as_json:
        try:
            document = json.loads(text)
        except ValueError:
            return text
        if isinstance(document, dict) and isinstance(document.get("coverage"), dict):
            document["coverage"]["ref"] = ref
        return json.dumps(document, indent=2)
    first, newline, rest = text.partition("\n")
    if first.startswith("<") and first.endswith(">"):
        first = f"{first} @{ref}"
    elif "::" in first and first.endswith(")"):
        name, _, span = first.rpartition(" (")
        first = f"{name}@{ref} ({span}"
    head, sep, trailer = rest.rpartition("\nnext: sct focus ")
    if sep and "\n" not in trailer:
        rest = f"{head}{sep}{trailer}@{ref}"
    return f"{first}{newline}{rest}"


def _typed_path_header(text: str, path: str) -> str:
    """The file line of an answer names the path the caller typed, so
    `<file line>::<name>` is an address the caller can run. The formatter
    prints the base name (the frozen contract); the shell door widens it."""
    typed = path.rstrip("/\\") or path
    base = os.path.basename(typed)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(("<", "note: ", "Note: ")):
            continue
        if base and (line.startswith(base + " (") or line.startswith(base + "/ (")):
            lines[i] = typed + line[len(base) :]
        break
    return "\n".join(lines)


def _split_address(address: str) -> tuple[str, str, str | None]:
    """`path::name[@ref]` -> (path, name, ref). A quoted name keeps its quotes
    and any `@` inside them; the ref is what follows the closing quote or
    the last `@`."""
    path, sep, name = address.rpartition("::")
    if not sep:
        raise UsageError("sct focus: give <path> <name>, or one address path::Qualified.name[@ref]")
    ref = None
    if name.startswith('"'):
        closing = name.find('"', 1)
        if closing > 0 and name[closing + 1 :].startswith("@"):
            ref = name[closing + 2 :]
            name = name[: closing + 1]
    elif "@" in name:
        name, _, ref = name.rpartition("@")
    return path, name, ref or None


def to_ascii(text: str) -> str:
    return "".join(GLYPHS.get(char, char) for char in text)


def _text(result) -> str:
    return "".join(part.text for part in result)


def _not_found(text: str) -> bool:
    """Whether the answer, after its coverage line and any notes, says there
    was nothing to show."""
    body = text
    while body.startswith(("<", "note: ", "Note: ")):
        body = body.partition("\n")[2]
    return body.startswith(NOT_FOUND_PREFIXES)


def _stdin_paths(command: str) -> list[str]:
    paths = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    if not paths:
        raise UsageError(f"sct {command}: `-` given but stdin holds no paths")
    return paths


def _stdin_content(command: str, as_path: str | None, paths: Sequence[str]) -> str:
    """The content form: exactly one path, `-`, plus --as naming it."""
    if list(paths) != [STDIN]:
        raise UsageError(f"sct {command}: --as goes with `-` as the only path")
    if not as_path:
        raise UsageError(f"sct {command}: --as PATH is required to scan stdin content")
    return sys.stdin.read()


def run_orient(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

    if not os.path.isdir(args.directory):
        return [f"sct: no such directory: {args.directory}"], 1
    return [_text(server.preview_directory(directory=args.directory))], 0


def run_scan(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

    output_format = "json" if args.json else "tree"
    if args.as_path and args.ref:
        raise UsageError(
            "sct scan: --as scans stdin content; --ref reads the repository. One or the other."
        )
    if args.as_path:
        content = _stdin_content("scan", args.as_path, args.path)
        text = _text(
            server.scan_file_content(
                content=content,
                filename=args.as_path,
                budget=args.budget,
                depth=args.depth,
                include_metadata=False,
                output_format=output_format,
            )
        )
        return [text], 1 if _not_found(text) else 0

    paths = [
        p for given in args.path for p in (_stdin_paths("scan") if given == STDIN else [given])
    ]
    outputs, code = [], 0
    for path in paths:
        if args.ref:
            text = _scan_at_ref(path, args, output_format)
            if _not_found(text):
                code = 1
            outputs.append(text)
            continue
        if os.path.isdir(path):
            result = server.scan_directory(
                directory=path, delta=False, include_metadata=False, output_format=output_format
            )
        elif os.path.isfile(path):
            result = server.scan_file(
                file_path=path,
                budget=args.budget,
                depth=args.depth,
                delta=False,
                include_metadata=False,
                output_format=output_format,
            )
        else:
            outputs.append(f"sct scan: no such file or directory: {path}")
            code = 1
            continue
        text = _text(result)
        if _not_found(text):
            code = 1
        outputs.append(text if args.json else _typed_path_header(text, path))
    return outputs, code


def _scan_at_ref(path: str, args: argparse.Namespace, output_format: str) -> str:
    from . import server

    top, rel = repo_and_rel(path)
    if ref_kind(top, args.ref, rel) == "blob":
        text = _text(
            server.scan_file_content(
                content=blob(top, args.ref, rel),
                filename=path,
                budget=args.budget,
                depth=args.depth,
                include_metadata=False,
                output_format=output_format,
            )
        )
    else:
        shown = path.rstrip("/\\") or path
        with materialised(top, args.ref, rel, os.path.basename(os.path.abspath(path))) as tree:
            text = _relabel(
                _text(
                    server.scan_directory(
                        directory=tree,
                        delta=False,
                        include_metadata=False,
                        output_format=output_format,
                    )
                ),
                tree,
                shown,
            )
    if not args.json:
        text = _typed_path_header(text, path)
    return _stamp_ref(text, args.ref, args.json)


def run_focus(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

    if args.name is None:
        args.path, args.name, ref = _split_address(args.path)
        if ref and args.ref and ref != args.ref:
            raise UsageError(f"sct focus: the address says @{ref}, --ref says {args.ref}")
        args.ref = args.ref or ref
    if args.as_path and args.ref:
        raise UsageError(
            "sct focus: --as reads stdin content; --ref reads the repository. One or the other."
        )
    if args.as_path or args.path == STDIN:
        content = _stdin_content("focus", args.as_path, [args.path])
        result = server.scan_file_content(
            content=content, filename=args.as_path, focus=args.name, include_metadata=False
        )
    elif args.ref:
        top, rel = repo_and_rel(args.path)
        if ref_kind(top, args.ref, rel) != "blob":
            raise RefError(f"{spec(args.ref, rel)} is a directory; focus reads one file")
        result = server.scan_file_content(
            content=blob(top, args.ref, rel),
            filename=args.path,
            focus=args.name,
            include_metadata=False,
        )
    elif not os.path.isfile(args.path):
        return [f"sct focus: no such file: {args.path}"], 1
    else:
        result = server.scan_file(
            file_path=args.path, focus=args.name, delta=False, include_metadata=False
        )
    text = _text(result)
    if args.ref:
        text = _stamp_ref(text, args.ref, False)
    return [text], 1 if _not_found(text) else 0


def run_search(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

    pattern = {"name_pattern" if args.names else "content_pattern": args.pattern}
    kwargs = dict(
        type_filter=args.type,
        include_metadata=False,
        limit=args.limit,
        offset=args.offset,
        output_format="json" if args.json else "tree",
        **pattern,
    )
    if args.ref:
        top, rel = repo_and_rel(args.directory)
        if ref_kind(top, args.ref, rel) != "tree":
            raise RefError(f"{spec(args.ref, rel)} is a file; search reads a directory")
        shown = args.directory.rstrip("/\\") or args.directory
        name = os.path.basename(os.path.abspath(args.directory))
        with materialised(top, args.ref, rel, name) as tree:
            text = _relabel(_text(server.search_structures(directory=tree, **kwargs)), tree, shown)
        text = _stamp_ref(text, args.ref, args.json)
    elif not os.path.isdir(args.directory):
        return [f"sct search: no such directory: {args.directory}"], 1
    else:
        text = _text(server.search_structures(directory=args.directory, **kwargs))
    return [text], 1 if _not_found(text) else 0


def run_diff(args: argparse.Namespace) -> tuple[list[str], int]:
    from .structural_diff import (
        WORKTREE,
        ahead_behind,
        diff_refs,
        diff_to_json,
        format_diff,
        merge_base,
        repo_top,
        short,
        verify_ref,
    )

    where = args.repo or os.getcwd()
    top = repo_top(where)
    if top is None:
        raise RefError(f"{where} is not inside a git repository; pass --repo DIR")
    side_a, side_b = args.ref_a, args.ref_b or WORKTREE
    for ref in (side_a, side_b):
        if not verify_ref(top, ref):
            raise RefError(f"unknown ref {ref!r} in {top}")
    note = None
    if args.ref_b and not args.no_merge_base:
        base = merge_base(top, side_a, side_b)
        if base and short(top, base) != short(top, side_a):
            ahead, behind = ahead_behind(top, side_a, side_b)
            note = (
                f"note: {side_a} and {side_b} diverged at {short(top, base)}; "
                f"{side_a} is {ahead} ahead, {side_b} is {behind}; comparing "
                f"{short(top, base)} → {side_b} (--no-merge-base compares the tips)"
            )
            side_a = short(top, base)
    result = diff_refs(top, side_a, side_b, args.path)
    result.note = note
    if args.json:
        return [json.dumps(diff_to_json(result), indent=2)], 0
    return [format_diff(result)], 0


def _surface_at(package_dir: str, ref: str | None):
    """The surface of the package as typed, or as it is at ref; paths are
    prefixed with the directory the caller typed, so each row is runnable."""
    from .surface import read_surface

    typed = package_dir.rstrip("/\\") or package_dir
    if ref is None:
        if not os.path.isdir(typed):
            raise RefError(f"{package_dir} is not a directory")
        surface = read_surface(typed)
    else:
        top, rel = repo_and_rel(typed)
        if ref_kind(top, ref, rel) != "tree":
            raise RefError(f"{spec(ref, rel)} is not a directory; surface reads a package")
        with materialised(top, ref, rel, os.path.basename(os.path.abspath(typed))) as tree:
            surface = read_surface(tree)
    parent = os.path.dirname(typed)
    for export in surface.exports:
        if export.path:
            export.path = (
                os.path.join(parent, export.path).replace(os.sep, "/") if parent else export.path
            )
    return surface


def run_surface(args: argparse.Namespace) -> tuple[list[str], int]:
    from .surface import format_surface, format_surface_diff, surface_to_json

    label_a = f"@{args.ref}" if args.ref else "@WORKTREE"
    surface_a = _surface_at(args.package_dir, args.ref)
    if args.against:
        surface_b = _surface_at(args.package_dir, args.against)
        text = format_surface_diff(surface_a, surface_b, label_a, f"@{args.against}")
        if args.json:
            document = {
                "direction": f"{label_a} → @{args.against}",
                "a": surface_to_json(surface_a, label_a),
                "b": surface_to_json(surface_b, f"@{args.against}"),
            }
            return [json.dumps(document, indent=2)], 0
        return [text], 0
    if args.json:
        return [json.dumps(surface_to_json(surface_a, label_a), indent=2)], 0
    text = format_surface(surface_a, label_a)
    return [text], 1 if not surface_a.exports else 0


def run_overlap(args: argparse.Namespace) -> tuple[list[str], int]:
    from .overlap import format_overlap, overlap, overlap_to_json
    from .structural_diff import repo_top, verify_ref

    where = args.repo or os.getcwd()
    top = repo_top(where)
    if top is None:
        raise RefError(f"{where} is not inside a git repository; pass --repo DIR")
    for ref in (args.base, *args.branches):
        if not verify_ref(top, ref):
            raise RefError(f"unknown ref {ref!r} in {top}")
    try:
        result = overlap(top, args.base, args.branches)
    except ValueError as error:
        raise RefError(str(error)) from error
    if args.json:
        return [json.dumps(overlap_to_json(result), indent=2)], 0
    return [format_overlap(result)], 0


def run_callers(args: argparse.Namespace) -> tuple[list[str], int]:
    from .callers import callers_to_json, find_callers, format_callers

    directory = args.dir or "."
    label = f"@{args.ref}" if args.ref else ""
    if args.ref:
        top, rel = repo_and_rel(directory)
        if ref_kind(top, args.ref, rel) != "tree":
            raise RefError(f"{spec(args.ref, rel)} is not a directory")
        with materialised(top, args.ref, rel, os.path.basename(os.path.abspath(directory))) as tree:
            found = find_callers(tree, args.name)
    elif not os.path.isdir(directory):
        raise RefError(f"{directory} is not a directory")
    else:
        found = find_callers(directory, args.name)
    if args.json:
        return [json.dumps(callers_to_json(found, label), indent=2)], 0 if found.sites else 1
    return [format_callers(found, label)], 0 if found.sites else 1


def run_resolve(args: argparse.Namespace) -> tuple[list[str], int]:
    from .resolve import Resolution, format_resolution, resolution_to_json, resolve
    from .structural_diff import repo_top, verify_ref

    address = args.address
    target: str | int
    if "::" in address:
        path, name, ref_in_address = _split_address(address)
        target = name
        if ref_in_address and not args.ref_from:
            args.ref_from = ref_in_address
    else:
        path, sep, line = address.rpartition(":")
        if not sep or not line.isdigit():
            raise UsageError("sct resolve: give path:line or path::name")
        target = int(line)
    if not args.ref_from:
        raise UsageError("sct resolve: --from REF is required (or an address carrying @REF)")
    top = repo_top(args.repo or os.path.dirname(os.path.abspath(path)))
    if top is None:
        raise RefError(f"{path} is not inside a git repository; pass --repo DIR")
    rel = os.path.relpath(os.path.abspath(path), top).replace(os.sep, "/")
    if args.repo:
        rel = path.replace(os.sep, "/")
    for ref in (args.ref_from, args.ref_to):
        if not verify_ref(top, ref):
            raise RefError(f"unknown ref {ref!r} in {top}")
    outcome = resolve(top, rel, target, args.ref_from, args.ref_to)
    if not isinstance(outcome, Resolution):
        return [outcome], 1
    text = (
        json.dumps(resolution_to_json(outcome), indent=2)
        if args.json
        else format_resolution(outcome)
    )
    return [text.replace(rel, path, 1) if path != rel else text], 0 if outcome.target else 1


RUNNERS: dict[str, Callable[[argparse.Namespace], tuple[list[str], int]]] = {
    "": run_orient,
    "scan": run_scan,
    "focus": run_focus,
    "search": run_search,
    "diff": run_diff,
    "surface": run_surface,
    "overlap": run_overlap,
    "callers": run_callers,
    "resolve": run_resolve,
}


def build_parsers() -> dict[str, argparse.ArgumentParser]:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ascii", action="store_true", help="scantool's own glyphs as ASCII")

    def parser(command: str, description: str, json_form: bool) -> argparse.ArgumentParser:
        prog = f"sct {command}".rstrip()
        p = argparse.ArgumentParser(prog=prog, description=description, parents=[common])
        if json_form:
            p.add_argument("--json", action="store_true", help="same content as JSON")
        else:
            p.set_defaults(json=False)
        return p

    def stdin_option(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--as",
            dest="as_path",
            metavar="PATH",
            help="scan stdin content (path `-`) under this name; its extension picks the parser",
        )

    def ref_option(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--ref", metavar="REF", help="read at this git ref (branch, tag, SHA), no checkout"
        )

    orient = parser("", "Orientation: entry points, hot functions, call-graph map.", False)
    orient.add_argument("directory")

    scan = parser("scan", "Skeleton of files or a directory, within a budget.", True)
    scan.add_argument("path", nargs="+", help="file, directory, or `-` for paths on stdin")
    scan.add_argument("--budget", type=int, metavar="N", help="approximate output tokens (files)")
    scan.add_argument("--depth", choices=("quick", "normal", "deep"), help="files only")
    stdin_option(scan)
    ref_option(scan)

    focus = parser("focus", "One structure verbatim with parent context.", False)
    focus.add_argument("path", help="file, an address path::name[@ref], or `-` with --as")
    focus.add_argument(
        "name", nargs="?", help="name, Class.method, heading, or a heading substring"
    )
    stdin_option(focus)
    ref_option(focus)

    search = parser("search", "Text or names across a directory with structural context.", True)
    search.add_argument("directory")
    search.add_argument("pattern", help="Python regex")
    search.add_argument("--names", action="store_true", help="match structure names, not text")
    search.add_argument("--type", metavar="TYPE", help="report only structures of this type")
    search.add_argument("--limit", type=int, default=40, metavar="N", help="structures per page")
    search.add_argument(
        "--offset", type=int, default=0, metavar="N", help="skip this many structures"
    )
    ref_option(search)

    diff = parser("diff", "Structural diff between refs, or a ref and the working tree.", True)
    diff.add_argument("ref_a", metavar="refA")
    diff.add_argument("ref_b", metavar="refB", nargs="?", help="default: the working tree")
    diff.add_argument("--repo", metavar="DIR", help="repository (default: the one cwd is inside)")
    diff.add_argument("--path", metavar="PATH", help="a file or directory, relative to the repo")
    diff.add_argument(
        "--no-merge-base", action="store_true", help="compare the tips, not merge-base...refB"
    )

    surface = parser("surface", "The public surface of a Python package at a ref.", True)
    surface.add_argument("package_dir", metavar="package-dir")
    ref_option(surface)
    surface.add_argument(
        "--against", metavar="REF", help="print the surface diff, this ref on the B side"
    )

    overlap = parser("overlap", "N branches against one base, merge-base per branch.", True)
    overlap.add_argument("base")
    overlap.add_argument("branches", metavar="branch", nargs="+")
    overlap.add_argument(
        "--repo", metavar="DIR", help="repository (default: the one cwd is inside)"
    )

    callers = parser(
        "callers", "Actual call sites of a function or method across a directory.", True
    )
    callers.add_argument("name", help="function, method, or Class.method")
    callers.add_argument("--dir", metavar="DIR", help="directory to scan (default: .)")
    ref_option(callers)

    resolve = parser("resolve", "Translate path:line or path::name from one ref to another.", True)
    resolve.add_argument("address", metavar="path:line | path::name")
    resolve.add_argument(
        "--from", dest="ref_from", metavar="REF", help="the ref the address is from"
    )
    resolve.add_argument(
        "--to", dest="ref_to", metavar="REF", default="WORKTREE", help="default: the working tree"
    )
    resolve.add_argument(
        "--repo", metavar="DIR", help="repository; the path is then relative to it"
    )

    return {
        "": orient,
        "scan": scan,
        "focus": focus,
        "search": search,
        "diff": diff,
        "surface": surface,
        "overlap": overlap,
        "callers": callers,
        "resolve": resolve,
    }


def _configure_streams() -> None:
    """UTF-8 and LF regardless of console code page or platform newline."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def _emit(outputs: list[str], as_json: bool, as_ascii: bool) -> None:
    if as_json:
        documents, messages = [], []
        for output in outputs:
            try:
                documents.append(json.loads(output))
            except ValueError:
                messages.append(output)
        for message in messages:
            sys.stderr.write(message.rstrip("\n") + "\n")
        if documents:
            document = documents[0] if len(documents) == 1 else documents
            sys.stdout.write(json.dumps(document, indent=2) + "\n")
        return
    text = "\n".join(output.rstrip("\n") for output in outputs) + "\n"
    sys.stdout.write(to_ascii(text) if as_ascii else text)


def main(argv: Sequence[str] | None = None) -> int:
    _configure_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(HELP)
        return 0
    if argv[0] == "--version":
        from . import __version__

        sys.stdout.write(f"sct {__version__}\n")
        return 0
    command = argv[0] if argv[0] in COMMANDS else ""
    parser = build_parsers()[command]
    args = parser.parse_args(argv[1:] if command else argv)
    try:
        outputs, code = RUNNERS[command](args)
    except UsageError as error:
        parser.print_usage(sys.stderr)
        sys.stderr.write(f"{error}\n")
        return 2
    except RefError as error:
        sys.stderr.write(f"sct {command}: {error}\n".replace("sct : ", "sct: "))
        return 1
    _emit(outputs, args.json, args.ascii)
    return code


if __name__ == "__main__":
    sys.exit(main())
