"""Base scanner class and data structures for all language-specific scanners."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StructureNode:
    """Represents a node in the file structure with rich metadata."""

    type: str  # e.g., "class", "function", "heading"
    name: str
    start_line: int
    end_line: int
    children: list["StructureNode"] = field(default_factory=list)

    # Enhanced metadata (optional)
    signature: Optional[str] = None  # Function signature with types
    decorators: list[str] = field(default_factory=list)  # @decorators
    docstring: Optional[str] = None  # First line of docstring
    complexity: Optional[dict] = None  # {"lines": int, "depth": int, "branches": int}
    modifiers: list[str] = field(default_factory=list)  # async, static, public, etc.
    file_metadata: Optional[dict] = None  # File-level metadata: size, timestamps, permissions

    def __repr__(self):
        return f"{self.type}: {self.name} ({self.start_line}-{self.end_line})"


class BaseScanner(ABC):
    """Base class for all file type scanners."""

    def __init__(self, show_errors: bool = True, fallback_on_errors: bool = True):
        """
        Initialize scanner with error handling options.

        Args:
            show_errors: Include ERROR nodes in output
            fallback_on_errors: Use regex fallback if too many parse errors
        """
        self.show_errors = show_errors
        self.fallback_on_errors = fallback_on_errors

    @classmethod
    @abstractmethod
    def get_extensions(cls) -> list[str]:
        """Return list of file extensions this scanner handles (e.g., ['.py', '.pyw'])."""
        pass

    @classmethod
    @abstractmethod
    def get_language_name(cls) -> str:
        """Return the human-readable language name (e.g., 'Python')."""
        pass

    @classmethod
    def get_priority(cls) -> int:
        """
        Return priority for this scanner (higher = preferred).
        Useful when multiple scanners claim the same extension.
        """
        return 0

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """
        Check if this file should be skipped based on filename patterns.

        Override this in language-specific scanners to skip common files like:
        - __init__.py (Python empty init files)
        - *.min.js (JavaScript minified files)
        - *.d.ts (TypeScript declaration files)

        Args:
            filename: Just the filename (not full path)

        Returns:
            True if file should be skipped (not scanned)
        """
        return False

    @abstractmethod
    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """
        Scan source code and extract structure.

        Args:
            source_code: Raw file content as bytes

        Returns:
            List of StructureNode objects representing the file structure,
            or None if the file couldn't be parsed
        """
        pass

    def _get_node_text(self, node, source_code: bytes) -> str:
        """Extract text from a tree-sitter node (helper for tree-sitter-based scanners)."""
        try:
            return source_code[node.start_byte:node.end_byte].decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return source_code[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _normalize_signature(self, signature: str) -> str:
        """
        Normalize a signature to single line for tree formatting.

        Removes newlines and collapses multiple spaces to ensure signatures
        don't break the tree structure visualization.

        Args:
            signature: Raw signature string (may contain newlines)

        Returns:
            Normalized single-line signature
        """
        if not signature:
            return signature

        # Replace newlines with spaces
        normalized = signature.replace('\n', ' ').replace('\r', ' ')

        # Collapse multiple spaces into single space
        normalized = ' '.join(normalized.split())

        return normalized

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

        # Use fallback if more than 50% are error nodes
        return total > 0 and (errors / total) > 0.5

    def _calculate_complexity(self, node) -> dict:
        """
        Calculate complexity metrics for a node.

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
            # Count control flow structures
            if n.type in ("if_statement", "for_statement", "while_statement",
                         "switch_statement", "case_statement", "match_statement"):
                stats["branches"] += 1
            for child in n.children:
                traverse_depth(child, depth + 1)

        traverse_depth(node, 0)
        return stats
