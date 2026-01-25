"""Markdown language support - unified scanner and analyzer.

This module combines MarkdownScanner and MarkdownAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path, PurePosixPath

import tree_sitter_markdown
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class MarkdownLanguage(BaseLanguage):
    """Unified language handler for Markdown files (.md, .markdown, .mdown, .mkd).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract headings and code blocks with hierarchy
    - extract_imports(): Find links, images, and include directives
    - find_entry_points(): Find README files and documentation root headings
    - extract_definitions(): Convert scan() output to DefinitionInfo
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_markdown.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".md", ".markdown", ".mdown", ".mkd"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Markdown"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    def should_analyze(self, file_path: str) -> bool:
        """Skip files that should not be analyzed.

        Tier 2 filtering for Markdown-specific patterns.
        """
        filename = Path(file_path).name.lower()

        # Skip common auto-generated documentation
        if filename.endswith(('.generated.md', '.auto.md')):
            return False

        return True

    # ===========================================================================
    # Structure Scanning (from MarkdownScanner)
    # ===========================================================================

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
                        name="invalid syntax",
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
                    name=text + " (fallback)",
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
                        name=prev_line + " (fallback)",
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
                    name=name + " (fallback)",
                    start_line=line_num,
                    end_line=line_num,
                    signature=language
                )

                if heading_stack:
                    heading_stack[-1][1].children.append(code_block)
                else:
                    structures.append(code_block)

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from MarkdownAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports/references from Markdown file.

        Extracts:
        - Markdown links: [text](file.md), [text](../path/file.md)
        - Images: ![alt](image.png), ![alt](path/to/image.jpg)
        - HTML img tags: <img src="image.png">
        - Include directives: {{include file.md}}, {% include file.md %}
        """
        imports = []

        # Pattern 1: Markdown images ![alt](path) - Process FIRST to avoid duplicate matches
        # Matches: ![diagram](assets/arch.png), ![logo](../images/logo.svg)
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        for match in re.finditer(image_pattern, content):
            image_path = match.group(2).strip()

            # Skip URLs and data URIs
            if '://' in image_path or image_path.startswith('data:'):
                continue

            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=image_path,
                import_type="image",
                line=line
            ))

        # Pattern 2: Markdown links [text](path) - Must NOT match images (![...])
        # Matches: [API Docs](api.md), [Guide](../docs/guide.md)
        # Use negative lookbehind to exclude image syntax
        link_pattern = r'(?<!!)\[([^\]]+)\]\(([^)]+)\)'
        for match in re.finditer(link_pattern, content):
            link_target = match.group(2).strip()

            # Skip URLs (http://, https://, mailto:, etc.)
            if '://' in link_target or link_target.startswith('mailto:'):
                continue

            # Skip anchors only (#section)
            if link_target.startswith('#'):
                continue

            # Remove anchor part (file.md#section -> file.md)
            link_target = link_target.split('#')[0].strip()
            if not link_target:
                continue

            line = content[:match.start()].count('\n') + 1

            # Determine if it's an image or document link based on extension
            is_image = link_target.lower().endswith(('.png', '.jpg', '.jpeg', '.gif',
                                                     '.svg', '.webp', '.bmp', '.ico'))
            import_type = "image" if is_image else "link"

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=link_target,
                import_type=import_type,
                line=line
            ))

        # Pattern 3: HTML img tags <img src="path">
        # Matches: <img src="image.png">, <img src='image.png' alt="text">
        html_img_pattern = r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(html_img_pattern, content, re.IGNORECASE):
            image_path = match.group(1).strip()

            # Skip URLs and data URIs
            if '://' in image_path or image_path.startswith('data:'):
                continue

            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=image_path,
                import_type="image",
                line=line
            ))

        # Pattern 4: Include directives (various formats)
        # Matches: {{include file.md}}, {% include file.md %}, {!file.md!}
        include_patterns = [
            r'\{\{include\s+([^\}]+)\}\}',  # {{include file.md}}
            r'\{%\s*include\s+["\']?([^"\'%]+)["\']?\s*%\}',  # {% include file.md %}
            r'\{!([^!]+)!\}',  # {!file.md!} (MkDocs)
        ]

        for pattern in include_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                include_path = match.group(1).strip().strip('"\'')
                line = content[:match.start()].count('\n') + 1
                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=include_path,
                    import_type="include",
                    line=line
                ))

        # Handle relative imports for Markdown (file-system paths)
        for imp in imports:
            # Markdown links are file-system relative paths (not Python-style imports)
            # Resolve them relative to the file's directory
            if imp.target_module.startswith('../') or imp.target_module.startswith('./'):
                resolved = self._resolve_markdown_path(file_path, imp.target_module)
                if resolved:
                    imp.target_module = resolved

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in Markdown documentation.

        Entry points for Markdown:
        - README.md, INDEX.md (common documentation roots)
        - Files with "# Main" or "# Home" heading (site roots)
        - Files with "# Getting Started" (user entry point)
        """
        entry_points = []
        filename = Path(file_path).name.upper()

        # Pattern 1: Common documentation root files
        if filename in ('README.MD', 'INDEX.MD', 'HOME.MD'):
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="documentation_root",
                name=filename,
                line=1
            ))

        # Pattern 2: Main/Home headings (# Main, # Home, # Getting Started)
        heading_pattern = r'^#\s+(Main|Home|Getting Started|Introduction|Overview)\s*$'
        for match in re.finditer(heading_pattern, content, re.MULTILINE | re.IGNORECASE):
            heading_text = match.group(1)
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="entry_heading",
                name=heading_text,
                line=line
            ))

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2 (reusing scan() output)
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract definitions by reusing scan() output.

        For Markdown, definitions are headings (as they define document structure).
        """
        try:
            structures = self.scan(content.encode("utf-8"))
            if not structures:
                return []
            return self._structures_to_definitions(file_path, structures)
        except Exception:
            return []

    # ===========================================================================
    # Classification (from MarkdownAnalyzer)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify Markdown file into architectural cluster.

        Markdown-specific classification:
        - README* -> entry_points
        - docs/, documentation/ -> documentation cluster
        - Otherwise use base implementation
        """
        path = Path(file_path)
        filename = path.name.upper()

        # README files are entry points
        if filename.startswith('README'):
            return "entry_points"

        # Documentation directories (check path parts for cross-platform compatibility)
        path_parts_lower = [p.lower() for p in path.parts]
        if 'docs' in path_parts_lower or 'documentation' in path_parts_lower:
            return "documentation"

        # Fall back to base implementation
        return super().classify_file(file_path, content)

    # ===========================================================================
    # CodeMap Integration (from MarkdownAnalyzer)
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> Optional[str]:
        """Resolve Markdown link to file path.

        Markdown links to other docs or assets.
        """
        # Skip URLs
        if module.startswith(("http://", "https://", "mailto:", "#")):
            return None

        # Remove anchor if present
        if "#" in module:
            module = module.split("#")[0]

        if not module:
            return None

        # Direct match
        if module in all_files:
            return module

        # Try relative to source file
        source_dir = str(Path(source_file).parent)
        if source_dir != ".":
            candidate = f"{source_dir}/{module}"
            if candidate in all_files:
                return candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format Markdown entry point for display.

        Formats:
        - readme: "README.MD @line"
        - index: "index @line"
        """
        if ep.type == "readme":
            return f"  {ep.file}:README.MD @{ep.line}"
        elif ep.type == "index":
            return f"  {ep.file}:index @{ep.line}"
        else:
            return super().format_entry_point(ep)

    # ===========================================================================
    # Helper methods (Markdown-specific)
    # ===========================================================================

    def _resolve_markdown_path(self, current_file: str, relative_path: str) -> Optional[str]:
        """Resolve relative file-system path in Markdown.

        Args:
            current_file: Path of the Markdown file (e.g., "docs/current/page.md")
            relative_path: Relative file path (e.g., "../other.md", "./file.md")

        Returns:
            Resolved path (normalized, not absolute) or None if cannot resolve
        """
        try:
            # Use PurePosixPath to handle path operations without filesystem access
            current_dir = PurePosixPath(current_file).parent

            # Join and normalize the path (removes .. and .)
            resolved = (current_dir / relative_path)

            # Normalize by converting to string and back
            # This handles .. and . properly
            parts = []
            for part in resolved.parts:
                if part == '..':
                    if parts and parts[-1] != '..':
                        parts.pop()
                    else:
                        parts.append(part)
                elif part != '.':
                    parts.append(part)

            # Join parts back together
            return '/'.join(parts) if parts else '.'
        except (ValueError, IndexError):
            return None
