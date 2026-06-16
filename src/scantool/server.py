"""FastMCP server with file scanning tools."""

import json
import os
import re
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from mcp.types import TextContent

from .code_health import analyze_health
from .content_search import search_content, format_hits, find_leads
from .delta import ScanMemory, apply_node_delta, format_age
from .ref_diff import diff_against_ref
from .focus import format_focus
from .formatter import TreeFormatter
from .directory_formatter import DirectoryFormatter
from .git_signals import collect_git_signals, file_churn, format_activity, recent_line_edits, repo_root
from .connectivity import connectivity_tail
from .scanner import FileScanner
from .languages import StructureNode
from .preview import preview_directory as preview_dir_func
from .code_map import CodeMap
from .consensus import DivergenceConfig, find_divergences, format_divergences

# Injected into context at session start even when tools are deferred behind
# ToolSearch (clients truncate at ~2KB — most important guidance first).
SERVER_INSTRUCTIONS = """\
Structural scanner for code and documents — use INSTEAD of ls/find/grep/cat \
when exploring projects or understanding files. Handles all file types: code \
(20+ languages), markdown, HTML, CSS, SQL, config.

WHY: returns structure (functions, classes, headings, line numbers) with \
condensed code skeletons instead of raw file contents — far fewer tool calls \
and tokens than ls/find/grep followed by full file reads. Repeat scans are \
delta-aware: unchanged files come back as a one-liner.

PICK THE CHEAPEST TOOL THAT ANSWERS THE QUESTION:
- targeted question ("where is X" / "how does X work") -> search_structures: \
name/type/decorator filters, or content_pattern for text search WITH \
enclosing function/class/section context (replaces grep)
- cheap overview of a directory -> scan_directory: file tree with one-line \
gists, code health and churn labels (replaces ls/glob)
- one file -> scan_file with budget=1500 (300 for a quick look) BEFORE \
reading it; it may append a CONNECTIVITY note (candidate dead/orphan/drift \
across the whole corpus, silent when clean) — a hint to look at, not a verdict
- read ONE function/class/section from the scan -> scan_file with \
focus="name" (or "ClassA.method"): the node verbatim plus parent context. \
Never cat a whole file or guess a sed/Read line range for this — measured \
75% fewer read tokens at equal answer quality (M2c)
- "what changed" / review -> scan_diff against HEAD/main/any ref: \
new/changed/removed functions (replaces git diff)
- hunt drift / misaligned implementations across a codebase -> find_divergence: \
functions that break a call pattern their siblings follow (review hint, silent \
when consistent)
- first-time orientation in an UNKNOWN codebase -> preview_directory: entry \
points, hot functions, call graph (RICH, ~3-5k tokens — not for targeted \
questions)
- folder hierarchy only -> list_directories; remote/unsaved content -> \
scan_file_content

TRIGGER: about to run ls, find, grep or cat to explore? STOP — one of the \
tools above answers it cheaper. About to cat/sed/Read a file to see one \
function or section? STOP — scan_file(focus=...) reads exactly that node. \
Default first call in a directory you have not scanned yet: scan_directory.

After a full recursive scan_directory(pattern="**/*"), do not re-search with \
glob/grep — the output already lists every file.

PARAMETERS (keyword arguments required): directory= (not directory_path); \
scan_file takes file_path=; max_depth exists only on list_directories. Do \
not guess file paths — discover them via scan_directory first.
"""

mcp = FastMCP("File Scanner MCP", instructions=SERVER_INSTRUCTIONS)

# Global scanner and formatter instances
scanner = FileScanner()
formatter = TreeFormatter()
dir_formatter = DirectoryFormatter()

# Session-scoped scan memory for delta mode — lives as long as the server
scan_memory = ScanMemory()


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


def _is_unsupported(structures: list) -> bool:
    """True if the file has no parseable structure — just an 'unsupported'
    file-info stub. Reading such files (e.g. multi-GB binaries) as text is
    pointless and can be ruinously slow, so callers skip them."""
    if len(structures) != 1:
        return False
    node = structures[0]
    return (
        node.type == "file-info"
        and node.file_metadata is not None
        and node.file_metadata.get("unsupported", False)
    )


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
)
def preview_directory(
    directory: str,
    depth: str = "deep",
    max_files: int = 10000,
    max_entries: int = 20,
    respect_gitignore: bool = True
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
                respect_gitignore=respect_gitignore
            )
            return [TextContent(type="text", text=result + _git_activity_section(directory))]

        elif depth in ("normal", "deep"):
            # Code analysis (Layer 1 for normal, Layer 1+2 for deep)
            enable_layer2 = (depth == "deep")

            cm = CodeMap(
                directory=directory,
                respect_gitignore=respect_gitignore,
                max_files=max_files,
                enable_layer2=enable_layer2
            )

            result = cm.analyze()
            output = cm.format_tree(result, max_entries=max_entries)

            return [TextContent(type="text", text=output + _git_activity_section(directory))]

        else:
            return [TextContent(type="text", text=f"Error: Invalid depth '{depth}'. Use 'quick', 'normal', or 'deep'.")]

    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: Directory not found: {directory}")]
    except PermissionError as e:
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
)
def list_directories(
    directory: str,
    max_depth: Optional[int] = 3,
    respect_gitignore: bool = True
) -> list[TextContent]:
    """
    List directory tree showing only folders (no files).

    Displays hierarchical folder structure as a tree, perfect for understanding
    project organization without file clutter.

    Args (tiered — most calls need only Common):
        Common:
            directory: Root directory to list
        Cost & slicing:
            max_depth: Maximum depth to traverse (default: 3)
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
                    is_last = (i == len(entries) - 1)
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
    description="Scan file content directly - USE THIS for remote files, GitHub, APIs instead of saving to disk first"
)
def scan_file_content(
    content: str,
    filename: str,
    show_signatures: bool = True,
    show_decorators: bool = True,
    show_docstrings: bool = True,
    show_complexity: bool = False,
    output_format: str = "tree"
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
        Semantics & display:
            show_signatures: Include function signatures with types (default: True)
            show_decorators: Include decorators like @property, @staticmethod (default: True)
            show_docstrings: Include first line of docstrings (default: True)
            show_complexity: Show complexity metrics for long/complex functions (default: False)
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
            include_metadata=True
        )

        if structures is None:
            supported = ", ".join(scanner.get_supported_extensions())
            return [TextContent(
                type="text",
                text=f"Error: Unsupported file type. Supported extensions: {supported}"
            )]

        if not structures:
            return [TextContent(type="text", text=f"{filename} (empty file or no structure found)")]

        # Format output
        if output_format == "json":
            return [TextContent(type="text", text=_structures_to_json(structures, filename))]
        else:
            # Use custom formatter with options
            custom_formatter = TreeFormatter(
                show_signatures=show_signatures,
                show_decorators=show_decorators,
                show_docstrings=show_docstrings,
                show_complexity=show_complexity
            )
            result = custom_formatter.format(filename, structures)
            return [TextContent(type="text", text=result)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error scanning content: {e}")]


@mcp.tool(
    tags={"local", "file", "analysis"},
    description="Scan ANY file (code, markdown, text, HTML, config) - structure with condensed code skeletons. USE BEFORE Read. For exploration, pass budget=1500 (or 300 for a quick look) - full depth is rarely needed on the first pass. To READ one function/class/section verbatim afterwards, pass focus='name' (or 'Class.method') instead of guessing line ranges. May append a self-levelling CONNECTIVITY note - candidate dead/orphan/drift across the whole corpus, silent when clean; candidates to look at, not verdicts"
)
def scan_file(
    file_path: str,
    focus: Optional[str] = None,
    show_signatures: bool = True,
    show_decorators: bool = True,
    show_docstrings: bool = True,
    show_complexity: bool = False,
    condense: bool = True,
    budget: Optional[int] = None,
    delta: bool = True,
    mode: str = "balanced",
    output_format: str = "tree"
) -> list[TextContent]:
    """
    Scan any file and return its structure — works on code, markdown, text, HTML, CSS, SQL, config, and 20+ file types.

    **When to use this vs other tools:**
    - Use scan_file() BEFORE Read → get table of contents with line numbers first
    - Use scan_file() INSTEAD of reading entire file → see structure overview efficiently
    - Use scan_directory() INSTEAD when exploring multiple files → get directory-wide view
    - Use scan_file_content() INSTEAD for remote content → no local file needed

    **Recommended for:** Local files (includes full metadata: timestamps, permissions, size)

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
            delta: Re-scans show only what changed since YOUR previous scan of
                the same file in this session: unchanged file → one line;
                modified file → full structure but code detail only for new or
                changed functions ([new]/[changed] labels, removed ones listed).
                First scan is always full. Pass delta=False for full output
                (default: True)
        Semantics & display:
            mode: Saliency weight profile — "balanced" (default) or "active"
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
        # Delta: unchanged since this session's previous scan → one line.
        # Focused reads bypass delta entirely — they request content, not
        # structure changes
        if delta and focus is None and output_format != "json":
            age = scan_memory.file_unchanged(file_path)
            if age is not None:
                return [TextContent(type="text", text=(
                    f"{file_path}: unchanged since last scan "
                    f"({format_age(age)} ago) — structure is identical "
                    f"to the previous response (delta=False for full output)"))]

        # Git activity first — recent line edits feed saliency selection
        # (weight 0.15 toward actively-worked nodes) and "[N edits/90d]"
        # labels. Cold files (zero churn) skip the blame call; silently
        # absent without git.
        churn = file_churn(file_path)
        line_edits = recent_line_edits(file_path) if churn else None

        structures = scanner.scan_file(file_path, budget=budget,
                                       line_edits=line_edits, mode=mode)

        if structures is None:
            supported = ", ".join(scanner.get_supported_extensions())
            return [TextContent(type="text", text=f"Unsupported file type. Supported extensions: {supported}")]

        if not structures:
            return [TextContent(type="text", text=f"{file_path} (empty file or no structure found)")]

        if churn and structures[0].type == "file-info" and structures[0].file_metadata is not None:
            structures[0].file_metadata["churn_90d"] = churn

        if focus is not None:
            source_lines = Path(file_path).read_text(errors="replace").split("\n")
            return [TextContent(type="text", text=format_focus(
                file_path, structures, source_lines, focus))]

        delta_note = ""
        if delta and output_format != "json":
            source_lines = Path(file_path).read_text(errors="replace").split("\n")
            diff = scan_memory.diff_and_record(file_path, structures, source_lines)
            if diff is not None:
                changed, unchanged = apply_node_delta(structures, diff)
                removed = f"; removed: {', '.join(diff.removed)}" if diff.removed else ""
                delta_note = (
                    f"(delta since last scan: {changed} changed/new, "
                    f"{unchanged} unchanged — code detail only for changed"
                    f"{removed}; delta=False for everything)\n")

        # Format output
        if output_format == "json":
            return [TextContent(type="text", text=json.dumps(_structures_to_json(structures, file_path), indent=2))]
        else:
            # Use custom formatter with options
            custom_formatter = TreeFormatter(
                show_signatures=show_signatures,
                show_decorators=show_decorators,
                show_docstrings=show_docstrings,
                show_complexity=show_complexity,
                condense=condense
            )
            result = delta_note + custom_formatter.format(file_path, structures)
            result += _connectivity_note(file_path)
            return [TextContent(type="text", text=result)]

    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error scanning file: {e}")]


@mcp.tool(
    tags={"local", "directory", "exploration"},
    description="Scan directory - file tree with one-line gists per file, code health and churn labels (cheap overview, good first call). Replaces Glob/ls for ALL file types"
)
def scan_directory(
    directory: str,
    pattern: str = "**/*",
    max_files: Optional[int] = None,
    respect_gitignore: bool = True,
    exclude_patterns: Optional[list[str]] = None,
    delta: bool = True,
    mode: str = "balanced",
    output_format: str = "tree"
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
        Semantics & display:
            mode: Saliency weight profile for the per-file glimpse lines —
                "balanced" (default) or "active" (weights actively-edited
                code higher)
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
        results = scanner.scan_directory(
            directory=directory,
            pattern=pattern,
            respect_gitignore=respect_gitignore,
            exclude_patterns=exclude_patterns,
            mode=mode
        )

        if not results:
            return [TextContent(type="text", text=f"No supported files found in {directory} matching {pattern}")]

        # Apply max_files limit if specified
        if max_files is not None and len(results) > max_files:
            sorted_items = sorted(results.items())[:max_files]
            results = dict(sorted_items)
            warning = f"Note: Limited to first {max_files} files (out of {len(results)} total)\n\n"
        else:
            warning = ""

        if output_format == "json":
            json_results = {}
            for file_path, structures in results.items():
                if structures:
                    json_results[file_path] = _structures_to_json(structures, file_path, return_dict=True)
            return [TextContent(type="text", text=warning + json.dumps(json_results, indent=2))]
        else:
            _annotate_churn(results, directory)

            # Delta: files unchanged since this session's previous scan are
            # aggregated to one line; full detail only for changed/new files.
            # Health runs on the FULL set regardless — "unreferenced" must
            # see references living in unchanged files.
            unchanged_paths = []
            display_results = results
            if delta:
                for path in results:
                    if scan_memory.file_unchanged(path) is not None:
                        unchanged_paths.append(path)
                    elif results[path] and not _is_unsupported(results[path]):
                        try:
                            lines = Path(path).read_text(errors="replace").split("\n")
                            scan_memory.diff_and_record(path, results[path], lines)
                        except OSError:
                            pass
                if unchanged_paths:
                    display_results = {p: s for p, s in results.items()
                                       if p not in set(unchanged_paths)}

            if delta and not display_results:
                names = ", ".join(sorted(Path(p).name for p in unchanged_paths))
                return [TextContent(type="text", text=(
                    f"{directory}: all {len(unchanged_paths)} files unchanged "
                    f"since last scan in this session ({names}) — "
                    f"delta=False for full output"))]

            # ALWAYS use compact inline format for directory scans
            custom_formatter = DirectoryFormatter(
                include_structures=True,
                flatten_structures=True  # Always flat for directory overview
            )
            result = warning + custom_formatter.format(directory, display_results)
            if unchanged_paths:
                names = ", ".join(sorted(Path(p).name for p in unchanged_paths))
                result += (f"\nunchanged since last scan ({len(unchanged_paths)} "
                           f"files): {names} (delta=False for everything)")
            result += analyze_health(results)
            return [TextContent(type="text", text=result)]

    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error scanning directory: {e}")]


@mcp.tool(
    tags={"local", "diff", "review"},
    description="Structural diff against a git ref - which functions are new/changed/removed since HEAD/main/a release, with condensed skeletons. USE THIS INSTEAD of git diff for review and 'what changed' questions"
)
def scan_diff(
    directory: str,
    ref: str = "HEAD",
    budget: Optional[int] = 1500
) -> list[TextContent]:
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
            return [TextContent(type="text", text=(
                f"{directory}: no call graph to analyze "
                f"(peer divergence needs code with cross-function calls)"))]
        file_clusters = {
            f: cluster for cluster, files in result.clusters.items() for f in files
        }
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
)
def search_structures(
    directory: str,
    type_filter: Optional[str] = None,
    name_pattern: Optional[str] = None,
    has_decorator: Optional[str] = None,
    min_complexity: Optional[int] = None,
    content_pattern: Optional[str] = None,
    output_format: str = "tree"
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
        # Scan directory (recursively scan all files)
        results = scanner.scan_directory(directory, "**/*")

        if content_pattern is not None:
            found = search_content(results, content_pattern)
            if type_filter:
                found = [h for h in found if h.node_type and type_filter in h.node_type]
            if name_pattern:
                name_re = re.compile(name_pattern)
                found = [h for h in found if h.node_name and name_re.search(h.node_name)]
            leads = find_leads(found, results)
            return [TextContent(type="text",
                                text=format_hits(found, content_pattern, leads))]

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
                min_complexity=min_complexity
            )

            if filtered:
                matching[file_path] = filtered

        if not matching:
            return [TextContent(type="text", text="No structures found matching the criteria")]

        # Format output
        if output_format == "json":
            json_results = {}
            for file_path, structures in matching.items():
                json_results[file_path] = _structures_to_json(structures, file_path, return_dict=True)
            return [TextContent(type="text", text=json.dumps(json_results, indent=2))]
        else:
            outputs = []
            for file_path, structures in sorted(matching.items()):
                outputs.append(formatter.format(file_path, structures))
            result = "\n\n".join(outputs)
            return [TextContent(type="text", text=result)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error searching: {e}")]


def _filter_structures(
    structures: list[StructureNode],
    type_filter: Optional[str] = None,
    name_pattern: Optional[str] = None,
    has_decorator: Optional[str] = None,
    min_complexity: Optional[int] = None
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

        if has_decorator and (not node.decorators or not any(has_decorator in d for d in node.decorators)):
            match = False

        if min_complexity and node.complexity:
            if node.complexity.get("lines", 0) < min_complexity:
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
                min_complexity=min_complexity
            )
            results.extend(filtered_children)

    return results


def _structures_to_json(structures: list[StructureNode], file_path: str, return_dict: bool = False):
    """Convert structures to JSON format."""

    def node_to_dict(node: StructureNode) -> dict:
        """Convert a single node to dictionary."""
        result = {
            "type": node.type,
            "name": node.name,
            "start_line": node.start_line,
            "end_line": node.end_line,
        }

        if node.signature:
            result["signature"] = node.signature
        if node.decorators:
            result["decorators"] = node.decorators
        if node.docstring:
            result["docstring"] = node.docstring
        if node.modifiers:
            result["modifiers"] = node.modifiers
        if node.complexity:
            result["complexity"] = node.complexity
        if node.children:
            result["children"] = [node_to_dict(child) for child in node.children]

        return result

    data = {
        "file": file_path,
        "structures": [node_to_dict(s) for s in structures]
    }

    return data if return_dict else json.dumps(data, indent=2)


def main():
    """Main entry point for the MCP server (STDIO mode)."""
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
    port = int(os.environ.get("PORT", 8080))
    print(f"Listening on port {port}")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
