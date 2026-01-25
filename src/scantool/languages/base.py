"""Base language class that unifies scanner and analyzer functionality.

This module provides the BaseLanguage class that combines:
- Structure scanning (tree-sitter based AST extraction)
- Semantic analysis (imports, entry points, definitions, calls)

Each language implementation inherits from BaseLanguage and provides
a single file per language instead of separate scanner + analyzer files.
"""

from abc import ABC, abstractmethod
from typing import Optional

from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class BaseLanguage(ABC):
    """Unified base class for language support.

    Combines the functionality of BaseScanner and BaseAnalyzer into a single
    interface. Each language provides one implementation file that handles
    both structure scanning and semantic analysis.

    Key methods:
    - scan(): Extract structure (classes, functions, methods) from source
    - extract_imports(): Find import statements
    - find_entry_points(): Find main functions, exports, etc.
    - extract_definitions(): Get function/class definitions (can reuse scan())
    - extract_calls(): Find function/method calls
    """

    def __init__(self, show_errors: bool = True, fallback_on_errors: bool = True):
        """Initialize language handler with error handling options.

        Args:
            show_errors: Include ERROR nodes in output
            fallback_on_errors: Use regex fallback if too many parse errors
        """
        self.show_errors = show_errors
        self.fallback_on_errors = fallback_on_errors

    # ===========================================================================
    # Metadata (REQUIRED - classmethod)
    # ===========================================================================

    @classmethod
    @abstractmethod
    def get_extensions(cls) -> list[str]:
        """Return list of file extensions this language handles.

        Examples:
            ['.py', '.pyw']  # Python
            ['.ts', '.tsx']  # TypeScript
            ['.swift']       # Swift
        """
        pass

    @classmethod
    @abstractmethod
    def get_language_name(cls) -> str:
        """Return the human-readable language name.

        Examples: 'Python', 'TypeScript', 'Swift'
        """
        pass

    @classmethod
    def get_priority(cls) -> int:
        """Return priority for this language (higher = preferred).

        Used when multiple languages claim the same extension.
        Default: 0
        """
        return 0

    # ===========================================================================
    # Skip/Filter Logic (OPTIONAL - combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Check if file should be skipped for scanning.

        Override to skip files like:
        - __init__.py (Python empty init files)
        - *.min.js (JavaScript minified files)
        - *.d.ts (TypeScript declaration files)

        Args:
            filename: Just the filename (not full path)

        Returns:
            True if file should be skipped (not scanned)
        """
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Check if file should be analyzed for semantic information.

        Override to skip certain files from import/entry point analysis.
        This is similar to should_skip but operates on full paths and
        is called during CodeMap analysis.

        Args:
            file_path: Relative path to the file

        Returns:
            True if file should be analyzed
        """
        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Check if file is low-value for inventory listing.

        Unlike should_analyze (which skips analysis entirely), this identifies
        files that CAN be analyzed but are low-value for overview displays.
        Used by preview_directory to filter noise.

        NOTE: Central/hot files should NEVER be excluded, regardless of
        this method's return value. Caller must check centrality.

        Override for patterns like:
        - Empty __init__.py (Python)
        - Type declarations *.d.ts (TypeScript)
        - Re-export index files

        Args:
            file_path: Relative path to the file
            size: File size in bytes (0 = unknown)

        Returns:
            True if file is low-value for inventory (can be hidden)
        """
        if size > 0 and size < 50:
            return True
        return False

    # ===========================================================================
    # Structure Scanning (REQUIRED - from BaseScanner)
    # ===========================================================================

    @abstractmethod
    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan source code and extract structure.

        This is the primary scanning method that extracts classes, functions,
        methods, and other structural elements from source code.

        Args:
            source_code: Raw file content as bytes

        Returns:
            List of StructureNode objects representing the file structure,
            or None if the file couldn't be parsed
        """
        pass

    # ===========================================================================
    # Semantic Analysis - Layer 1 (REQUIRED - from BaseAnalyzer)
    # ===========================================================================

    @abstractmethod
    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract import statements from file.

        Args:
            file_path: Relative path to the file
            content: File content as string

        Returns:
            List of ImportInfo objects
        """
        pass

    @abstractmethod
    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in the file.

        Entry points include:
        - main() functions
        - if __name__ == "__main__" blocks
        - app/server instances (Flask, FastAPI, Express, etc.)
        - Module exports

        Args:
            file_path: Relative path to the file
            content: File content as string

        Returns:
            List of EntryPointInfo objects
        """
        pass

    # ===========================================================================
    # Semantic Analysis - Layer 2 (OPTIONAL - default implementations)
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract function/class definitions from file.

        Default implementation converts scan() output to DefinitionInfo.
        Override for more precise control or when scan() isn't suitable.

        Args:
            file_path: Relative path to the file
            content: File content as string

        Returns:
            List of DefinitionInfo objects
        """
        try:
            structures = self.scan(content.encode("utf-8"))
            if not structures:
                return []
            return self._structures_to_definitions(file_path, structures)
        except Exception:
            return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Extract function/method calls from file.

        Default implementation returns empty list.
        Override to enable call graph analysis.

        Args:
            file_path: Relative path to the file
            content: File content as string
            definitions: List of known definitions from this file

        Returns:
            List of CallInfo objects
        """
        return []

    def _structures_to_definitions(
        self, file_path: str, structures: list[StructureNode], parent: str = None
    ) -> list[DefinitionInfo]:
        """Convert StructureNode list to DefinitionInfo list.

        Helper for default extract_definitions() implementation.
        """
        definitions = []

        for node in structures:
            if node.type in ("class", "function", "method"):
                definitions.append(
                    DefinitionInfo(
                        file=file_path,
                        type=node.type,
                        name=node.name,
                        line=node.start_line,
                        signature=node.signature,
                        parent=parent,
                    )
                )

            # Recurse into children
            if node.children:
                child_parent = node.name if node.type == "class" else parent
                definitions.extend(
                    self._structures_to_definitions(file_path, node.children, child_parent)
                )

        return definitions

    # ===========================================================================
    # Classification (OPTIONAL)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify file into architectural cluster.

        Clusters:
        - "entry_points" (main.py, server.py, app.py)
        - "core_logic" (scanner, parser, analyzer)
        - "utilities" (helpers, formatters)
        - "plugins" (scanners/*, extensions/*)
        - "config" (settings, constants)
        - "tests" (test_*.py, *_test.py)
        - "other" (default)

        Args:
            file_path: Relative path to the file
            content: File content as string

        Returns:
            Cluster name
        """
        path_lower = file_path.lower()
        name = file_path.split("/")[-1].lower()

        # Entry points
        entry_names = [
            "main.py", "server.py", "app.py", "__main__.py",
            "index.ts", "main.tsx", "app.tsx", "main.go"
        ]
        if name in entry_names:
            return "entry_points"

        # Tests
        if name.startswith("test_") or "_test." in name or "/tests/" in path_lower:
            return "tests"

        # Config
        config_names = ["config.py", "settings.py", "constants.py", "config.ts", "settings.ts"]
        if name in config_names:
            return "config"

        # Plugins
        plugin_dirs = ["/scanners/", "/plugins/", "/extensions/", "/languages/"]
        if any(plugin_dir in path_lower for plugin_dir in plugin_dirs):
            return "plugins"

        # Utilities
        if "/utils/" in path_lower or "/helpers/" in path_lower or "utils." in name or "helper." in name:
            return "utilities"

        # Core logic
        core_keywords = ["scanner", "parser", "formatter", "analyzer", "processor", "engine"]
        if any(keyword in name for keyword in core_keywords):
            return "core_logic"

        return "other"

    # ===========================================================================
    # CodeMap Integration (OPTIONAL)
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> Optional[str]:
        """Resolve import module to actual file path.

        Override for language-specific resolution:
        - Python: dot.separated.module -> path/to/module.py
        - Swift: Type references -> file defining Type
        - Go: github.com/pkg -> pkg/file.go
        - TypeScript: ./relative -> relative.ts or relative/index.ts

        Args:
            module: Module/type name to resolve
            source_file: Path of file doing the import
            all_files: List of all files in project
            definitions_map: Map of type/definition names to file paths

        Returns:
            Resolved file path, or None if external/unresolvable
        """
        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format entry point for display.

        Override for language-specific formatting.

        Args:
            ep: EntryPointInfo object to format

        Returns:
            Formatted string for display (with leading 2-space indent)
        """
        line_str = f" @{ep.line}" if ep.line else ""
        return f"  {ep.file}:{ep.name or ep.type}{line_str}"

    def get_file_extension(self) -> str:
        """Return primary file extension for this language.

        Returns:
            Primary extension (e.g., ".py", ".swift", ".go")
        """
        exts = self.get_extensions()
        return exts[0] if exts else ""

    # ===========================================================================
    # Helper methods (from BaseScanner)
    # ===========================================================================

    def _get_node_text(self, node, source_code: bytes) -> str:
        """Extract text from a tree-sitter node."""
        try:
            return source_code[node.start_byte:node.end_byte].decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return source_code[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _normalize_signature(self, signature: str) -> str:
        """Normalize a signature to single line for tree formatting."""
        if not signature:
            return signature
        normalized = signature.replace('\n', ' ').replace('\r', ' ')
        return ' '.join(normalized.split())

    def _count_error_nodes(self, node) -> int:
        """Count ERROR nodes in tree (for fallback detection)."""
        count = 1 if node.type == "ERROR" else 0
        for child in node.children:
            count += self._count_error_nodes(child)
        return count

    def _count_nodes(self, node) -> int:
        """Count all nodes in tree."""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count

    def _should_use_fallback(self, root_node) -> bool:
        """Determine if we should use regex fallback due to too many errors."""
        if not self.fallback_on_errors:
            return False
        total = self._count_nodes(root_node)
        errors = self._count_error_nodes(root_node)
        return total > 0 and (errors / total) > 0.5

    def _calculate_complexity(self, node) -> dict:
        """Calculate complexity metrics for a node.

        Returns:
            Dict with keys: lines, max_depth, branches
        """
        stats = {
            "lines": node.end_point[0] - node.start_point[0] + 1,
            "max_depth": 0,
            "branches": 0,
        }

        def traverse_depth(n, depth: int):
            stats["max_depth"] = max(stats["max_depth"], depth)
            if n.type in (
                "if_statement", "for_statement", "while_statement",
                "switch_statement", "case_statement", "match_statement"
            ):
                stats["branches"] += 1
            for child in n.children:
                traverse_depth(child, depth + 1)

        traverse_depth(node, 0)
        return stats

    def _resolve_relative_import(
        self, current_file: str, relative_import: str
    ) -> Optional[str]:
        """Resolve relative import to absolute file path.

        Args:
            current_file: Path of file doing the import
            relative_import: Relative import string

        Returns:
            Resolved path or None
        """
        if not relative_import.startswith("."):
            return None

        dots = len(relative_import) - len(relative_import.lstrip("."))
        rest = relative_import.lstrip(".")

        parts = current_file.split("/")[:-1]  # Remove filename

        for _ in range(dots - 1):
            if not parts:
                return None
            parts.pop()

        if rest:
            parts.extend(rest.split("."))

        return "/".join(parts) if parts else None
