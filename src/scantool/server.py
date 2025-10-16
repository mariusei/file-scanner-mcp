from fastmcp import FastMCP
from .scanner import FileScanner
from .formatter import TreeFormatter

mcp = FastMCP("File Scanner MCP")

scanner = FileScanner()
formatter = TreeFormatter()


@mcp.tool
def scan_file(file_path: str) -> str:
    """
    Scan a source file and return its structure as a pretty tree.

    Returns a table of contents with line numbers (from-to) in a beautifully
    formatted tree structure with indentation, showing classes, functions,
    methods, imports, and other structural elements.

    Supports: Python, JavaScript, TypeScript, Rust, Go, and Markdown files.

    Args:
        file_path: Absolute or relative path to the file to scan

    Returns:
        Pretty-formatted tree structure with line numbers

    Example output:
        example.py (1-50)
        ├─ imports: import statements (1-3)
        ├─ class: UserManager (5-25)
        │  ├─ method: __init__ (6-8)
        │  ├─ method: create_user (10-15)
        │  └─ method: delete_user (17-24)
        ├─ function: validate_email (27-32)
        └─ function: main (34-50)
    """
    try:
        structures = scanner.scan_file(file_path)

        if structures is None:
            return f"Error: Unsupported file type. Supported extensions: {', '.join(FileScanner.LANGUAGE_MAP.keys())}"

        if not structures:
            return f"{file_path} (empty file or no structure found)"

        return formatter.format(file_path, structures)

    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error scanning file: {e}"


def main():
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
