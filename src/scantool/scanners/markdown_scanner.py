"""Scanner for Markdown files."""

import re
from typing import Optional

import tree_sitter_markdown
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class MarkdownScanner(BaseScanner):
    """Scanner for Markdown files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_markdown.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".md", ".markdown", ".mdown", ".mkd"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Markdown"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Markdown source and extract structure with metadata."""
        try:
            tree = self.parser.parse(source_code)

            # Check if we should use fallback due to too many errors
            if self._should_use_fallback(tree.root_node):
                return self._fallback_extract(source_code)

            return self._extract_structure(tree.root_node, source_code)

        except Exception as e:
            # Return error node instead of crashing
            return [StructureNode(
                type="error",
                name=f"Failed to parse: {str(e)}",
                start_line=1,
                end_line=1
            )]

    def _extract_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract hierarchical structure from Markdown."""
        structures = []

        # Build hierarchy based on heading levels
        heading_stack: list[tuple[int, StructureNode]] = []  # (level, node)

        def add_node_to_hierarchy(level: int, node: StructureNode):
            """Add a node to the appropriate level in the hierarchy."""
            # Pop all headings at same or deeper level
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            if heading_stack:
                # Add as child to the current parent
                heading_stack[-1][1].children.append(node)
            else:
                # Top-level structure
                structures.append(node)

            # Add to stack if it's a heading (can have children)
            if node.type.startswith("heading"):
                heading_stack.append((level, node))

        def traverse(node: Node):
            """Traverse tree and extract structures."""
            # Handle parse errors
            if node.type == "ERROR":
                if self.show_errors:
                    error_node = StructureNode(
                        type="parse-error",
                        name="⚠ invalid syntax",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1
                    )
                    # Add to current parent or root
                    if heading_stack:
                        heading_stack[-1][1].children.append(error_node)
                    else:
                        structures.append(error_node)
                return

            # ATX headings (# style)
            if node.type == "atx_heading":
                heading_node = self._extract_atx_heading(node, source_code)
                level = self._get_heading_level(node)
                add_node_to_hierarchy(level, heading_node)
                return  # Don't traverse children, we already got the text

            # Setext headings (underline style)
            elif node.type == "setext_heading":
                heading_node = self._extract_setext_heading(node, source_code)
                level = self._get_setext_level(node, source_code)
                add_node_to_hierarchy(level, heading_node)
                return  # Don't traverse children

            # Fenced code blocks (```language)
            elif node.type == "fenced_code_block":
                code_block = self._extract_fenced_code_block(node, source_code)
                if heading_stack:
                    heading_stack[-1][1].children.append(code_block)
                else:
                    structures.append(code_block)
                return

            # Indented code blocks (4 spaces)
            elif node.type == "indented_code_block":
                code_block = self._extract_indented_code_block(node, source_code)
                if heading_stack:
                    heading_stack[-1][1].children.append(code_block)
                else:
                    structures.append(code_block)
                return

            # Continue traversing for other nodes
            for child in node.children:
                traverse(child)

        traverse(root)

        # Fix end_line for all headings to include their content
        self._fix_heading_ranges(structures, source_code)

        return structures

    def _fix_heading_ranges(self, structures: list[StructureNode], source_code: bytes):
        """Fix end_line for headings to include their content sections."""
        total_lines = len(source_code.decode('utf-8', errors='replace').split('\n'))

        def fix_node(node: StructureNode, next_sibling_start: Optional[int] = None):
            """Recursively fix end_line for a node and its children."""
            if not node.type.startswith("heading"):
                return

            # Process children first
            if node.children:
                for i, child in enumerate(node.children):
                    # Next sibling's start line (or parent's end if no next sibling)
                    if i + 1 < len(node.children):
                        next_start = node.children[i + 1].start_line
                    else:
                        next_start = next_sibling_start
                    fix_node(child, next_start)

                # Set this heading's end_line to just before the first child's start
                # or to the last child's end_line
                last_child = node.children[-1]
                node.end_line = last_child.end_line
            elif next_sibling_start is not None:
                # No children, extend to just before next sibling
                node.end_line = next_sibling_start - 1
            else:
                # No children and no next sibling, extend to end of file
                node.end_line = total_lines

        # Fix all top-level structures
        for i, structure in enumerate(structures):
            if i + 1 < len(structures):
                next_start = structures[i + 1].start_line
            else:
                next_start = None
            fix_node(structure, next_start)

    def _extract_atx_heading(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract ATX-style heading (# Heading)."""
        level = self._get_heading_level(node)

        # Get heading text (excluding the # markers)
        text = self._get_heading_text(node, source_code)

        return StructureNode(
            type=f"heading-{level}",
            name=text or "(empty heading)",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            children=[]
        )

    def _extract_setext_heading(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract Setext-style heading (underlined with = or -)."""
        level = self._get_setext_level(node, source_code)

        # Get the heading text (first line, before underline)
        text = self._get_heading_text(node, source_code)

        return StructureNode(
            type=f"heading-{level}",
            name=text or "(empty heading)",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            children=[]
        )

    def _extract_fenced_code_block(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract fenced code block with language identifier."""
        # Try to get language from info_string
        language = None
        for child in node.children:
            if child.type == "info_string":
                lang_text = self._get_node_text(child, source_code).strip()
                if lang_text:
                    language = lang_text
                break

        # Create a descriptive name
        if language:
            name = f"code block ({language})"
        else:
            name = "code block"

        return StructureNode(
            type="code-block",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=language  # Store language in signature field
        )

    def _extract_indented_code_block(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract indented code block (4 spaces)."""
        return StructureNode(
            type="code-block",
            name="code block (indented)",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1
        )

    def _get_heading_level(self, node: Node) -> int:
        """Get the level of an ATX heading by counting # markers."""
        for child in node.children:
            if child.type == "atx_h1_marker":
                return 1
            elif child.type == "atx_h2_marker":
                return 2
            elif child.type == "atx_h3_marker":
                return 3
            elif child.type == "atx_h4_marker":
                return 4
            elif child.type == "atx_h5_marker":
                return 5
            elif child.type == "atx_h6_marker":
                return 6
        return 1  # Default

    def _get_setext_level(self, node: Node, source_code: bytes) -> int:
        """Get the level of a Setext heading (1 for =, 2 for -)."""
        # Look for the underline child
        for child in node.children:
            if child.type == "setext_h1_underline":
                return 1
            elif child.type == "setext_h2_underline":
                return 2
        return 1  # Default

    def _get_heading_text(self, node: Node, source_code: bytes) -> str:
        """Extract the text content of a heading."""
        # For ATX headings, use the heading_content field
        content = node.child_by_field_name("heading_content")
        if content:
            return self._get_node_text(content, source_code).strip()

        # For Setext headings, get text from inline nodes
        for child in node.children:
            if child.type == "inline":
                return self._get_node_text(child, source_code).strip()

        # Fallback: get all text except underlines and markers
        text_parts = []
        for child in node.children:
            if child.type not in ("setext_h1_underline", "setext_h2_underline",
                                 "atx_h1_marker", "atx_h2_marker", "atx_h3_marker",
                                 "atx_h4_marker", "atx_h5_marker", "atx_h6_marker"):
                text_parts.append(self._get_node_text(child, source_code))

        text = "".join(text_parts).strip()
        # Remove any trailing newlines
        text = text.split('\n')[0].strip()
        return text

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for malformed Markdown files."""
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        lines = text.split('\n')
        heading_stack: list[tuple[int, StructureNode]] = []

        for i, line in enumerate(lines):
            line_num = i + 1

            # ATX headings
            atx_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if atx_match:
                level = len(atx_match.group(1))
                text = atx_match.group(2).strip()

                heading = StructureNode(
                    type=f"heading-{level}",
                    name=text + " ⚠",
                    start_line=line_num,
                    end_line=line_num,
                    children=[]
                )

                # Handle hierarchy
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                if heading_stack:
                    heading_stack[-1][1].children.append(heading)
                else:
                    structures.append(heading)

                heading_stack.append((level, heading))
                continue

            # Setext heading (=== or ---)
            if i > 0 and re.match(r'^[=\-]{3,}$', line.strip()):
                prev_line = lines[i - 1].strip()
                if prev_line:
                    level = 1 if '=' in line else 2

                    heading = StructureNode(
                        type=f"heading-{level}",
                        name=prev_line + " ⚠",
                        start_line=i,  # Previous line
                        end_line=line_num,
                        children=[]
                    )

                    # Handle hierarchy
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()

                    if heading_stack:
                        heading_stack[-1][1].children.append(heading)
                    else:
                        structures.append(heading)

                    heading_stack.append((level, heading))
                continue

            # Fenced code blocks
            fence_match = re.match(r'^```(\w+)?', line)
            if fence_match:
                language = fence_match.group(1)
                name = f"code block ({language})" if language else "code block"

                code_block = StructureNode(
                    type="code-block",
                    name=name + " ⚠",
                    start_line=line_num,
                    end_line=line_num,
                    signature=language
                )

                if heading_stack:
                    heading_stack[-1][1].children.append(code_block)
                else:
                    structures.append(code_block)

        return structures
