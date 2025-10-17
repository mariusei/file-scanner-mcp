"""Hierarchical directory tree formatter with integrated code structures."""

from pathlib import Path
from collections import defaultdict
from typing import Optional
from datetime import datetime
from .scanners import StructureNode


class DirectoryFormatter:
    """Formats directory scans as hierarchical trees with code structures."""

    # Tree drawing characters
    BRANCH = "├─"
    LAST_BRANCH = "└─"
    VERTICAL = "│  "
    SPACE = "   "

    @staticmethod
    def _format_relative_time(iso_timestamp: str) -> str:
        """Format timestamp as relative time (e.g., '2 mins ago', '3 days ago')."""
        try:
            # Parse ISO timestamp
            modified_time = datetime.fromisoformat(iso_timestamp)
            now = datetime.now()
            diff = now - modified_time

            # Calculate time difference
            seconds = diff.total_seconds()
            if seconds < 60:
                return "just now"
            elif seconds < 3600:  # < 1 hour
                mins = int(seconds / 60)
                return f"{mins} min{'s' if mins != 1 else ''} ago"
            elif seconds < 86400:  # < 1 day
                hours = int(seconds / 3600)
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif seconds < 604800:  # < 1 week
                days = int(seconds / 86400)
                return f"{days} day{'s' if days != 1 else ''} ago"
            elif seconds < 2592000:  # < 30 days
                weeks = int(seconds / 604800)
                return f"{weeks} week{'s' if weeks != 1 else ''} ago"
            elif seconds < 31536000:  # < 1 year
                months = int(seconds / 2592000)
                return f"{months} month{'s' if months != 1 else ''} ago"
            else:
                years = int(seconds / 31536000)
                return f"{years} year{'s' if years != 1 else ''} ago"
        except Exception:
            # If parsing fails, return empty string
            return ""

    def __init__(self, show_signatures: bool = True, show_decorators: bool = True,
                 show_docstrings: bool = True, show_complexity: bool = False,
                 include_structures: bool = True, flatten_structures: bool = False):
        """
        Initialize directory formatter with display options.

        Args:
            flatten_structures: Show only top-level structures (classes/functions)
                               without nested children (methods). Reduces output by ~50%.
        """
        self.show_signatures = show_signatures
        self.show_decorators = show_decorators
        self.show_docstrings = show_docstrings
        self.show_complexity = show_complexity
        self.include_structures = include_structures
        self.flatten_structures = flatten_structures

    def format(self, base_dir: str, file_structures: dict[str, list[StructureNode]]) -> str:
        """
        Format directory scan as hierarchical tree.

        Args:
            base_dir: Base directory path
            file_structures: Dict mapping file paths to their structure nodes

        Returns:
            Formatted hierarchical tree string
        """
        base_path = Path(base_dir).resolve()

        # Build directory tree
        tree = self._build_tree(base_path, file_structures)

        # Format as text
        lines = [f"{base_path.name}/ {self._format_stats(tree)}"]
        lines.extend(self._format_tree_node(tree, ""))

        return "\n".join(lines)

    def _build_tree(self, base_path: Path, file_structures: dict[str, list[StructureNode]]) -> dict:
        """Build hierarchical directory tree structure."""
        tree = {
            "type": "directory",
            "name": base_path.name,
            "path": base_path,
            "children": {},
            "files": {},
            "stats": {"files": 0, "classes": 0, "functions": 0, "methods": 0}
        }

        for file_path_str, structures in file_structures.items():
            if not structures:
                continue

            file_path = Path(file_path_str).resolve()

            # Get relative path from base
            try:
                rel_path = file_path.relative_to(base_path)
            except ValueError:
                # File is outside base_path, skip it
                continue

            # Navigate/create directory structure
            current = tree
            parts = list(rel_path.parts[:-1])  # All but filename

            for part in parts:
                if part not in current["children"]:
                    current["children"][part] = {
                        "type": "directory",
                        "name": part,
                        "children": {},
                        "files": {},
                        "stats": {"files": 0, "classes": 0, "functions": 0, "methods": 0}
                    }
                current = current["children"][part]

            # Add file to current directory
            filename = rel_path.parts[-1]
            current["files"][filename] = {
                "type": "file",
                "name": filename,
                "path": file_path,
                "structures": structures
            }

            # Update stats recursively up the tree
            self._update_stats(tree, structures)

        return tree

    def _update_stats(self, node: dict, structures: list[StructureNode]):
        """Update statistics for a node and count structures."""
        node["stats"]["files"] += 1

        def count_structures(structs):
            for s in structs:
                if s.type == "class":
                    node["stats"]["classes"] += 1
                elif s.type == "function":
                    node["stats"]["functions"] += 1
                elif s.type == "method":
                    node["stats"]["methods"] += 1

                if hasattr(s, "children") and s.children:
                    count_structures(s.children)

        count_structures(structures)

    def _format_stats(self, node: dict) -> str:
        """Format directory statistics."""
        stats = node["stats"]
        parts = []

        if stats["files"] > 0:
            parts.append(f"{stats['files']} file{'s' if stats['files'] != 1 else ''}")
        if stats["classes"] > 0:
            parts.append(f"{stats['classes']} class{'es' if stats['classes'] != 1 else ''}")
        if stats["functions"] > 0:
            parts.append(f"{stats['functions']} function{'s' if stats['functions'] != 1 else ''}")
        if stats["methods"] > 0:
            parts.append(f"{stats['methods']} method{'s' if stats['methods'] != 1 else ''}")

        return f"({', '.join(parts)})" if parts else ""

    def _format_tree_node(self, node: dict, prefix: str) -> list[str]:
        """Recursively format a tree node and its children."""
        lines = []

        # Get sorted children and files
        dirs = sorted(node["children"].items())
        files = sorted(node["files"].items())

        all_items = [(name, child, True) for name, child in dirs] + \
                    [(name, child, False) for name, child in files]

        for i, (name, child, is_dir) in enumerate(all_items):
            is_last = i == len(all_items) - 1
            connector = self.LAST_BRANCH if is_last else self.BRANCH

            if is_dir:
                # Directory
                stats_str = self._format_stats(child)
                lines.append(f"{prefix}{connector} {name}/ {stats_str}")

                # Recurse into directory
                child_prefix = prefix + (self.SPACE if is_last else self.VERTICAL)
                lines.extend(self._format_tree_node(child, child_prefix))

            else:
                # File
                structures = child["structures"]

                # Check if this is an unsupported file (only has file-info with unsupported flag)
                is_unsupported = (
                    len(structures) == 1
                    and structures[0].type == "file-info"
                    and hasattr(structures[0], "file_metadata")
                    and structures[0].file_metadata
                    and structures[0].file_metadata.get("unsupported", False)
                )

                if is_unsupported:
                    # Unsupported file - show with metadata (no extension needed, it's in the filename)
                    metadata = structures[0].file_metadata
                    size = metadata.get("size_formatted", "")

                    # Format modified time as relative (e.g., "2 mins ago")
                    modified_iso = metadata.get("modified", "")
                    modified_relative = self._format_relative_time(modified_iso) if modified_iso else ""

                    # Build metadata string: size, relative time
                    meta_parts = [size, modified_relative]
                    meta_str = ", ".join(p for p in meta_parts if p)
                    lines.append(f"{prefix}{connector} {name} [{meta_str}]")
                else:
                    # Supported file - show structures with metadata
                    min_line = min(s.start_line for s in self._flatten(structures)) if structures else 1
                    max_line = max(s.end_line for s in self._flatten(structures)) if structures else 1

                    # Extract metadata from file-info node if present
                    file_metadata = None
                    if structures and structures[0].type == "file-info":
                        file_metadata = structures[0].file_metadata

                    # Format metadata (size and modified time)
                    metadata_str = ""
                    if file_metadata:
                        size = file_metadata.get("size_formatted", "")
                        modified_iso = file_metadata.get("modified", "")
                        modified_relative = self._format_relative_time(modified_iso) if modified_iso else ""

                        meta_parts = [size, modified_relative]
                        metadata_str = " [" + ", ".join(p for p in meta_parts if p) + "]"

                    # Format file line
                    if self.include_structures and self.flatten_structures:
                        # Ultra-compact mode: show structures inline
                        display_structures = self._flatten_top_level(structures)
                        if display_structures:
                            # Get just the names of classes and functions
                            names = [s.name for s in display_structures]
                            if len(names) > 5:
                                # Truncate if too many
                                structure_list = ", ".join(names[:5]) + f", ... ({len(names)} total)"
                            else:
                                structure_list = ", ".join(names)
                            lines.append(f"{prefix}{connector} {name} ({min_line}-{max_line}){metadata_str} - {structure_list}")
                        else:
                            lines.append(f"{prefix}{connector} {name} ({min_line}-{max_line}){metadata_str}")
                    elif self.include_structures:
                        # Normal mode: show structures in tree below file
                        lines.append(f"{prefix}{connector} {name} ({min_line}-{max_line}){metadata_str}")
                        child_prefix = prefix + (self.SPACE if is_last else self.VERTICAL)
                        lines.extend(self._format_structures(structures, child_prefix))
                    else:
                        # No structures mode
                        lines.append(f"{prefix}{connector} {name} ({min_line}-{max_line}){metadata_str}")

        return lines

    def _format_structures(self, structures: list[StructureNode], prefix: str) -> list[str]:
        """Format structure nodes with indentation."""
        lines = []

        for i, node in enumerate(structures):
            is_last = i == len(structures) - 1
            lines.extend(self._format_structure_node(node, prefix, is_last))

        return lines

    def _format_structure_node(self, node: StructureNode, prefix: str, is_last: bool) -> list[str]:
        """Format a single structure node."""
        lines = []
        connector = self.LAST_BRANCH if is_last else self.BRANCH

        # Build main line
        parts = [f"{prefix}{connector} {node.type}: {node.name}"]

        # Add signature if available
        if self.show_signatures and hasattr(node, "signature") and node.signature:
            parts.append(node.signature)

        # Add line numbers
        parts.append(f"({node.start_line}-{node.end_line})")

        # Add modifiers if present
        if hasattr(node, "modifiers") and node.modifiers:
            modifiers_str = " ".join(node.modifiers)
            parts.append(f"[{modifiers_str}]")

        lines.append(" ".join(parts))

        # Add decorators on separate lines
        if self.show_decorators and hasattr(node, "decorators") and node.decorators:
            decorator_prefix = prefix + (self.SPACE if is_last else self.VERTICAL) + "  "
            for decorator in node.decorators:
                lines.append(f"{decorator_prefix}{decorator}")

        # Add docstring on separate line
        if self.show_docstrings and hasattr(node, "docstring") and node.docstring:
            docstring_prefix = prefix + (self.SPACE if is_last else self.VERTICAL) + "  "
            lines.append(f'{docstring_prefix}"{node.docstring}"')

        # Format children
        if hasattr(node, "children") and node.children:
            child_prefix = prefix + (self.SPACE if is_last else self.VERTICAL)
            for j, child in enumerate(node.children):
                is_last_child = j == len(node.children) - 1
                lines.extend(self._format_structure_node(child, child_prefix, is_last_child))

        return lines

    def _flatten(self, structures: list[StructureNode]) -> list[StructureNode]:
        """Flatten structure tree to get all nodes."""
        result = []
        for node in structures:
            result.append(node)
            if hasattr(node, "children") and node.children:
                result.extend(self._flatten(node.children))
        return result

    def _flatten_top_level(self, structures: list[StructureNode]) -> list[StructureNode]:
        """
        Create shallow copies of structures without children.

        Returns only top-level classes and functions, stripping nested methods.
        Reduces output by ~50% while maintaining overview.
        """
        flattened = []
        for node in structures:
            # Skip non-code structures (file-info, imports)
            if node.type in ('file-info', 'imports'):
                continue

            # Create shallow copy with no children
            shallow = StructureNode(
                type=node.type,
                name=node.name,
                start_line=node.start_line,
                end_line=node.end_line,
                signature=None,  # Strip signatures for compactness
                decorators=[],   # Strip decorators
                docstring=None,  # Strip docstrings
                complexity=None,
                modifiers=[],
                children=[]  # No children - flattened!
            )
            flattened.append(shallow)
        return flattened
