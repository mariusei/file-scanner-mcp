"""FastMCP server with file scanning tools."""

import json
import os
import re
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import TextContent

from .code_health import analyze_health
from .code_map import CodeMap
from .connectivity import connectivity_tail
from .consensus import DivergenceConfig, find_divergences, format_divergences
from .content_search import find_leads, format_hits, hits_to_json, search_content
from .delta import FULL_DETAIL, GIST_DETAIL, ScanMemory, apply_node_delta, format_age
from .directory_formatter import DirectoryFormatter, coverage_dict, format_coverage
from .focus import format_focus
from .formatter import (
    TreeFormatter,
    file_coverage,
    format_file_coverage,
    next_focus,
    structures_to_json,
)
from .git_signals import (
    collect_git_signals,
    file_churn,
    format_activity,
    recent_line_edits,
    repo_root,
)
from .languages import StructureNode, is_file_info_stub
from .languages.models import Sweep
from .launcher import ensure_launcher, shell_hint, shell_instructions
from .preview import preview_directory as preview_dir_func
from .ref_diff import diff_against_ref
from .scanner import FileScanner

# Injected into context at session start even when tools are deferred behind
# ToolSearch. Clients cap this text (measured ~2 047 characters in one; the
# rest is silently gone), so the whole block stays under 2 000 characters:
# shell first, every command named, parameter hints in the tool descriptions.
INSTRUCTIONS_CAP = 2000
SERVER_INSTRUCTIONS = """\
READ CODE THROUGH sct IN YOUR SHELL. When a Bash step would read or search \
source with cat, head, sed -n, grep, find, ls or git show, run the sct form \
instead: it returns structure (functions, classes, headings, path:line; code, \
markdown, HTML, SQL, config) in one command, and it fits inside && chains and pipes. A rule to work through the shell is satisfied \
by sct: sct IS the shell.

{shell}

MCP TOOLS, the same reader for clients without a shell or when a call needs \
JSON; parameters in each description: search_structures, scan_directory, \
scan_file (focus= reads one node), scan_diff, preview_directory, \
find_divergence, list_directories, scan_file_content.
"""

mcp = FastMCP(
    "File Scanner MCP", instructions=SERVER_INSTRUCTIONS.format(shell=shell_instructions())
)

# Global scanner and formatter instances
scanner = FileScanner()
formatter = TreeFormatter()
dir_formatter = DirectoryFormatter()

# Session-scoped scan memory for delta mode — lives as long as the server
scan_memory = ScanMemory()


def _next_focus_trailer(file_path: str, structures: list[StructureNode]) -> str:
    """One line, only when the budget cut something: the call that reads the
    largest cut node in full, as an address the shell accepts back."""
    name = next_focus(structures)
    return f"\nnext: sct focus {file_path}::{name}" if name else ""


def _budget_for(budget: int | None, depth: str | None) -> int | None:
    """An explicit budget wins; otherwise depth names one of three tiers."""
    if budget is None and depth is not None:
        return {"quick": 300, "normal": 1500, "deep": None}.get(depth)
    return budget


def _git_activity_section(directory: str) -> str:
    """Git activity for preview output; "" outside git repos (signals are
    optional — output without git must look exactly like before)."""
    signals = collect_git_signals(directory)
    if signals is None:
        return ""
    return format_activity(signals)


def _connectivity_note(file_path: str) -> str:
    """Self-levelling connectivity tail for a scanned file (server layer): candidate
    dead/orphan/drift across the whole corpus, silent when clean. Never raises —
    a connectivity hiccup must not affect the scan itself."""
    try:
        root = repo_root(file_path)
        if not root:
            return ""
        return connectivity_tail(root, file_path)
    except Exception:
        return ""


def _without_file_info(structures: list[StructureNode] | None) -> list[StructureNode] | None:
    """Drop the file-info record from a parsed file. A bare stub (an unsupported
    file, nothing but the record) stays, so the file is still listed."""
    if structures is None or is_file_info_stub(structures):
        return structures
    return [node for node in structures if node.type != "file-info"]


def _annotate_churn(results: dict, directory: str) -> None:
    """Inject per-file churn into file-info metadata; no-op without git."""
    signals = collect_git_signals(directory)
    if signals is None:
        return
    for file_str, structures in results.items():
        if not structures or structures[0].type != "file-info":
            continue
        if structures[0].file_metadata is None:
            continue
        count = signals.churn.get(os.path.relpath(file_str, directory))
        if count:
            structures[0].file_metadata["churn_90d"] = count


@mcp.tool(
    tags={"exploration", "overview", "analysis", "primary"},
    description="Deep architecture analysis - entry points, hot functions, call graph, git activity (RICH output ~3-5k tokens; for first-time orientation of an unknown codebase. For targeted questions, search_structures or scan_directory are cheaper first calls)"
    + shell_hint("<dir>"),
)
def preview_directory(
    directory: str,
    depth: str = "deep",
    max_files: int = 10000,
    max_entries: int = 20,
    respect_gitignore: bool = True,
) -> list[TextContent]:
    """
    Intelligent directory preview - analyzes all file types including code, markdown, text, HTML, CSS, SQL, and config files.

    **PRIMARY TOOL - Use this instead of ls/find/grep for project exploration!**

    This tool automatically analyzes code structure, entry points, and architecture.
    Much faster and more informative than manual ls/grep exploration.

    **Depth levels:**
    - "quick": Metadata only (0.5s) - file counts, sizes, types
    - "normal": Architecture analysis (2-5s) - imports, entry points, clusters
    - "deep": Function-level (5-10s) - hot functions, call graph, centrality [DEFAULT]

    **What you get (depth="deep", default):**
    - ✅ Entry Points: main(), if __name__, app instances
    - ✅ Core Files: Most imported files (architectural hubs)
    - ✅ Architecture: Files clustered by role (entry points, core logic, utilities, tests)
    - ✅ Import Graph: How files depend on each other
    - ✅ Hot Functions: Most called functions (critical code paths)
    - ✅ Call Graph: Function-to-function dependencies
    - ✅ Peer Divergence: sites breaking a sibling call pattern (review hint,
         not a bug list) — only shown when a site clearly stands out; silent on
         a consistent codebase
    - ✅ Git Activity: hot files (churn) and co-changed file pairs over the
         last 90 days — works for any repo content (code, docs, config);
         section is silently absent outside git repositories
    - ✅ Noise Filtered: Skips .git/, node_modules/, __pycache__, etc.

    **Why use this instead of ls/grep:**
    - 75% fewer tool calls (one call vs multiple ls/grep/find)
    - Semantic understanding (imports, entry points, hot functions) not just file lists
    - Pre-filtered noise (.git/, node_modules/ already excluded)
    - Instant architecture AND critical function overview
    - Function-level insights ("get_pool() called by 41 functions")

    Args (tiered — most calls need only Common):
        Common:
            directory: Root directory to analyze
            depth: Analysis depth - "quick", "normal", or "deep" [default]
        Cost & slicing:
            max_files: Maximum files to analyze (safety limit, default: 10000)
            max_entries: Maximum entries to show per section (default: 20)
            respect_gitignore: Respect .gitignore patterns (default: True)

    Returns:
        Structured code analysis with entry points, architecture, hot functions, and call graph

    Examples:
        # DEFAULT usage (recommended for most cases):
        preview_directory("./my-project")
        → 5-10s, full analysis with hot functions and call graph

        # Quick metadata only (if >10k files):
        preview_directory("./huge-repo", depth="quick")
        → 0.5s, just file counts and sizes

        # Normal (without hot functions, faster):
        preview_directory("./my-project", depth="normal")
        → 2-5s, architecture and imports only (no function-level)

    Use cases:
        ✅ First time exploring unknown codebase
        ✅ Understanding multi-modality projects (frontend/backend/db)
        ✅ Finding entry points (where does app start?)
        ✅ Identifying core files (architectural hubs)
        ✅ Replacing ls/find/grep workflows

    Performance:
        - Filters noise: .git/, node_modules/, __pycache__, dist/, build/
        - Language-aware: Skips .min.js, .d.ts, .pyc, bundle.js
        - Scales: 486 files analyzed in 4.79s (production FastAPI backend)
    """
    try:
        # Map depth to analysis mode
        if depth == "quick":
            # Metadata only
            result = preview_dir_func(
                directory=directory,
                max_depth=5,
                max_files_hint=max_files,
                show_top_n=max_entries,
                respect_gitignore=respect_gitignore,
            )
            return [TextContent(type="text", text=result + _git_activity_section(directory))]

        elif depth in ("normal", "deep"):
            # Code analysis (Layer 1 for normal, Layer 1+2 for deep)
            enable_layer2 = depth == "deep"

            cm = CodeMap(
                directory=directory,
                respect_gitignore=respect_gitignore,
                max_files=max_files,
                enable_layer2=enable_layer2,
            )

            code_map = cm.analyze()
            output = cm.format_tree(code_map, max_entries=max_entries)

            return [TextContent(type="text", text=output + _git_activity_section(directory))]

        else:
            return [
                TextContent(
                    type="text",
                    text=f"Error: Invalid depth '{depth}'. Use 'quick', 'normal', or 'deep'.",
                )
            ]

    except FileNotFoundError:
        return [TextContent(type="text", text=f"Error: Directory not found: {directory}")]
    except PermissionError:
        return [TextContent(type="text", text=f"Error: Permission denied: {directory}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error analyzing directory: {e}")]


# DEPRECATED: code_map - commented out, use preview_directory() instead
# @mcp.tool(
#     tags={"exploration", "analysis", "overview", "deprecated"},
#     description="[DEPRECATED] Use preview_directory() instead - Same functionality, better UX"
# )
# def code_map(
#     directory: str,
#     respect_gitignore: bool = True,
#     max_files: int = 10000,
#     max_entries: int = 20,
#     enable_layer2: bool = True
# ) -> list[TextContent]:
#     """Deprecated. Use preview_directory() instead."""
#     try:
#         cm = CodeMap(
#             directory=directory,
#             respect_gitignore=respect_gitignore,
#             max_files=max_files,
#             enable_layer2=enable_layer2
#         )
#         result = cm.analyze()
#         output = cm.format_tree(result, max_entries=max_entries)
#         return [TextContent(type="text", text=output)]
#     except Exception as e:
#         return [TextContent(type="text", text=f"Error: {e}")]


@mcp.tool(
    tags={"exploration", "navigation", "directories"},
    description="List directory tree structure (folders only, no files) - USE THIS to see folder hierarchy"
    + shell_hint("--help"),
)
def list_directories(
    directory: str, max_depth: int | None = 3, respect_gitignore: bool = True
) -> list[TextContent]:
    """
    List directory tree showing only folders (no files).

    Displays hierarchical folder structure as a tree, perfect for understanding
    project organization without file clutter.

    Args (tiered — most calls need only Common):
        Common:
            directory: Root directory to list
        Cost & slicing:
            max_depth: Maximum depth to traverse (default: 3). Exists on this
                tool only; the scanners take pattern= instead
            respect_gitignore: Respect .gitignore patterns (default: True)

    Returns:
        Tree structure showing only directories

    Examples:
        # Show directory structure 3 levels deep
        list_directories("./src")

        # Show all directories (ignoring gitignore)
        list_directories(".", max_depth=5, respect_gitignore=False)
    """
    from pathlib import Path

    from .gitignore import load_gitignore

    try:
        root_path = Path(directory).resolve()
        if not root_path.exists():
            return [TextContent(type="text", text=f"Error: Directory not found: {directory}")]
        if not root_path.is_dir():
            return [TextContent(type="text", text=f"Error: Not a directory: {directory}")]

        gitignore = load_gitignore(root_path) if respect_gitignore else None

        def build_tree(path: Path, prefix: str = "", depth: int = 0) -> list[str]:
            """Recursively build directory tree."""
            if max_depth is not None and depth >= max_depth:
                return []

            lines = []
            try:
                # Get all subdirectories
                all_dirs = [e for e in path.iterdir() if e.is_dir()]

                # Filter out gitignored directories
                entries = []
                for entry in all_dirs:
                    if gitignore:
                        rel_path = str(entry.relative_to(root_path))
                        if gitignore.matches(rel_path, is_dir=True):
                            continue
                    entries.append(entry)

                # Sort after filtering
                entries = sorted(entries, key=lambda x: x.name.lower())

                for i, entry in enumerate(entries):
                    is_last = i == len(entries) - 1
                    connector = "└─ " if is_last else "├─ "
                    extension = "   " if is_last else "│  "

                    lines.append(f"{prefix}{connector}{entry.name}/")

                    # Recurse into subdirectories
                    sub_lines = build_tree(entry, prefix + extension, depth + 1)
                    lines.extend(sub_lines)

            except PermissionError:
                pass

            return lines

        # Build tree starting from root
        result_lines = [f"{root_path}/"]
        result_lines.extend(build_tree(root_path))

        return [TextContent(type="text", text="\n".join(result_lines))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error listing directories: {e}")]


@mcp.tool(
    tags={"remote", "http", "content"},
    description="Scan file content directly - USE THIS for remote files, GitHub, APIs, a git blob or stdin instead of saving to disk first. Same budget/depth and focus='name' as scan_file"
    + shell_hint("scan - --as <path>", "focus - --as <path> <name>"),
)
def scan_file_content(
    content: str,
    filename: str,
    focus: str | None = None,
    show_signatures: bool = True,
    show_decorators: bool = True,
    show_docstrings: bool = True,
    show_complexity: bool = False,
    condense: bool = True,
    budget: int | None = None,
    depth: str | None = None,
    mode: str = "balanced",
    include_metadata: bool = True,
    output_format: str = "tree",
) -> list[TextContent]:
    """
    Scan file content directly without requiring a file path.

    **When to use this vs other tools:**
    - Use scan_file_content() INSTEAD of saving remote content to disk → scan directly
    - Use scan_file_content() for GitHub/API content → no file system needed
    - Use scan_file() INSTEAD for local files → includes full metadata (timestamps, permissions)

    **Recommended for:** HTTP/remote connections, GitHub files, API responses, web content

    Use this when you have file content from remote sources (e.g., GitHub API,
    URLs, or any content not stored locally). The filename parameter is used
    only to determine the language/file type for parsing.

    More efficient than saving to disk first - directly scans provided content.

    Supports: Python, JavaScript, TypeScript, Rust, Go, Java, C/C++, C#, PHP,
    Ruby, SQL, Markdown, Plain Text, and image formats.

    Args (tiered — most calls need only Common):
        Common:
            content: The file content as a string
            filename: Filename (with extension) to determine parser type
            focus: Read ONE node verbatim by name ("query", "ClassA.method",
                a heading or a substring of one), as in scan_file
        Cost & slicing:
            budget: Approximate token cap for code skeletons (None = full)
            depth: "quick" (~300), "normal" (~1500) or "deep" (full) when
                budget is not given
            mode: Saliency weight profile — "balanced" or "active"
            include_metadata: The file-info record (name, size) as first node
                (default: True)
        Semantics & display:
            show_signatures: Include function signatures with types (default: True)
            show_decorators: Include decorators like @property, @staticmethod (default: True)
            show_docstrings: Include first line of docstrings (default: True)
            show_complexity: Show complexity metrics for long/complex functions (default: False)
            condense: Show code as skeletons rather than verbatim excerpts (default: True)
            output_format: Output format - "tree" or "json" (default: "tree")

    Returns:
        Formatted structure output (tree or JSON)

    Example usage:
        # Scan Python code from a string
        scan_file_content(
            content="def hello(): pass",
            filename="example.py"
        )
    """
    try:
        structures = scanner.scan_content(
            content=content,
            filename=filename,
            include_metadata=include_metadata,
            budget=_budget_for(budget, depth),
            mode=mode,
            expand_values=depth == "deep",
        )

        if structures is None:
            supported = ", ".join(scanner.get_supported_extensions())
            return [
                TextContent(
                    type="text",
                    text=f"Error: Unsupported file type. Supported extensions: {supported}",
                )
            ]

        if not structures:
            return [TextContent(type="text", text=f"{filename} (empty file or no structure found)")]

        if focus is not None:
            source_lines = content.split("\n")
            return [
                TextContent(
                    type="text",
                    text=format_focus(filename, structures, source_lines, focus, addressed=True),
                )
            ]
        if output_format == "json":
            document = {
                "coverage": file_coverage(structures),
                **structures_to_json(structures, filename, return_dict=True),
            }
            return [TextContent(type="text", text=json.dumps(document, indent=2))]
        custom_formatter = TreeFormatter(
            show_signatures=show_signatures,
            show_decorators=show_decorators,
            show_docstrings=show_docstrings,
            show_complexity=show_complexity,
            condense=condense,
        )
        text = (
            format_file_coverage(structures) + "\n" + custom_formatter.format(filename, structures)
        )
        return [TextContent(type="text", text=text + _next_focus_trailer(filename, structures))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error scanning content: {e}")]


@mcp.tool(
    tags={"local", "file", "analysis"},
    description="Scan ANY file (code, markdown, text, HTML, config) - structure with condensed code skeletons. USE BEFORE Read. For exploration, pass budget=1500 (or 300 for a quick look) - full depth is rarely needed on the first pass. To READ one function/class/section verbatim afterwards, pass focus='name' (or 'Class.method') instead of guessing line ranges. May append a self-levelling CONNECTIVITY note - candidate dead/orphan/drift across the whole corpus, silent when clean; candidates to look at, not verdicts"
    + shell_hint("scan <path>", "focus <path> <name>"),
)
def scan_file(
    file_path: str,
    focus: str | None = None,
    show_signatures: bool = True,
    show_decorators: bool = True,
    show_docstrings: bool = True,
    show_complexity: bool = False,
    condense: bool = True,
    budget: int | None = None,
    depth: str | None = None,
    delta: bool = True,
    caller: str | None = None,
    mode: str = "balanced",
    include_metadata: bool = True,
    output_format: str = "tree",
) -> list[TextContent]:
    """
    Scan any file and return its structure — works on code, markdown, text, HTML, CSS, SQL, config, and 20+ file types.

    **When to use this vs other tools:**
    - Use scan_file() BEFORE Read → get table of contents with line numbers first
    - Use scan_file() INSTEAD of reading entire file → see structure overview efficiently
    - Use scan_directory() INSTEAD when exploring multiple files → get directory-wide view
    - Use scan_file_content() INSTEAD for remote content → no local file needed

    **Recommended for:** Local files (includes full metadata: timestamps, permissions, size)

    Keyword arguments only: file_path= (not directory). Paths come from a
    scan_directory answer, not from a guess.

    Provides table of contents with line numbers for any file type:
    - Code files: classes, functions, methods, imports
    - Markdown: headings, code blocks, sections
    - Text: sections, structure
    - HTML/CSS: tags, selectors, rules

    The file-info line includes git churn ("churn: N commits/90d") when the
    file is in a git repository — absent otherwise, never an error. Nodes
    additionally carry "[N edits/90d]" labels (git blame projected onto
    current lines, so no hunk drift) when — and only when — the counts
    differ between nodes; a uniform value repeats file churn and is omitted.

    Args (tiered — most calls need only Common):
        Common:
            file_path: Absolute or relative path to the file to scan
            focus: Read ONE node verbatim by name instead of guessing line
                ranges: a function/class/method/heading from a previous scan,
                qualified if needed ("ClassA.method"). Returns the file
                skeleton at depth 1 (parent context) plus the focused node's
                full body with line numbers. Ambiguous name → candidate list
        Cost & slicing:
            budget: Approximate token cap for skeleton content. The least salient
                functions degrade first (full depth → outline → header only), so
                output size becomes predictable for huge files while the most
                important code keeps its depth (default: None = no cap).
                Presets for the exploration funnel — use instead of grep:
                budget=300 ≈ file preview (top functions only), budget=1500 ≈
                compact overview, None = full two-tier detail
            depth: Convenience alias for budget, mirroring preview_directory's
                knob — "quick"≈300, "normal"≈1500, "deep"=full, and only
                "deep" shows module values (constants, tables, __all__)
                whole. budget= is the native lever and wins if both are
                given (default: None)
            delta: Re-scans show only what changed since YOUR previous scan of
                the same file in this session: unchanged file → one line;
                modified file → full structure but code detail only for new or
                changed functions ([new]/[changed] labels, removed ones listed).
                First scan is always full. Only a previous scan_file at equal
                or deeper detail (budget) counts — a scan_directory gist or a
                shallower budget never shortens the answer. Pass delta=False
                for full output (default: True)
            caller: Your own id (an agent or session name). Delta memory is
                kept per caller, so pass the same id on every call; without
                it there is no memory and never a one-liner (default: None)
        Semantics & display:
            mode: Saliency weight profile — "balanced" (default) or "active"
            include_metadata: File size and mtime, git churn and per-node
                "[N edits/90d]" labels (default: True). False for output that
                must not depend on the checkout: the CLI, snapshots, diffs
                (weights actively-edited code higher in skeleton selection)
            condense: Show code as condensed method skeletons (pseudocode without
                line numbers) — every function gets a shallow depth-2 outline, the
                most salient get full depth (default: True; set False for verbatim
                excerpts with line numbers, top-tier nodes only)
            show_signatures: Include function signatures with types (default: True)
            show_decorators: Include decorators like @property, @staticmethod (default: True)
            show_docstrings: Include first line of docstrings (default: True)
            show_complexity: Show complexity metrics for long/complex functions (default: False)
            output_format: Output format - "tree" or "json" (default: "tree")

    Returns:
        Formatted structure output (tree or JSON)

    Example output (token-optimized tree format with entropy-based code excerpts):
        Compact format: @line instead of (start-end), inline docstrings with #
        Every function shows its method as a condensed skeleton: pseudocode
        lines WITHOUT line numbers (control flow + calls + returns; trivial
        statements folded to …); the most salient functions in full depth,
        the rest as depth-2 outlines. Verbatim lines keep "N |" line numbers.

        example.py (3-57)
        - import statements @3
        - DatabaseManager @8 # Manages database connections
          - __init__ (self, connection_string: str) @11
          - connect (self) @15 # Establish database connection
          - query (self, sql: str) -> list @24 # Execute a SQL query
             return self.cursor.execute(sql).fetchall()
        - validate_email (email: str) -> bool @48 # Validate email format
    """
    try:
        # depth is an alias carried over from preview_directory; map it to the
        # native cost lever. Explicit budget always wins; "deep" == full (None).
        budget = _budget_for(budget, depth)

        # The detail level THIS call would show — a previous record may only
        # shorten the answer if the consumer already saw at least this much
        # (a directory gist or shallower budget never suppresses this scan)
        detail = float(budget) if budget is not None else FULL_DETAIL

        # Delta: unchanged since this session's previous scan → one line.
        # Focused reads bypass delta entirely — they request content, not
        # structure changes
        if delta and caller and focus is None and output_format != "json":
            age = scan_memory.file_unchanged(file_path, detail, caller)
            if age is not None:
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"{file_path}: unchanged since last scan "
                            f"({format_age(age)} ago) — structure is identical "
                            f"to the previous response (delta=False for full output)"
                        ),
                    )
                ]

        # Git activity first — recent line edits feed saliency selection
        # (weight 0.15 toward actively-worked nodes) and "[N edits/90d]"
        # labels. Cold files (zero churn) skip the blame call; silently
        # absent without git.
        churn = file_churn(file_path) if include_metadata else None
        line_edits = recent_line_edits(file_path) if churn else None

        structures = scanner.scan_file(
            file_path,
            include_file_metadata=include_metadata,
            budget=budget,
            line_edits=line_edits,
            mode=mode,
            expand_values=depth == "deep",
        )

        if structures is None:
            supported = ", ".join(scanner.get_supported_extensions())
            return [
                TextContent(
                    type="text", text=f"Unsupported file type. Supported extensions: {supported}"
                )
            ]

        if not structures:
            return [
                TextContent(type="text", text=f"{file_path} (empty file or no structure found)")
            ]

        if churn and structures[0].type == "file-info" and structures[0].file_metadata is not None:
            structures[0].file_metadata["churn_90d"] = churn

        if focus is not None:
            source_lines = Path(file_path).read_text(errors="replace").split("\n")
            return [
                TextContent(
                    type="text",
                    text=format_focus(file_path, structures, source_lines, focus, addressed=True),
                )
            ]

        delta_note = ""
        if delta and caller and output_format != "json":
            source_lines = Path(file_path).read_text(errors="replace").split("\n")
            diff = scan_memory.diff_and_record(file_path, structures, source_lines, detail, caller)
            if diff is not None:
                changed, unchanged = apply_node_delta(structures, diff)
                removed = f"; removed: {', '.join(diff.removed)}" if diff.removed else ""
                delta_note = (
                    f"(delta since last scan: {changed} changed/new, "
                    f"{unchanged} unchanged — code detail only for changed"
                    f"{removed}; delta=False for everything)\n"
                )

        # Format output
        if output_format == "json":
            document = {
                "coverage": file_coverage(structures),
                **structures_to_json(structures, file_path, return_dict=True),
            }
            return [TextContent(type="text", text=json.dumps(document, indent=2))]
        else:
            # Use custom formatter with options
            custom_formatter = TreeFormatter(
                show_signatures=show_signatures,
                show_decorators=show_decorators,
                show_docstrings=show_docstrings,
                show_complexity=show_complexity,
                condense=condense,
            )
            result = (
                format_file_coverage(structures)
                + "\n"
                + delta_note
                + custom_formatter.format(file_path, structures)
                + _next_focus_trailer(file_path, structures)
            )
            result += _connectivity_note(file_path)
            return [TextContent(type="text", text=result)]

    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error scanning file: {e}")]


@mcp.tool(
    tags={"local", "directory", "exploration"},
    description="Scan directory - file tree with one-line gists per file, code health and churn labels (cheap overview, good first call). Replaces Glob/ls for ALL file types"
    + shell_hint("scan <dir>"),
)
def scan_directory(
    directory: str,
    pattern: str = "**/*",
    max_files: int | None = None,
    respect_gitignore: bool = True,
    exclude_patterns: list[str] | None = None,
    delta: bool = True,
    caller: str | None = None,
    mode: str = "balanced",
    depth: str | None = None,
    include_metadata: bool = True,
    output_format: str = "tree",
) -> list[TextContent]:
    """
    Scan directory and show compact overview of all file structures (code, docs, markdown, config, text).

    **When to use this vs other tools:**
    - Use scan_directory() INSTEAD of Glob → shows file tree AND inline code structures
    - Use scan_directory() BEFORE scan_file() or Read → understand codebase organization first
    - Use scan_directory() for exploring unknown directories → get complete overview in one call
    - Use scan_file() INSTEAD for single file details → get full method-level structure

    **Recommended for:** Local codebases and file system exploration

    PRIMARY TOOL FOR CODEBASE EXPLORATION. Shows directory tree with inline
    list of top-level classes/functions for each file. Compact bird's-eye view
    perfect for understanding codebase organization.

    Keyword arguments only: directory= (not directory_path). After a full
    recursive scan (pattern="**/*") do not re-search with glob or grep: the
    output already lists every file. Do not guess file paths; discover them
    here first.

    For detailed view of a specific file (with methods, decorators, docstrings),
    use scan_file() instead.

    ALWAYS shows structures in compact inline format, plus a one-line
    glimpse of each file's most salient function (its condensed gist —
    ~25 tokens per code file, so you rarely need grep to know what a
    file actually does):
    - filename.py (1-100) - ClassName, function_name, AnotherClass
       > main_function: drift = sum(...) ; for t in sorted(txns): ; return …

    Output ends with a CODE HEALTH section when there is something to say:
    - UNREFERENCED: definitions whose name appears nowhere else in the
      scanned files (text-based, language-agnostic; conservative — any
      mention in code, strings, comments or config suppresses the flag;
      decorated/override/entry-point/container definitions are exempt)
    - DUPLICATE: byte-identical definition blocks (whitespace-normalized,
      >=4 lines) repeated across or within files
    File lines carry a "Nx/90d" git churn label inside git repositories.

    Use pattern to control scope:
    - "**/*" = recursive scan all files (default)
    - "*/*" = 1 level deep only
    - "src/**/*.py" = only Python files in src/
    - "**/*.{py,ts}" = Python and TypeScript files

    Respects .gitignore by default (excludes node_modules, .venv, etc.)

    Args (tiered — most calls need only Common):
        Common:
            directory: Directory path to scan
            pattern: Glob pattern (default: "**/*" = recursive all files)
        Cost & slicing:
            max_files: Maximum files to process (default: None = unlimited)
            respect_gitignore: Respect .gitignore exclusions (default: True)
            exclude_patterns: Additional patterns to exclude (gitignore syntax)
            delta: Re-scans aggregate files unchanged since YOUR previous scan
                in this session to a single line — full detail only for changed
                or new files. The CODE HEALTH section always covers everything.
                Pass delta=False for full output (default: True)
            caller: Your own id (an agent or session name). Delta memory is
                kept per caller, so pass the same id on every call; without
                it there is no memory and never a one-liner (default: None)
        Semantics & display:
            mode: Saliency weight profile for the per-file glimpse lines —
                "balanced" (default) or "active" (weights actively-edited
                code higher)
            include_metadata: File size and mtime, git churn and per-node
                "[N edits/90d]" labels (default: True). False for output that
                must not depend on the checkout: the CLI, snapshots, diffs
            depth: Accepted but inert — scan_directory is already the shallow
                bird's-eye tier, so there is no depth axis to set. Passing it
                triggers a one-line usage hint pointing at the right lever
                (pattern for breadth; scan_file/preview_directory for depth)
            output_format: "tree" or "json" (default: "tree")

    Returns:
        Hierarchical tree with compact inline structures

    Examples:
        # Full recursive scan
        scan_directory("./src")

        # Specific file type
        scan_directory("./src", pattern="**/*.py")

        # Shallow scan (1 level)
        scan_directory(".", pattern="*/*")
    """
    try:
        # depth has no analog here — scan_directory is already the shallow tier.
        # Accept it (no crash) but flag it as non-optimal tool use, in-loop.
        depth_note = ""
        if depth is not None:
            depth_note = (
                "Note: scan_directory has no depth setting — it is already the "
                "shallow bird's-eye tier (one-line gists, no deep analysis), so "
                "'depth' was ignored. Narrow breadth with pattern (e.g. '*/*' = "
                "one level); for deeper per-file detail use scan_file(budget=) "
                "or preview_directory(depth=).\n\n"
            )

        sweep = scanner.sweep(
            directory=directory,
            pattern=pattern,
            respect_gitignore=respect_gitignore,
            exclude_patterns=exclude_patterns,
            mode=mode,
            max_files=max_files,
        )
        results = sweep.results
        if depth_note:
            sweep.notes.append(depth_note.strip())
        if max_files is not None and len(results) >= max_files:
            sweep.notes.append(
                f"Note: Limited to first {max_files} files; scanning stopped at the limit"
            )
        if not include_metadata:
            results = {path: _without_file_info(nodes) for path, nodes in results.items()}
            sweep.results = results
        # Every directory answer opens with what was seen and what was left out
        notes = "".join(f"{note}\n" for note in sweep.notes)
        header = notes + format_coverage(sweep) + "\n"

        if not results:
            return [
                TextContent(
                    type="text",
                    text=header + f"No supported files found in {directory} matching {pattern}",
                )
            ]

        if output_format == "json":
            json_results = {}
            for file_path, structures in results.items():
                if structures:
                    json_results[file_path] = structures_to_json(
                        structures, file_path, return_dict=True
                    )
            document = {"coverage": coverage_dict(sweep), "files": json_results}
            return [TextContent(type="text", text=json.dumps(document, indent=2))]
        else:
            if include_metadata:
                _annotate_churn(results, directory)

            # Delta: files unchanged since this session's previous scan are
            # aggregated to one line; full detail only for changed/new files.
            # Health runs on the FULL set regardless — "unreferenced" must
            # see references living in unchanged files.
            unchanged_paths = []
            display_results = results
            if delta and caller:
                for path in results:
                    # Gist-level records: enough to aggregate future directory
                    # scans, but never enough to suppress a scan_file
                    if scan_memory.file_unchanged(path, GIST_DETAIL, caller) is not None:
                        unchanged_paths.append(path)
                    elif results[path] and not is_file_info_stub(results[path]):
                        try:
                            lines = Path(path).read_text(errors="replace").split("\n")
                            scan_memory.diff_and_record(
                                path, results[path], lines, GIST_DETAIL, caller
                            )
                        except OSError:
                            pass
                if unchanged_paths:
                    display_results = {
                        p: s for p, s in results.items() if p not in set(unchanged_paths)
                    }

            if delta and caller and not display_results:
                names = ", ".join(sorted(Path(p).name for p in unchanged_paths))
                return [
                    TextContent(
                        type="text",
                        text=notes
                        + (
                            f"{directory}: all {len(unchanged_paths)} files unchanged "
                            f"since last scan in this session ({names}) — "
                            f"delta=False for full output"
                        ),
                    )
                ]

            # ALWAYS use compact inline format for directory scans
            custom_formatter = DirectoryFormatter(
                include_structures=True,
                flatten_structures=True,  # Always flat for directory overview
                show_metadata=include_metadata,
            )
            result = header + custom_formatter.format(directory, display_results)
            if unchanged_paths:
                names = ", ".join(sorted(Path(p).name for p in unchanged_paths))
                result += (
                    f"\nunchanged since last scan ({len(unchanged_paths)} "
                    f"files): {names} (delta=False for everything)"
                )
            result += analyze_health(results)
            return [TextContent(type="text", text=result)]

    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error scanning directory: {e}")]


@mcp.tool(
    tags={"local", "diff", "review"},
    description="Structural diff against a git ref - which functions are new/changed/removed since HEAD/main/a release, with condensed skeletons. USE THIS INSTEAD of git diff for review and 'what changed' questions"
    + shell_hint("diff <ref>", "diff <refA> <refB>"),
)
def scan_diff(directory: str, ref: str = "HEAD", budget: int | None = 1500) -> list[TextContent]:
    """
    Structural diff of the working tree against a git ref.

    **When to use this vs other tools:**
    - Use scan_diff() INSTEAD of git diff → review-oriented view: WHICH
      functions/classes/sections are new, changed or removed, with their
      condensed method skeletons — not line noise
    - ref="HEAD" (default) shows uncommitted work; ref="main" shows the
      whole branch; ref="HEAD~5" the last five commits

    Per changed file: new/changed nodes carry [new]/[changed] labels and show
    code detail; unchanged nodes keep headers only; removed nodes are
    listed by name. Files changed without structural impact (whitespace,
    comments) are reported as exactly that. Works for any file type —
    markdown diffs show changed sections.

    A PEER DIVERGENCE tail may follow when a changed function breaks a call
    pattern its siblings across the repo follow (e.g. peers calling X also call
    Y, this one doesn't) — a REVIEW HINT to look at, not a verified bug. Peers
    can legitimately differ; adjudicate by reading. Silent when nothing changed
    breaks a strong pattern.

    Args (tiered — most calls need only Common):
        Common:
            directory: Directory inside the git repository to diff
            ref: Git ref to compare the working tree against (default: HEAD)
        Cost & slicing:
            budget: Approximate token cap per file's skeletons (default: 1500)

    Returns:
        Structural diff with per-node change labels
    """
    try:
        return [TextContent(type="text", text=diff_against_ref(directory, ref, budget))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error diffing: {e}")]


@mcp.tool(
    tags={"local", "analysis", "review", "divergence"},
    description="Audit a directory for peer divergence - functions that break a call pattern their siblings across the codebase follow (peers calling X also call Y, this one doesn't). A REVIEW HINT to look at, not a verified bug list. Silent on a consistent codebase. Use to hunt drift, dead/missing connectivity, or misaligned implementations - cheaper and more focused than preview_directory when divergence is all you want"
    + shell_hint("--help"),
)
def find_divergence(
    directory: str,
    respect_gitignore: bool = True,
    max_findings: int = 20,
) -> list[TextContent]:
    """
    Audit a whole directory for peer divergence: sites that break a call pattern
    their siblings across the codebase follow.

    This is a REVIEW HINT, not a verified bug list — peers may legitimately
    differ, so adjudicate by reading. The detector is self-levelling and
    role-conditioned: a consistent codebase yields nothing, and that silence is
    the truthful signal (it does not mean the tool failed).

    Cheaper and more focused than preview_directory when drift is all you want;
    preview_directory shows the same section but only as part of a full
    architecture analysis at depth="deep".

    Args:
        directory: Root directory to audit
        respect_gitignore: Respect .gitignore patterns (default: True)
        max_findings: Cap on the number of findings shown (default: 20)
    """
    try:
        cm = CodeMap(directory, respect_gitignore=respect_gitignore)
        result = cm.analyze()
        if not result.definitions or not result.calls:
            return [
                TextContent(
                    type="text",
                    text=(
                        f"{directory}: no call graph to analyze "
                        f"(peer divergence needs code with cross-function calls)"
                    ),
                )
            ]
        file_clusters = {f: cluster for cluster, files in result.clusters.items() for f in files}
        findings = find_divergences(
            result.definitions,
            result.calls,
            config=DivergenceConfig(TOP_N=max_findings),
            file_clusters=file_clusters,
        )
        return [TextContent(type="text", text=format_divergences(findings))]
    except FileNotFoundError:
        return [TextContent(type="text", text=f"Error: Directory not found: {directory}")]
    except PermissionError:
        return [TextContent(type="text", text=f"Error: Permission denied: {directory}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error analyzing directory: {e}")]


@mcp.tool(
    tags={"local", "search", "filter"},
    description="Search across all file types - BEST FIRST CALL for targeted questions, USE INSTEAD of Grep: content_pattern finds text WITH structural context (enclosing function/class/section) plus leads to definitions; name/type/decorator find structures"
    + shell_hint("search <dir> <pattern>"),
)
def search_structures(
    directory: str,
    type_filter: str | None = None,
    name_pattern: str | None = None,
    has_decorator: str | None = None,
    min_complexity: int | None = None,
    content_pattern: str | None = None,
    include_metadata: bool = True,
    limit: int = 40,
    offset: int = 0,
    output_format: str = "tree",
) -> list[TextContent]:
    """
    Search for structures — or for text in its structural context — across a directory.

    **When to use this vs other tools:**
    - Use content_pattern INSTEAD of Grep → text hits come embedded in their
      structural context: which function/class/section each hit lives in,
      with the node chain and line range — grep gives a location, this gives
      a place in the architecture
    - Use name_pattern/type_filter → find code constructs (classes, functions)
    - Use has_decorator → e.g., all @pytest.fixture or @dataclass

    **Recommended for:** Local codebases - semantic search for classes, functions, methods

    SEMANTIC CODE SEARCH. Understands code structure, not just text matching.
    content_pattern works for ANY file type: a hit in markdown returns its
    section, in SQL its table, in code its enclosing function.

    Args (tiered — most calls need only Common):
        Common:
            directory: Directory to search in
            content_pattern: Regex searched in raw file content (case-insensitive);
                hits are grouped by their containing structure. Combine with
                type_filter/name_pattern to restrict which structures count.
            name_pattern: Regex pattern to match names (e.g., "^test_", ".*Manager$")
            type_filter: Filter by type (e.g., "function", "class", "method")
        Semantics & display:
            has_decorator: Filter by decorator (e.g., "@property", "@staticmethod")
            min_complexity: Minimum complexity (lines) to include
            output_format: Output format - "tree" or "json" (default: "tree")

    Returns:
        Matching structures with line numbers and metadata

    Examples:
        # Where is retry logic? (concept search with structural answers)
        search_structures("./src", content_pattern="retry|backoff")

        # Which functions touch fx_rates?
        search_structures("./src", content_pattern="fx_rates", type_filter="function")

        # Find all classes ending in "Manager"
        search_structures("./src", type_filter="class", name_pattern=".*Manager$")
    """
    try:
        sweep = _search_scope(directory)
        results = sweep.results
        if not include_metadata:
            results = {path: _without_file_info(nodes) for path, nodes in results.items()}
            sweep.results = results
        if content_pattern and "\\|" in content_pattern:
            # grep -r users write BRE; in a Python regex \| is a literal bar
            # and the answer would be a silent "no matches" (§9 item 3)
            content_pattern = content_pattern.replace("\\|", "|")
            sweep.notes.append(
                "note: `\\|` read as alternation (grep BRE); this is a Python regex, "
                "where `|` alternates — write `[|]` for a literal bar"
            )
        header = "".join(f"{note}\n" for note in sweep.notes) + format_coverage(sweep) + "\n"

        if content_pattern is not None:
            found = search_content(results, content_pattern)
            if type_filter:
                found = [h for h in found if h.node_type and type_filter in h.node_type]
            if name_pattern:
                name_re = re.compile(name_pattern)
                found = [h for h in found if h.node_name and name_re.search(h.node_name)]
            leads = find_leads(found, results)
            if output_format == "json":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                **hits_to_json(found, content_pattern, leads, limit, offset),
                                "coverage": coverage_dict(sweep),
                            },
                            indent=2,
                        ),
                    )
                ]
            return [
                TextContent(
                    type="text",
                    text=header + format_hits(found, content_pattern, leads, limit, offset),
                )
            ]

        # Filter structures
        matching = {}
        for file_path, structures in results.items():
            if not structures:
                continue

            filtered = _filter_structures(
                structures,
                type_filter=type_filter,
                name_pattern=name_pattern,
                has_decorator=has_decorator,
                min_complexity=min_complexity,
            )

            if filtered:
                matching[file_path] = filtered

        if not matching:
            text = "No structures found matching the criteria"
            if name_pattern:
                text += _paths_matching(results, name_pattern, directory)
            return [TextContent(type="text", text=header + text)]

        # Format output
        if output_format == "json":
            json_results = {}
            for file_path, structures in matching.items():
                json_results[file_path] = structures_to_json(
                    structures, file_path, return_dict=True
                )
            document = {"coverage": coverage_dict(sweep), "files": json_results}
            return [TextContent(type="text", text=json.dumps(document, indent=2))]
        else:
            outputs = []
            for file_path, structures in sorted(matching.items()):
                outputs.append(formatter.format(file_path, structures))
            result = "\n\n".join(outputs)
            return [TextContent(type="text", text=header + result)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error searching: {e}")]


def _search_scope(path: str) -> Sweep:
    """The files a search covers: a directory swept recursively, or the one
    file named (search reads content by path, so a file is a scope too)."""
    if not os.path.isfile(path):
        return scanner.sweep(path, "**/*")
    structures = scanner.scan_file(path)
    sweep = Sweep(directory=path, results={})
    if structures is None:
        sweep.unsupported[os.path.splitext(path)[1].lower() or "(no ext)"] += 1
    else:
        sweep.results[path] = structures
    return sweep


_PATHS_BY_NAME_CAP = 10


def _paths_matching(results: dict, name_pattern: str, scope: str) -> str:
    """Files and directories in the scope whose own name matches the name
    pattern, spelled from the scope as the caller typed it: a Python name
    that is a module or a package has no structure named after it, and a
    bare "no structures" would hide that it exists."""
    regex = re.compile(name_pattern)
    root = Path(scope).resolve()
    seen: list[str] = []
    for file_path in sorted(results):
        try:
            parts = Path(file_path).resolve().relative_to(root).parts
        except ValueError:
            parts = Path(file_path).parts
        for depth, part in enumerate(parts):
            is_file = depth == len(parts) - 1
            name = Path(part).stem if is_file else part
            if regex.search(name) or (is_file and regex.search(part)):
                shown = os.path.join(scope, *parts[: depth + 1]) + ("" if is_file else os.sep)
                if shown not in seen:
                    seen.append(shown)
    if not seen:
        return ""
    listed = ", ".join(seen[:_PATHS_BY_NAME_CAP])
    more = f", … {len(seen) - _PATHS_BY_NAME_CAP} more" if len(seen) > _PATHS_BY_NAME_CAP else ""
    verb = "matches" if len(seen) == 1 else "match"
    return f"; {len(seen)} path{'' if len(seen) == 1 else 's'} {verb} by name: {listed}{more}"


def _filter_structures(
    structures: list[StructureNode],
    type_filter: str | None = None,
    name_pattern: str | None = None,
    has_decorator: str | None = None,
    min_complexity: int | None = None,
) -> list[StructureNode]:
    """Filter structures based on criteria."""
    results = []

    for node in structures:
        # Check filters
        match = True

        if type_filter and node.type != type_filter:
            match = False

        if name_pattern and not re.search(name_pattern, node.name):
            match = False

        if has_decorator and (
            not node.decorators or not any(has_decorator in d for d in node.decorators)
        ):
            match = False

        if min_complexity and node.complexity and node.complexity.get("lines", 0) < min_complexity:
            match = False

        if match:
            results.append(node)

        # Recurse into children
        if node.children:
            filtered_children = _filter_structures(
                node.children,
                type_filter=type_filter,
                name_pattern=name_pattern,
                has_decorator=has_decorator,
                min_complexity=min_complexity,
            )
            results.extend(filtered_children)

    return results


def main():
    """Main entry point for the MCP server (STDIO mode)."""
    ensure_launcher()
    mcp.run()


def http_main():
    """Entry point for HTTP mode (used by Smithery)."""
    import uvicorn
    from starlette.middleware.cors import CORSMiddleware

    print("Scantool MCP Server starting in HTTP mode...")

    # Setup Starlette app with CORS for cross-origin requests
    app = mcp.http_app()

    # Add CORS middleware for browser-based clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id", "mcp-protocol-version"],
        max_age=86400,
    )

    # Get port from environment variable (Smithery sets this to 8081)
    ensure_launcher()
    port = int(os.environ.get("PORT", 8080))
    print(f"Listening on port {port}")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
