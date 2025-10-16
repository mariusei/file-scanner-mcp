"""Pretty tree formatter for file structure."""

from pathlib import Path
from .scanner import StructureNode


class TreeFormatter:
    """Formats structure nodes as a pretty tree."""

    # Tree drawing characters
    BRANCH = "├─"
    LAST_BRANCH = "└─"
    VERTICAL = "│  "
    SPACE = "   "

    def format(self, file_path: str, structures: list[StructureNode]) -> str:
        """Format the structure as a pretty tree."""
        if not structures:
            return f"{Path(file_path).name} (empty file)"

        # Get file line range
        min_line = min(s.start_line for s in self._flatten(structures))
        max_line = max(s.end_line for s in self._flatten(structures))

        lines = [f"{Path(file_path).name} ({min_line}-{max_line})"]

        for i, node in enumerate(structures):
            is_last = i == len(structures) - 1
            lines.extend(self._format_node(node, "", is_last))

        return "\n".join(lines)

    def _format_node(self, node: StructureNode, prefix: str, is_last: bool) -> list[str]:
        """Format a single node and its children."""
        lines = []

        # Current node connector
        connector = self.LAST_BRANCH if is_last else self.BRANCH

        # Format current node
        node_str = f"{prefix}{connector} {node.type}: {node.name} ({node.start_line}-{node.end_line})"
        lines.append(node_str)

        # Format children
        if node.children:
            # New prefix for children
            child_prefix = prefix + (self.SPACE if is_last else self.VERTICAL)

            for i, child in enumerate(node.children):
                is_last_child = i == len(node.children) - 1
                lines.extend(self._format_node(child, child_prefix, is_last_child))

        return lines

    def _flatten(self, structures: list[StructureNode]) -> list[StructureNode]:
        """Flatten structure tree to get all nodes."""
        result = []
        for node in structures:
            result.append(node)
            if node.children:
                result.extend(self._flatten(node.children))
        return result
