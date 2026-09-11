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
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

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
  sct focus    - --as <path> <name>        stdin content, one node
  sct search   <dir> <pattern> [--ref REF] [--names] [--type TYPE]
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
  search    Text across a directory with structural context: each hit shows
            its enclosing structure, plus leads to where matched names are
            defined. --names matches structure names instead of text. The
            pattern is a Python regex: `a|b` alternates, grep's `\\|` is a
            literal bar. --type filters WHICH structures are reported, not
            where the text is. Truncates at 40 structures and says so.

OPTIONS
  --ref REF      Read at a git ref (branch, tag, SHA) instead of the working
                 tree. No checkout; the repository is found from the path.
                 The coverage line ends with @REF.
  --budget N     Approximate output size in tokens (scan, files only).
  --as PATH      The name stdin content is scanned under (its extension picks
                 the parser; the name appears in the output).
  --json         Same content as JSON (scan, search).
  --ascii        scantool's own glyphs as ASCII; file content is untouched.

CONVENTIONS
  path:line on every structure. Exit 0 ok, 1 not found, 2 usage error.
  Plain text; one fact per line. Errors on stderr.
"""

COMMANDS = ("scan", "focus", "search")
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


class RefError(Exception):
    """Nothing to read at the ref: the message names the ref, the path and
    the repository, so the next call can be corrected. Exit 1."""


def _git(top: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", top, *args], capture_output=True)


def _repo_and_rel(path: str) -> tuple[str, str]:
    """The repository containing path and path's forward-slash form relative
    to its top. The path need not exist in the working tree; it may exist
    only at the ref, so the repository is found from its nearest existing
    ancestor."""
    probe = os.path.abspath(path)
    while not os.path.isdir(probe):
        probe = os.path.dirname(probe)
    result = subprocess.run(
        ["git", "-C", probe, "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RefError(f"{path} is not inside a git repository; --ref needs one")
    top = result.stdout.strip()
    rel = os.path.relpath(os.path.abspath(path), top).replace(os.sep, "/")
    return top, "" if rel == "." else rel


def _spec(ref: str, rel: str) -> str:
    return f"{ref}:{rel}" if rel else ref


def _ref_kind(top: str, ref: str, rel: str) -> str:
    """'blob' or 'tree'; RefError with git's own words when there is neither."""
    result = _git(top, "cat-file", "-t", _spec(ref, rel))
    if result.returncode != 0:
        reason = result.stderr.decode(errors="replace").strip().splitlines()
        raise RefError(
            f"{_spec(ref, rel)} is not in {top} ({reason[0] if reason else 'git failed'})"
        )
    kind = result.stdout.decode().strip()
    return "tree" if kind == "commit" else kind  # the repository root is a tree


def _blob(top: str, ref: str, rel: str) -> str:
    result = _git(top, "show", _spec(ref, rel))
    if result.returncode != 0:
        raise RefError(f"{_spec(ref, rel)} is not in {top}")
    return result.stdout.decode("utf-8", errors="replace")


@contextmanager
def _materialised(top: str, ref: str, rel: str, name: str) -> Iterator[str]:
    """The tree at ref unpacked into a temporary directory under `name`, so
    the directory answer carries the caller's own name for it."""
    result = _git(top, "archive", "--format=tar", _spec(ref, rel))
    if result.returncode != 0:
        raise RefError(f"{_spec(ref, rel)} is not a directory in {top}")
    with tempfile.TemporaryDirectory(prefix="sct-ref-") as scratch:
        target = os.path.join(scratch, name)
        os.mkdir(target)
        with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
            if hasattr(tarfile, "data_filter"):  # 3.11.4+: refuse links and absolute paths
                tar.extractall(target, filter="data")
            else:
                tar.extractall(target)
        yield target


def _relabel(text: str, scratch_path: str, shown: str) -> str:
    """Every spelling of the temporary directory becomes the path the caller
    typed: the tools resolve paths, so the real path is replaced too."""
    for spelling in {os.path.realpath(scratch_path), scratch_path}:
        text = text.replace(spelling, shown).replace(spelling.replace(os.sep, "/"), shown)
    return text


def _stamp_ref(text: str, ref: str, as_json: bool) -> str:
    """The coverage line says which ref was read: `@REF` at its end, or
    coverage.ref in JSON."""
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
        return f"{first} @{ref}{newline}{rest}"
    return text


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
        outputs.append(text)
    return outputs, code


def _scan_at_ref(path: str, args: argparse.Namespace, output_format: str) -> str:
    from . import server

    top, rel = _repo_and_rel(path)
    if _ref_kind(top, args.ref, rel) == "blob":
        text = _text(
            server.scan_file_content(
                content=_blob(top, args.ref, rel),
                filename=path,
                budget=args.budget,
                depth=args.depth,
                include_metadata=False,
                output_format=output_format,
            )
        )
    else:
        shown = path.rstrip("/\\") or path
        with _materialised(top, args.ref, rel, os.path.basename(os.path.abspath(path))) as tree:
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
    return _stamp_ref(text, args.ref, args.json)


def run_focus(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

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
        top, rel = _repo_and_rel(args.path)
        if _ref_kind(top, args.ref, rel) != "blob":
            raise RefError(f"{_spec(args.ref, rel)} is a directory; focus reads one file")
        result = server.scan_file_content(
            content=_blob(top, args.ref, rel),
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
    return [text], 1 if _not_found(text) else 0


def run_search(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

    pattern = {"name_pattern" if args.names else "content_pattern": args.pattern}
    kwargs = dict(
        type_filter=args.type,
        include_metadata=False,
        output_format="json" if args.json else "tree",
        **pattern,
    )
    if args.ref:
        top, rel = _repo_and_rel(args.directory)
        if _ref_kind(top, args.ref, rel) != "tree":
            raise RefError(f"{_spec(args.ref, rel)} is a file; search reads a directory")
        shown = args.directory.rstrip("/\\") or args.directory
        name = os.path.basename(os.path.abspath(args.directory))
        with _materialised(top, args.ref, rel, name) as tree:
            text = _relabel(_text(server.search_structures(directory=tree, **kwargs)), tree, shown)
        text = _stamp_ref(text, args.ref, args.json)
    elif not os.path.isdir(args.directory):
        return [f"sct search: no such directory: {args.directory}"], 1
    else:
        text = _text(server.search_structures(directory=args.directory, **kwargs))
    return [text], 1 if _not_found(text) else 0


RUNNERS: dict[str, Callable[[argparse.Namespace], tuple[list[str], int]]] = {
    "": run_orient,
    "scan": run_scan,
    "focus": run_focus,
    "search": run_search,
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
    focus.add_argument("path", help="file, or `-` with --as for stdin content")
    focus.add_argument("name", help="name, Class.method, heading, or a heading substring")
    stdin_option(focus)
    ref_option(focus)

    search = parser("search", "Text or names across a directory with structural context.", True)
    search.add_argument("directory")
    search.add_argument("pattern", help="Python regex")
    search.add_argument("--names", action="store_true", help="match structure names, not text")
    search.add_argument("--type", metavar="TYPE", help="report only structures of this type")
    ref_option(search)

    return {"": orient, "scan": scan, "focus": focus, "search": search}


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
