"""Analyzer for Markdown documentation files."""

import re
from pathlib import Path
from typing import Optional

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class MarkdownAnalyzer(BaseAnalyzer):
    """Analyzer for Markdown files (.md, .markdown, .mdown, .mkd)."""

    @classmethod
    def get_extensions(cls) -> list[str]:
        """File extensions for Markdown."""
        return [".md", ".markdown", ".mdown", ".mkd"]

    @classmethod
    def get_language_name(cls) -> str:
        """Language name."""
        return "Markdown"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip files that should not be analyzed.

        Tier 2 filtering for Markdown-specific patterns.
        """
        filename = Path(file_path).name.lower()

        # Skip common auto-generated documentation
        if filename.endswith(('.generated.md', '.auto.md')):
            return False

        return True

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract imports/references from Markdown file.

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
        """
        Find entry points in Markdown documentation.

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

    def _resolve_markdown_path(self, current_file: str, relative_path: str) -> Optional[str]:
        """
        Resolve relative file-system path in Markdown.

        Args:
            current_file: Path of the Markdown file (e.g., "docs/current/page.md")
            relative_path: Relative file path (e.g., "../other.md", "./file.md")

        Returns:
            Resolved path (normalized, not absolute) or None if cannot resolve
        """
        from pathlib import PurePosixPath

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

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify Markdown file into architectural cluster.

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

        # Documentation directories (check both with and without leading slash)
        path_lower = str(path).lower()
        if '/docs/' in path_lower or path_lower.startswith('docs/'):
            return "documentation"
        if '/documentation/' in path_lower or path_lower.startswith('documentation/'):
            return "documentation"

        # Fall back to base implementation
        return super().classify_file(file_path, content)
