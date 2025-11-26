"""Base analyzer class for language-specific code analysis."""

from abc import ABC, abstractmethod
from typing import Optional
from .models import ImportInfo, EntryPointInfo, DefinitionInfo, CallInfo


class BaseAnalyzer(ABC):
    """Base class for all language-specific analyzers."""

    def __init__(self):
        """Initialize analyzer."""
        pass

    @classmethod
    @abstractmethod
    def get_extensions(cls) -> list[str]:
        """Return list of file extensions this analyzer handles (e.g., ['.py', '.pyw'])."""
        pass

    @classmethod
    @abstractmethod
    def get_language_name(cls) -> str:
        """Return the human-readable language name (e.g., 'Python')."""
        pass

    @classmethod
    def get_priority(cls) -> int:
        """
        Return priority for this analyzer (higher = preferred).
        Useful when multiple analyzers claim the same extension.
        """
        return 0

    # ===================================================================
    # LAYER 1: File-level analysis (REQUIRED)
    # ===================================================================

    @abstractmethod
    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract import statements from file.

        Args:
            file_path: Relative path to the file
            content: File content as string

        Returns:
            List of ImportInfo objects
        """
        pass

    @abstractmethod
    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in the file.

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

    # ===================================================================
    # LAYER 2: Structure-level analysis (OPTIONAL - default to empty)
    # ===================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """
        Extract function/class definitions from file.

        This is optional Layer 2 functionality. Base implementation returns empty list.
        Override in language-specific analyzers to enable call graph analysis.

        Args:
            file_path: Relative path to the file
            content: File content as string

        Returns:
            List of DefinitionInfo objects
        """
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """
        Extract function/method calls from file.

        This is optional Layer 2 functionality. Base implementation returns empty list.
        Override in language-specific analyzers to enable call graph analysis.

        Args:
            file_path: Relative path to the file
            content: File content as string
            definitions: List of known definitions from this file (for context)

        Returns:
            List of CallInfo objects
        """
        return []

    # ===================================================================
    # Utility methods (OPTIONAL)
    # ===================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify file into architectural cluster.

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
        # Default heuristic-based classification
        path_lower = file_path.lower()
        name = file_path.split("/")[-1].lower()

        # Entry points
        if name in ["main.py", "server.py", "app.py", "__main__.py", "index.ts", "main.tsx", "app.tsx"]:
            return "entry_points"

        # Tests
        if name.startswith("test_") or "_test." in name or "/tests/" in path_lower:
            return "tests"

        # Config
        if name in ["config.py", "settings.py", "constants.py", "config.ts", "settings.ts"]:
            return "config"

        # Plugins
        if any(plugin_dir in path_lower for plugin_dir in ["/scanners/", "/plugins/", "/extensions/"]):
            return "plugins"

        # Utilities
        if "/utils/" in path_lower or "/helpers/" in path_lower or "utils." in name or "helper." in name:
            return "utilities"

        # Core logic (keywords in filename)
        core_keywords = ["scanner", "parser", "formatter", "analyzer", "processor", "engine"]
        if any(keyword in name for keyword in core_keywords):
            return "core_logic"

        return "other"

    def should_analyze(self, file_path: str) -> bool:
        """
        Check if this file should be analyzed.

        Override in language-specific analyzers to skip certain files:
        - Empty __init__.py files
        - Minified files (*.min.js)
        - Type declarations (*.d.ts)
        - Generated files

        Args:
            file_path: Relative path to the file

        Returns:
            True if file should be analyzed
        """
        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """
        Check if file is low-value for inventory listing.

        Unlike should_analyze (which skips analysis entirely), this method
        identifies files that CAN be analyzed but are low-value for a
        file inventory overview. Used by preview_directory to filter noise.

        NOTE: Central/hot files should NEVER be excluded from inventory,
        regardless of this method's return value. The caller must ensure
        files with high centrality_score or in hot_functions are included.

        Override in language-specific analyzers for patterns like:
        - Empty __init__.py (Python)
        - Type declarations *.d.ts (TypeScript)
        - Re-export index files (TypeScript/JavaScript)
        - Generated files (*.pb.go, *.generated.cs)

        Args:
            file_path: Relative path to the file
            size: File size in bytes (0 = unknown)

        Returns:
            True if file is low-value for inventory (can be hidden)
        """
        # Default: very small files are often boilerplate
        if size > 0 and size < 50:
            return True
        return False

    # ===================================================================
    # Helper methods for common patterns
    # ===================================================================

    def _resolve_relative_import(
        self, current_file: str, relative_import: str
    ) -> Optional[str]:
        """
        Resolve relative import to absolute file path.

        Args:
            current_file: Path of file doing the import (e.g., "src/foo/bar.py")
            relative_import: Relative import string (e.g., "..utils")

        Returns:
            Resolved path or None if cannot resolve
        """
        if not relative_import.startswith("."):
            return None

        # Count leading dots
        dots = len(relative_import) - len(relative_import.lstrip("."))
        rest = relative_import.lstrip(".")

        # Get parent directories
        parts = current_file.split("/")[:-1]  # Remove filename

        # Go up 'dots - 1' levels (. = same level, .. = parent, etc.)
        for _ in range(dots - 1):
            if not parts:
                return None
            parts.pop()

        # Add rest of path
        if rest:
            parts.extend(rest.split("."))

        return "/".join(parts) if parts else None
