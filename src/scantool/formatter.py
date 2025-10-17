"""Pretty tree formatter for file structure with rich metadata display."""

from pathlib import Path
from datetime import datetime
from .scanners import StructureNode


class TreeFormatter:
    """Formats structure nodes as a pretty tree with metadata."""

    # Tree drawing characters
    BRANCH = "├─"
    LAST_BRANCH = "└─"
    VERTICAL = "│  "
    SPACE = "   "

    def __init__(self, show_signatures: bool = True, show_decorators: bool = True,
                 show_docstrings: bool = True, show_complexity: bool = False):
        """
        Initialize formatter with display options.

        Args:
            show_signatures: Display function signatures
            show_decorators: Display decorators
            show_docstrings: Display first line of docstrings
            show_complexity: Display complexity metrics
        """
        self.show_signatures = show_signatures
        self.show_decorators = show_decorators
        self.show_docstrings = show_docstrings
        self.show_complexity = show_complexity

    def format(self, file_path: str, structures: list[StructureNode]) -> str:
        """Format the structure as a pretty tree."""
        if not structures:
            return f"{Path(file_path).name} (empty file)"

        # Get file line range (excluding metadata nodes with line 0)
        content_nodes = [s for s in self._flatten(structures) if s.start_line > 0 or s.end_line > 0]
        if content_nodes:
            min_line = min(s.start_line for s in content_nodes)
            max_line = max(s.end_line for s in content_nodes)
            lines = [f"{Path(file_path).name} ({min_line}-{max_line})"]
        else:
            lines = [f"{Path(file_path).name}"]

        for i, node in enumerate(structures):
            is_last = i == len(structures) - 1
            lines.extend(self._format_node(node, "", is_last))

        return "\n".join(lines)

    def _format_node(self, node: StructureNode, prefix: str, is_last: bool) -> list[str]:
        """Format a single node and its children with metadata."""
        lines = []

        # Current node connector
        connector = self.LAST_BRANCH if is_last else self.BRANCH

        # Special formatting for file-info nodes
        if node.type == "file-info" and node.file_metadata:
            meta = node.file_metadata

            # Format timestamp as readable datetime
            modified_iso = meta.get('modified', '')
            if modified_iso:
                try:
                    dt = datetime.fromisoformat(modified_iso)
                    # Format as: 2025-10-17 14:30
                    modified_str = dt.strftime('%Y-%m-%d %H:%M')
                except Exception:
                    # Fallback to just date if parsing fails
                    modified_str = modified_iso.split('T')[0]
            else:
                modified_str = ""

            parts = [
                f"{prefix}{connector} {node.type}:",
                meta['size_formatted'],
                f"modified: {modified_str}" if modified_str else ""
            ]
            lines.append(" ".join(p for p in parts if p))
            return lines

        # Build the main node line
        parts = [f"{prefix}{connector} {node.type}: {node.name}"]

        # Add signature if available
        if self.show_signatures and node.signature:
            parts.append(node.signature)

        # Add line numbers (skip for file-info nodes with line 0)
        if node.start_line > 0 or node.end_line > 0:
            parts.append(f"({node.start_line}-{node.end_line})")

        # Add modifiers if present
        if node.modifiers:
            modifiers_str = " ".join(node.modifiers)
            parts.append(f"[{modifiers_str}]")

        # Add complexity indicator if enabled
        if self.show_complexity and node.complexity:
            complexity_str = self._format_complexity(node.complexity)
            if complexity_str:
                parts.append(complexity_str)

        lines.append(" ".join(parts))

        # Add decorators on separate lines (indented)
        if self.show_decorators and node.decorators:
            decorator_prefix = prefix + (self.SPACE if is_last else self.VERTICAL) + "  "
            for decorator in node.decorators:
                lines.append(f"{decorator_prefix}{decorator}")

        # Add docstring on separate line (indented)
        if self.show_docstrings and node.docstring:
            docstring_prefix = prefix + (self.SPACE if is_last else self.VERTICAL) + "  "
            lines.append(f'{docstring_prefix}"{node.docstring}"')

        # Format children
        if node.children:
            # New prefix for children
            child_prefix = prefix + (self.SPACE if is_last else self.VERTICAL)

            for i, child in enumerate(node.children):
                is_last_child = i == len(node.children) - 1
                lines.extend(self._format_node(child, child_prefix, is_last_child))

        return lines

    def _format_complexity(self, complexity: dict) -> str:
        """Format complexity metrics as a compact string."""
        parts = []

        if complexity.get("lines", 0) > 100:
            parts.append(f"📏{complexity['lines']}")

        if complexity.get("max_depth", 0) > 5:
            parts.append(f"🔄{complexity['max_depth']}")

        if complexity.get("branches", 0) > 10:
            parts.append(f"🌿{complexity['branches']}")

        return " ".join(parts) if parts else ""

    def _flatten(self, structures: list[StructureNode]) -> list[StructureNode]:
        """Flatten structure tree to get all nodes."""
        result = []
        for node in structures:
            result.append(node)
            if node.children:
                result.extend(self._flatten(node.children))
        return result
