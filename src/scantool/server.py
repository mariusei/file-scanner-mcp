"""FastMCP server with file scanning tools."""

import json
import os
import re
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from mcp.types import TextContent

from .formatter import TreeFormatter
from .directory_formatter import DirectoryFormatter
from .scanner import FileScanner
from .scanners import StructureNode
from .preview import preview_directory as preview_dir_func
from .intelligent_preview import intelligent_preview
from .code_map import CodeMap

mcp = FastMCP("File Scanner MCP")

# Global scanner and formatter instances
scanner = FileScanner()
formatter = TreeFormatter()
dir_formatter = DirectoryFormatter()


@mcp.tool(
    tags={"exploration", "overview", "fast"},
    description="Fast codebase preview - USE THIS FIRST before scan_directory to understand structure and make informed decisions"
)
def preview_directory(
    directory: str,
    max_depth: Optional[int] = 5,
    intelligent: bool = True,
    ollama_model: str = "qwen2.5-coder:1.5b",
    max_files_hint: int = 100000,
    show_top_n: int = 8,
    respect_gitignore: bool = True
) -> list[TextContent]:
    """
    Intelligent codebase preview with optional Ollama-powered code structure analysis.

    **When to use this vs other tools:**
    - Use preview_directory() FIRST → understand codebase structure with actual code
    - Use scan_directory() AFTER → for detailed scanning of specific parts
    - Set intelligent=False → for instant metadata-only overview (0.5s)

    **Two modes:**

    1. **Intelligent mode (default, ~23-30s):**
       - Uses Ollama to intelligently sample ~100-150 most important files
       - Returns actual code structure: functions, classes, methods
       - Token-efficient format with Norwegian labels (funksjoner:, klasser:)
       - 80% coverage of critical files (entry points, APIs, core logic)
       - Requires Ollama running locally with qwen2.5-coder:1.5b

    2. **Fast mode (intelligent=False, <0.5s):**
       - File system metadata only (no code parsing)
       - Directory tree with file counts and types
       - Perfect for quick orientation or very large repos

    **Recommended for:** Initial codebase exploration, understanding project architecture

    Args:
        directory: Root directory to preview
        max_depth: Maximum directory depth (default: 5)
        intelligent: Use Ollama for intelligent sampling with code structure (default: True)
        ollama_model: Ollama model to use (default: "qwen2.5-coder:1.5b")
        max_files_hint: Safety limit for file count (default: 100k, only for fast mode)
        show_top_n: Top directories to show (default: 8, only for fast mode)
        respect_gitignore: Respect .gitignore patterns (default: True)

    Returns:
        Intelligent mode: Sampled files with code structure
        Fast mode: Directory stats and file counts

    Examples:
        # Intelligent preview with code structure (default)
        preview_directory("./my-project")

        # Fast metadata-only preview
        preview_directory("./my-project", intelligent=False)

        # Use different Ollama model
        preview_directory("./src", ollama_model="qwen2.5-coder:7b")

    Typical workflow:
        1. preview_directory(".") → deep understanding with code structure
        2. Ask questions about architecture, patterns, key components
        3. scan_directory("src/api", "**/*.py") → detailed scan of specific parts
    """
    try:
        if intelligent:
            # Intelligent mode: Use Ollama for code structure
            result = intelligent_preview(
                directory=directory,
                ollama_model=ollama_model,
                max_depth=max_depth,
                respect_gitignore=respect_gitignore
            )
        else:
            # Fast mode: Metadata only
            result = preview_dir_func(
                directory=directory,
                max_depth=max_depth,
                max_files_hint=max_files_hint,
                show_top_n=show_top_n,
                respect_gitignore=respect_gitignore
            )
        return [TextContent(type="text", text=result)]
    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: Directory not found: {directory}")]
    except PermissionError as e:
        return [TextContent(type="text", text=f"Error: Permission denied: {directory}")]
    except RuntimeError as e:
        # Check if this is a fallback trigger from intelligent mode
        error_msg = str(e)
        if intelligent and ("Falling back to fast mode" in error_msg or "found structure in only" in error_msg):
            fallback_msg = f"⚠️  {error_msg}\n\n"
            try:
                basic_result = preview_dir_func(
                    directory=directory,
                    max_depth=max_depth,
                    max_files_hint=max_files_hint,
                    show_top_n=show_top_n,
                    respect_gitignore=respect_gitignore
                )
                return [TextContent(type="text", text=fallback_msg + basic_result)]
            except Exception as fallback_error:
                return [TextContent(type="text", text=fallback_msg + f"Error in fallback: {fallback_error}")]
        else:
            return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        # Graceful fallback for intelligent mode
        error_msg = str(e)
        if intelligent and ("Connection" in error_msg or "11434" in error_msg):
            fallback_msg = (
                f"⚠️  Ollama unavailable (connection failed)\n\n"
                f"To use intelligent preview:\n"
                f"1. Install Ollama: https://ollama.com\n"
                f"2. Pull model: ollama pull {ollama_model}\n"
                f"3. Ensure Ollama is running\n\n"
                f"Falling back to fast mode...\n\n"
            )
            try:
                basic_result = preview_dir_func(
                    directory=directory,
                    max_depth=max_depth,
                    max_files_hint=max_files_hint,
                    show_top_n=show_top_n,
                    respect_gitignore=respect_gitignore
                )
                return [TextContent(type="text", text=fallback_msg + basic_result)]
            except Exception:
                return [TextContent(type="text", text=fallback_msg + f"Error: {e}")]
        else:
            return [TextContent(type="text", text=f"Error previewing directory: {e}")]


@mcp.tool(
    tags={"exploration", "analysis", "overview", "local"},
    description="Intelligent code map - Shows entry points, import graph, call patterns, and architecture (fast, deterministic, offline)"
)
def code_map(
    directory: str,
    respect_gitignore: bool = True,
    max_files: int = 10000,
    max_entries: int = 20,
    enable_layer2: bool = True
) -> list[TextContent]:
    """
    Build intelligent code map showing codebase structure and relationships.

    **FAST REPLACEMENT for preview_directory's intelligent mode:**
    - 15x faster (<2s vs 23-30s with Ollama)
    - Deterministic (same results every time)
    - Offline (no Ollama required)
    - Richer analysis (imports, entry points, call patterns, architecture)

    **What it shows:**
    1. Entry Points: main(), if __name__, app instances, exports
    2. Core Files: Ranked by centrality (most imported = most important)
    3. Architecture: Files clustered by role (entry points, core logic, plugins, utilities, tests)
    4. Dependencies: Import relationships between files

    **Layer 1 Analysis:**
    - File-level import graph
    - Entry point detection
    - File clustering
    - Centrality ranking

    **Layer 2 Analysis (default enabled):**
    - Function/class definitions
    - Cross-file call graph
    - Function-level centrality
    - Hot function detection

    **Recommended workflow:**
    1. code_map(".") → instant architecture understanding with call graph
    2. Ask about specific patterns, entry points, dependencies, hot functions
    3. scan_directory() → detailed code structure of specific areas

    Args:
        directory: Root directory to analyze
        respect_gitignore: Respect .gitignore patterns (default: True)
        max_files: Maximum files to analyze (default: 10000)
        max_entries: Maximum entries per section (default: 20)
        enable_layer2: Enable Layer 2 analysis (call graphs, function centrality) (default: True)

    Returns:
        Code map with entry points, import graph, and architecture

    Examples:
        # Analyze current project
        code_map(".")

        # Analyze subdirectory
        code_map("src/api")

        # Include all files (ignore .gitignore)
        code_map(".", respect_gitignore=False)
    """
    try:
        # Create code map instance
        cm = CodeMap(
            directory=directory,
            respect_gitignore=respect_gitignore,
            max_files=max_files,
            enable_layer2=enable_layer2
        )

        # Analyze
        result = cm.analyze()

        # Format as tree
        output = cm.format_tree(result, max_entries=max_entries)

        return [TextContent(type="text", text=output)]

    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: Directory not found: {directory}")]
    except PermissionError as e:
        return [TextContent(type="text", text=f"Error: Permission denied: {directory}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error analyzing code map: {e}")]


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

    Args:
        directory: Root directory to list
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

    Args:
        content: The file content as a string
        filename: Filename (with extension) to determine parser type
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
    description="Scan local file structure - USE THIS BEFORE Read to get overview with line numbers"
)
def scan_file(
    file_path: str,
    show_signatures: bool = True,
    show_decorators: bool = True,
    show_docstrings: bool = True,
    show_complexity: bool = False,
    output_format: str = "tree"
) -> list[TextContent]:
    """
    Scan a source file and return its structure.

    **When to use this vs other tools:**
    - Use scan_file() BEFORE Read → get table of contents with line numbers first
    - Use scan_file() INSTEAD of reading entire file → see structure overview efficiently
    - Use scan_directory() INSTEAD when exploring multiple files → get directory-wide view
    - Use scan_file_content() INSTEAD for remote content → no local file needed

    **Recommended for:** Local files (includes full metadata: timestamps, permissions, size)

    Use this to get a structural overview of a code file before reading it.
    Provides table of contents with line numbers, making it easy to identify
    which sections to read with the Read tool.

    More efficient than Read for initial exploration - shows what's in the file
    without loading full content. Get signatures, decorators, docstrings, and
    precise line ranges for each code element.

    Supports: Python, JavaScript, TypeScript, Rust, Go, Markdown, and Plain Text files.

    Args:
        file_path: Absolute or relative path to the file to scan
        show_signatures: Include function signatures with types (default: True)
        show_decorators: Include decorators like @property, @staticmethod (default: True)
        show_docstrings: Include first line of docstrings (default: True)
        show_complexity: Show complexity metrics for long/complex functions (default: False)
        output_format: Output format - "tree" or "json" (default: "tree")

    Returns:
        Formatted structure output (tree or JSON)

    Example output (token-optimized tree format with entropy-based code excerpts):
        Compact format: @line instead of (start-end), inline docstrings with #
        High-entropy functions show actual code implementation

        example.py (3-57)
        ├ import statements @3
        ├ DatabaseManager @8 # Manages database connections
        │ ├ __init__ (self, connection_string: str) @11
        │ ├ connect (self) @15 # Establish database connection
        │ └ query (self, sql: str) -> list @24 # Execute a SQL query
        │   24 | def query(self, sql: str) -> list:
        │   25 |     return self.cursor.execute(sql).fetchall()
        └ validate_email (email: str) -> bool @48 # Validate email format
    """
    try:
        structures = scanner.scan_file(file_path)

        if structures is None:
            supported = ", ".join(scanner.get_supported_extensions())
            return f"Error: Unsupported file type. Supported extensions: {supported}"

        if not structures:
            return f"{file_path} (empty file or no structure found)"

        # Format output
        if output_format == "json":
            return _structures_to_json(structures, file_path)
        else:
            # Use custom formatter with options
            custom_formatter = TreeFormatter(
                show_signatures=show_signatures,
                show_decorators=show_decorators,
                show_docstrings=show_docstrings,
                show_complexity=show_complexity
            )
            result = custom_formatter.format(file_path, structures)
            return [TextContent(type="text", text=result)]

    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error scanning file: {e}")]


@mcp.tool(
    tags={"local", "directory", "exploration"},
    description="Scan directory structure - USE THIS INSTEAD of Glob when you want to see both file tree AND code structure"
)
def scan_directory(
    directory: str,
    pattern: str = "**/*",
    max_files: Optional[int] = None,
    respect_gitignore: bool = True,
    exclude_patterns: Optional[list[str]] = None,
    output_format: str = "tree"
) -> list[TextContent]:
    """
    Scan directory and show compact overview of code structure.

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

    ALWAYS shows structures in compact inline format:
    - filename.py (1-100) - ClassName, function_name, AnotherClass

    Use pattern to control scope:
    - "**/*" = recursive scan all files (default)
    - "*/*" = 1 level deep only
    - "src/**/*.py" = only Python files in src/
    - "**/*.{py,ts}" = Python and TypeScript files

    Respects .gitignore by default (excludes node_modules, .venv, etc.)

    Args:
        directory: Directory path to scan
        pattern: Glob pattern (default: "**/*" = recursive all files)
        max_files: Maximum files to process (default: None = unlimited)
        respect_gitignore: Respect .gitignore exclusions (default: True)
        exclude_patterns: Additional patterns to exclude (gitignore syntax)
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
            exclude_patterns=exclude_patterns
        )

        if not results:
            return f"No supported files found in {directory} matching {pattern}"

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
            return warning + json.dumps(json_results, indent=2)
        else:
            # ALWAYS use compact inline format for directory scans
            custom_formatter = DirectoryFormatter(
                include_structures=True,
                flatten_structures=True  # Always flat for directory overview
            )
            result = warning + custom_formatter.format(directory, results)
            return [TextContent(type="text", text=result)]

    except FileNotFoundError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error scanning directory: {e}")]


@mcp.tool(
    tags={"local", "search", "filter"},
    description="Search code structures - USE THIS INSTEAD of Grep when searching for classes, functions, or methods by name/type/decorator"
)
def search_structures(
    directory: str,
    type_filter: Optional[str] = None,
    name_pattern: Optional[str] = None,
    has_decorator: Optional[str] = None,
    min_complexity: Optional[int] = None,
    output_format: str = "tree"
) -> list[TextContent]:
    """
    Search for specific structures across a directory.

    **When to use this vs other tools:**
    - Use search_structures() INSTEAD of Grep → when searching for code constructs (classes, functions)
    - Use search_structures() to find by decorator → e.g., all @pytest.fixture or @dataclass
    - Use search_structures() to find by pattern → e.g., all test_* functions or *Manager classes
    - Use Grep INSTEAD for literal text search → when you need to find specific strings/comments

    **Recommended for:** Local codebases - semantic search for classes, functions, methods

    SEMANTIC CODE SEARCH. Understands code structure, not just text matching.
    Can filter by decorators, complexity, and structure type.

    Perfect for: "find all test functions", "show async methods", "locate
    classes with @dataclass", "find complex functions to refactor".

    Args:
        directory: Directory to search in
        type_filter: Filter by type (e.g., "function", "class", "method")
        name_pattern: Regex pattern to match names (e.g., "^test_", ".*Manager$")
        has_decorator: Filter by decorator (e.g., "@property", "@staticmethod")
        min_complexity: Minimum complexity (lines) to include
        output_format: Output format - "tree" or "json" (default: "tree")

    Returns:
        Matching structures with line numbers and metadata

    Examples:
        # Find all async functions
        search_structures("./src", name_pattern="async.*")

        # Find all classes ending in "Manager"
        search_structures("./src", type_filter="class", name_pattern=".*Manager$")

        # Find functions with staticmethod decorator
        search_structures("./src", type_filter="function", has_decorator="@staticmethod")
    """
    try:
        # Scan directory (recursively scan all files)
        results = scanner.scan_directory(directory, "**/*")

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
            return "No structures found matching the criteria"

        # Format output
        if output_format == "json":
            json_results = {}
            for file_path, structures in matching.items():
                json_results[file_path] = _structures_to_json(structures, file_path, return_dict=True)
            return json.dumps(json_results, indent=2)
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
