"""
FILE: cli.py

PROBLEM:
  Agents read code through their shell. In a 24-day field study scantool
  served 4.5 % of reads; grep, sed line ranges and git show served the rest,
  and the agents rebuilt scan_file by hand (2 525 `grep "^def\\|^class"`).
  The MCP door is the wrong door for a shell-first agent.

SOLUTION:
  `sct`: a second door into the same tool functions the MCP server exposes.
  No second logic, no second formatter — the output contract is the same.
  Only the server-layer decorations that describe the checkout rather than
  the code (file size, mtime, churn, delta memory) are left out.

SCOPE:
  ✓ <dir> (orientation), scan, focus, search; --json, --ascii
  ✓ UTF-8 and LF on stdout on every platform
  ✗ git refs, diff, overlap, surface, resolve, callers: later steps
"""

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Sequence

HELP = """\
sct — structure-first reader for code and documents

Reads code (Python, TypeScript, Go, Rust, Java, …) and documents (Markdown,
HTML, CSS, SQL, config) as STRUCTURE — functions, classes, headings,
sections, signatures, call relations — with path:line on everything. Ask by
name, heading or question; never by line number.

USAGE
  sct <dir>                              orientation: entry points, hot functions, map
  sct scan     <path>... [--budget N] [--depth quick|normal|deep]
  sct focus    <path> <name|heading>
  sct search   <dir> <pattern> [--names] [--type TYPE]
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
            Elided content is marked ⟨…⟩; ask with focus to see it.
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
  --budget N     Approximate output size in tokens (scan, files only).
  --json         Same content as JSON (scan, search).
  --ascii        scantool's own glyphs as ASCII; file content is untouched.

CONVENTIONS
  path:line on every structure. Exit 0 ok, 1 not found, 2 usage error.
  Plain text; one fact per line.
"""

COMMANDS = ("scan", "focus", "search")

# Server-layer decorations that describe the checkout, not the code: the
# file-info line (size, mtime), per-node edit counts, and the directory
# listing's [size, age, churn] suffix.
FILE_INFO_LINE = re.compile(r"^- file-info: .*\n?", re.MULTILINE)
EDIT_TAG = re.compile(r" \[\d+ edits/90d\]")
DIRECTORY_METADATA = re.compile(r" \[\d+(?:\.\d+)?[KMGT]?B(?:, [^\]]*\[ts:\d+\])?(?:, \d+x/90d)?\]")

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


def strip_environment(text: str) -> str:
    return DIRECTORY_METADATA.sub("", EDIT_TAG.sub("", FILE_INFO_LINE.sub("", text)))


def to_ascii(text: str) -> str:
    return "".join(GLYPHS.get(char, char) for char in text)


def drop_file_info(value):
    """Remove file-info nodes from any JSON document the tools return."""
    if isinstance(value, dict):
        return {key: drop_file_info(item) for key, item in value.items()}
    if isinstance(value, list):
        return [
            drop_file_info(item)
            for item in value
            if not (isinstance(item, dict) and item.get("type") == "file-info")
        ]
    return value


def _text(result) -> str:
    return "".join(part.text for part in result)


def _not_found(text: str) -> bool:
    return text.startswith(NOT_FOUND_PREFIXES)


def run_orient(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

    if not os.path.isdir(args.directory):
        return [f"sct: no such directory: {args.directory}"], 1
    return [_text(server.preview_directory(directory=args.directory))], 0


def run_scan(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

    output_format = "json" if args.json else "tree"
    outputs, code = [], 0
    for path in args.path:
        if os.path.isdir(path):
            result = server.scan_directory(directory=path, delta=False, output_format=output_format)
        elif os.path.isfile(path):
            result = server.scan_file(
                file_path=path,
                budget=args.budget,
                depth=args.depth,
                delta=False,
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


def run_focus(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

    if not os.path.isfile(args.path):
        return [f"sct focus: no such file: {args.path}"], 1
    text = _text(server.scan_file(file_path=args.path, focus=args.name, delta=False))
    return [text], 1 if _not_found(text) else 0


def run_search(args: argparse.Namespace) -> tuple[list[str], int]:
    from . import server

    if not os.path.isdir(args.directory):
        return [f"sct search: no such directory: {args.directory}"], 1
    pattern = {"name_pattern" if args.names else "content_pattern": args.pattern}
    text = _text(
        server.search_structures(
            directory=args.directory,
            type_filter=args.type,
            output_format="json" if args.json else "tree",
            **pattern,
        )
    )
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

    orient = parser("", "Orientation: entry points, hot functions, call-graph map.", False)
    orient.add_argument("directory")

    scan = parser("scan", "Skeleton of files or a directory, within a budget.", True)
    scan.add_argument("path", nargs="+")
    scan.add_argument("--budget", type=int, metavar="N", help="approximate output tokens (files)")
    scan.add_argument("--depth", choices=("quick", "normal", "deep"), help="files only")

    focus = parser("focus", "One structure verbatim with parent context.", False)
    focus.add_argument("path")
    focus.add_argument("name", help="name, Class.method, heading, or a heading substring")

    search = parser("search", "Text or names across a directory with structural context.", True)
    search.add_argument("directory")
    search.add_argument("pattern", help="Python regex")
    search.add_argument("--names", action="store_true", help="match structure names, not text")
    search.add_argument("--type", metavar="TYPE", help="report only structures of this type")

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
            sys.stdout.write(json.dumps(drop_file_info(document), indent=2) + "\n")
        return
    text = "\n".join(strip_environment(output).rstrip("\n") for output in outputs) + "\n"
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
    args = build_parsers()[command].parse_args(argv[1:] if command else argv)
    outputs, code = RUNNERS[command](args)
    _emit(outputs, args.json, args.ascii)
    return code


if __name__ == "__main__":
    sys.exit(main())
