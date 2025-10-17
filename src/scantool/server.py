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

mcp = FastMCP("File Scanner MCP")

# Global scanner and formatter instances
scanner = FileScanner()
formatter = TreeFormatter()
dir_formatter = DirectoryFormatter()


@mcp.tool
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

    Example output (tree format):
        example.py (3-57)
        ├─ imports: import statements (3-5)
        ├─ class: DatabaseManager (8-26)
        │    "Manages database connections and queries."
        │  ├─ method: __init__ (self, connection_string: str) (11-13)
        │  ├─ method: connect (self) (15-17)
        │  │    "Establish database connection."
        │  └─ method: query (self, sql: str) -> list (24-26)
        │       "Execute a SQL query."
        └─ function: validate_email (email: str) -> bool (48-50)
             "Validate email format."
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


@mcp.tool
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


@mcp.tool
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

    SEMANTIC CODE SEARCH. Use this instead of Grep when searching for code
    constructs (classes, functions, methods). Understands code structure, not
    just text matching. Can filter by decorators, complexity, and structure type.

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
