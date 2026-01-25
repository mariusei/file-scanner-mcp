"""Pretty tree formatter for file structure with rich metadata display."""

from pathlib import Path
from datetime import datetime
from .languages import StructureNode


class TreeFormatter:
    """Formats structure nodes as a pretty tree with metadata."""

    # Tree drawing characters (token-optimized: 2-space indent)
    BRANCH = "├─"
    LAST_BRANCH = "└─"
    VERTICAL = "│ "  # 2-space indent
    SPACE = "  "     # 2-space indent

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

            # Format timestamp as readable datetime with unix timestamp
            modified_iso = meta.get('modified', '')
            if modified_iso:
                try:
                    dt = datetime.fromisoformat(modified_iso)
                    # Format as: 2025-10-17 14:30 with unix timestamp for LLM processing
                    readable = dt.strftime('%Y-%m-%d %H:%M')
                    unix_ts = int(dt.timestamp())
                    modified_str = f"{readable} [ts:{unix_ts}]"
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

        # Build the main node line (token-optimized format)
        # Remove "type:" prefix (redundant), shorten line range format
        parts = [f"{prefix}{connector[:-1]} {node.name}"]  # ├─  → ├

        # Add signature if available
        if self.show_signatures and node.signature:
            parts.append(node.signature)

        # Add line numbers in compact format @startline
        if node.start_line > 0 or node.end_line > 0:
            parts.append(f"@{node.start_line}")

        # Add modifiers if present
        if node.modifiers:
            modifiers_str = " ".join(node.modifiers)
            parts.append(f"[{modifiers_str}]")

        # Add complexity indicator if enabled
        if self.show_complexity and node.complexity:
            complexity_str = self._format_complexity(node.complexity)
            if complexity_str:
                parts.append(complexity_str)

        # Add docstring inline as comment (token-optimized)
        if self.show_docstrings and node.docstring:
            parts.append(f"# {node.docstring}")

        lines.append(" ".join(parts))

        # Add decorators on separate lines (2-space indent, token-optimized)
        if self.show_decorators and node.decorators:
            decorator_prefix = prefix + (self.SPACE if is_last else self.VERTICAL) + " "  # 2-space
            for decorator in node.decorators:
                lines.append(f"{decorator_prefix}{decorator}")

        # Add code excerpt if node is marked as salient (high-entropy)
        if hasattr(node, 'code_excerpt') and node.code_excerpt:
            code_prefix = prefix + (self.SPACE if is_last else self.VERTICAL) + " "  # 2-space indent

            # No blank line (token-optimized)
            # Compact line number format: {i} | instead of {i:4d} |
            for i, line in enumerate(node.code_excerpt, start=node.start_line):
                lines.append(f"{code_prefix}{i} | {line}")

        # Format children (2-space indent, token-optimized)
        if node.children:
            child_prefix = prefix + (self.SPACE if is_last else self.VERTICAL)

            for i, child in enumerate(node.children):
                is_last_child = i == len(node.children) - 1
                lines.extend(self._format_node(child, child_prefix, is_last_child))

        return lines

    def _format_complexity(self, complexity: dict) -> str:
        """Format complexity metrics as compact text (no emoji - cleaner output)."""
        parts = []

        if complexity.get("lines", 0) > 100:
            parts.append(f"L{complexity['lines']}")

        if complexity.get("max_depth", 0) > 5:
            parts.append(f"D{complexity['max_depth']}")

        if complexity.get("branches", 0) > 10:
            parts.append(f"B{complexity['branches']}")

        return " ".join(parts) if parts else ""

    def _flatten(self, structures: list[StructureNode]) -> list[StructureNode]:
        """Flatten structure tree to get all nodes."""
        result = []
        for node in structures:
            result.append(node)
            if node.children:
                result.extend(self._flatten(node.children))
        return result
