"""Main file scanner orchestrator using the plugin system."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .languages import BaseLanguage, StructureNode, get_registry
from .gitignore import load_gitignore, GitignoreParser
from .glob_expander import expand_braces


def _estimate_tokens(lines: list[str]) -> int:
    """Rough BPE-token estimate for display lines (~4 chars/token plus
    per-line prefix overhead) — used for budget allocation, not billing."""
    return len("\n".join(lines)) // 4 + len(lines)


class FileScanner:
    """Main scanner that delegates to language-specific scanner plugins."""

    # Skeleton depth for candidate nodes outside the full-display tier —
    # depth-2 measured as best fact-coverage per token (experiments/entropy_metrics/)
    BROAD_TIER_DEPTH = 2

    def __init__(self, show_errors: bool = True, fallback_on_errors: bool = True):
        """
        Initialize file scanner.

        Args:
            show_errors: Show parse error nodes in output
            fallback_on_errors: Use regex fallback for severely broken files
        """
        self.registry = get_registry()
        self.show_errors = show_errors
        self.fallback_on_errors = fallback_on_errors

    def scan_content(
        self,
        content: str | bytes,
        filename: str,
        include_metadata: bool = False
    ) -> Optional[list[StructureNode]]:
        """
        Scan file content directly without requiring a file path.

        Useful for scanning remote files (e.g., from GitHub) or content from APIs.

        Args:
            content: File content as string or bytes
            filename: Filename (used to determine language/scanner type)
            include_metadata: Include basic metadata node (just filename and size)

        Returns:
            List of StructureNode objects, or None if file type not supported
        """
        # Get file extension from filename
        path = Path(filename)
        suffix = path.suffix.lower()

        # Get appropriate scanner for this file type
        scanner_class = self.registry.get_scanner(suffix)

        if not scanner_class:
            return None  # Unsupported file type

        # Create scanner instance with options
        scanner = scanner_class(
            show_errors=self.show_errors,
            fallback_on_errors=self.fallback_on_errors
        )

        # Convert content to bytes if needed
        if isinstance(content, str):
            source_code = content.encode('utf-8')
        else:
            source_code = content

        # Scan using the appropriate plugin
        structures = scanner.scan(source_code)

        # Prepend metadata if requested and structures exist
        if include_metadata and structures is not None:
            size_bytes = len(source_code)
            if size_bytes < 1024:
                size_str = f"{size_bytes}B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f}KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f}MB"

            file_info = StructureNode(
                type="file-info",
                name=path.name,
                start_line=1,
                end_line=1,
                file_metadata={
                    "size": size_bytes,
                    "size_formatted": size_str,
                    "source": "content",
                }
            )
            structures = [file_info] + structures

        return structures

    def scan_file(
        self,
        file_path: str,
        include_file_metadata: bool = True,
        budget: Optional[int] = None,
        line_edits: Optional[dict[int, str]] = None
    ) -> Optional[list[StructureNode]]:
        """
        Scan a single file and return its structure.

        Args:
            file_path: Path to the file to scan
            include_file_metadata: Include file metadata (size, timestamps) as first node
            budget: Approximate token cap for code skeletons — the least
                salient nodes degrade (full → depth-2 → depth-1 → header
                only) until the estimate fits. None = no cap.
            line_edits: line number -> commit id for recently edited lines
                (from git_signals.recent_line_edits); boosts actively-worked
                nodes in selection and sets "[N edits/90d]" labels

        Returns:
            List of StructureNode objects, or None if file type not supported
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get appropriate scanner for this file type
        suffix = path.suffix.lower()
        scanner_class = self.registry.get_scanner(suffix)

        if not scanner_class:
            return None  # Unsupported file type

        # Get file metadata
        file_stats = os.stat(file_path)

        # Create scanner instance with options
        scanner = scanner_class(
            show_errors=self.show_errors,
            fallback_on_errors=self.fallback_on_errors
        )

        # Read file
        with open(file_path, "rb") as f:
            source_code = f.read()

        # Scan using the appropriate plugin
        structures = scanner.scan(source_code)

        # Entropy-based saliency analysis (annotate high-importance code regions)
        # Skip for binary/non-code files where entropy analysis is meaningless
        binary_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.pdf'}
        if structures is not None and suffix not in binary_extensions:
            self._annotate_salient_code(structures, file_path, source_code,
                                        language=scanner, budget=budget,
                                        line_edits=line_edits)

        # Prepend file metadata if requested and structures exist
        if include_file_metadata and structures is not None:
            # Format file size
            size_bytes = file_stats.st_size
            if size_bytes < 1024:
                size_str = f"{size_bytes}B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f}KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f}MB"

            # Create file info node
            file_info = StructureNode(
                type="file-info",
                name=path.name,
                start_line=1,
                end_line=1,
                file_metadata={
                    "size": size_bytes,
                    "size_formatted": size_str,
                    "created": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                    "permissions": oct(file_stats.st_mode)[-3:],
                }
            )
            structures = [file_info] + structures

        return structures

    # Display level degradation order: full tier loses depth before the
    # broad tier loses breadth — depth-2 outlines measured as the most
    # fact-dense representation (experiments/entropy_metrics/)
    _LEVEL_DOWN = {"full": 2, 2: 1, 1: 0}

    @staticmethod
    def _annotate_node_edits(structures: list, line_edits: dict[int, str]) -> None:
        """Per-node edit-count labels from a blame line map. Labels are only
        set when they discriminate — a uniform value across all nodes (e.g.
        a freshly created file) repeats the file-level churn and carries no
        information."""
        eligible: list[tuple] = []

        def walk(nodes):
            for node in nodes:
                if node.type != "file-info" and node.name and node.end_line >= node.start_line:
                    commits = {line_edits[line]
                               for line in range(node.start_line, node.end_line + 1)
                               if line in line_edits}
                    eligible.append((node, len(commits)))
                if node.children:
                    walk(node.children)

        walk(structures)
        if len({count for _, count in eligible}) <= 1:
            return
        for node, count in eligible:
            if count:
                node.recent_edits = count

    def _annotate_salient_code(
        self,
        structures: list[StructureNode],
        file_path: str,
        source_code: bytes,
        top_percent: float = 0.20,
        language=None,
        budget: Optional[int] = None,
        line_edits: Optional[dict[int, str]] = None
    ) -> None:
        """
        Annotate structure nodes with code in tiers by saliency, optionally
        within an approximate token budget.

        Nodes are scored directly on their byte ranges (entropy, conditional
        new information, centrality). Without budget: the top N% get full
        display (verbatim excerpt + full-depth skeleton), every other
        candidate a depth-2 outline. With budget: same starting point, then
        the least salient nodes degrade (full → d2 → d1 → header only)
        until the estimated skeleton cost fits — token allocation IS
        prioritization, and the budget makes it explicit.

        Args:
            structures: List of StructureNode objects to annotate
            file_path: Path to the file being analyzed (for error messages)
            source_code: Raw source code bytes
            top_percent: Share of candidates given full display (default: top 20%)
            language: BaseLanguage instance used to condense excerpts to skeletons (optional)
            budget: Approximate token cap for skeleton content (None = no cap)
        """
        try:
            from .entropy import select_salient_nodes
            from .languages.base import limit_skeleton_depth

            source_lines = source_code.decode('utf-8', errors='replace').split('\n')

            ranked = select_salient_nodes(source_code, structures, top_percent=1.0,
                                          line_edits=line_edits)
            if not ranked:
                return
            if line_edits:
                self._annotate_node_edits(structures, line_edits)
            full_count = max(1, int(len(ranked) * top_percent))
            # Compact-strategy skeletons (declarative content) are never
            # depth-cut — their downgrade path is skeleton → nothing
            is_compact = getattr(language, "CONDENSE_STRATEGY", None) == "compact"

            items = []
            for node, score in ranked:
                start_idx = max(0, node.start_line - 1)
                end_idx = min(len(source_lines), node.end_line)
                excerpt = source_lines[start_idx:end_idx]
                skeleton = language.condense_excerpt(excerpt) if language is not None else None
                items.append((node, score, excerpt, skeleton))

            levels: list = ["full" if i < full_count else self.BROAD_TIER_DEPTH
                            for i in range(len(items))]

            if budget is not None:
                def cost(i, level):
                    _, _, excerpt, skeleton = items[i]
                    if level == 0:
                        return 0
                    if skeleton is None:
                        # verbatim fallback exists only at full level
                        return _estimate_tokens(excerpt) if level == "full" else 0
                    if level == "full" or is_compact:
                        return _estimate_tokens(skeleton)
                    return _estimate_tokens(limit_skeleton_depth(skeleton, level))

                total = sum(cost(i, levels[i]) for i in range(len(items)))
                for from_level in ("full", 2, 1):
                    for i in reversed(range(len(items))):
                        if total <= budget:
                            break
                        if levels[i] == from_level:
                            total -= cost(i, levels[i])
                            levels[i] = self._LEVEL_DOWN[from_level]
                            total += cost(i, levels[i])
                    if total <= budget:
                        break

            for i, (node, score, excerpt, skeleton) in enumerate(items):
                level = levels[i]
                if level == 0:
                    continue
                if level == "full":
                    # Full tier: verbatim excerpt (shown when condense=False)
                    # + full-depth skeleton
                    node.code_excerpt = excerpt
                    node.saliency = score
                    if skeleton:
                        node.code_skeleton = skeleton
                elif skeleton:
                    shallow = skeleton if is_compact else limit_skeleton_depth(skeleton, level)
                    # all-fold skeletons ("…" only) carry no information
                    if any(line.strip() != "…" for line in shallow):
                        node.code_skeleton = shallow
                        node.saliency = score

        except Exception as e:
            # Fail gracefully if entropy analysis fails (e.g., file too small, import error)
            if self.show_errors:
                import sys
                print(f"Warning: Entropy analysis failed for {file_path}: {e}", file=sys.stderr)

    def scan_directory(
        self,
        directory: str,
        pattern: str = "**/*",
        respect_gitignore: bool = True,
        exclude_patterns: Optional[list[str]] = None
    ) -> dict[str, Optional[list[StructureNode]]]:
        """
        Scan all supported files in a directory.

        Args:
            directory: Directory path to scan
            pattern: Glob pattern for files (use "**/*" for recursive, "*" for current dir only)
            respect_gitignore: Respect .gitignore exclusions (default: True)
            exclude_patterns: Additional patterns to exclude (gitignore syntax)

        Returns:
            Dictionary mapping file paths to their structures
        """
        results = {}
        dir_path = Path(directory).resolve()

        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        # Load gitignore if requested
        gitignore = load_gitignore(dir_path) if respect_gitignore else None

        # Default exclusions - always applied
        default_exclusions = [
            # Files
            '.DS_Store',      # macOS
            'Thumbs.db',      # Windows
            'desktop.ini',    # Windows
            '.localized',     # macOS
            # Directories (universal noise)
            'node_modules/',  # Node.js dependencies
            '__pycache__/',   # Python bytecode
            '.pytest_cache/', # pytest cache
            'dist/',          # Build output
            'build/',         # Build output
            'target/',        # Rust/Java/Kotlin build
            '*.egg-info/',    # Python package metadata
            '.venv/',         # Python virtual env
            'venv/',          # Python virtual env
            '.next/',         # Next.js build
            '.nuxt/',         # Nuxt build
            'coverage/',      # Test coverage
            '.coverage/',     # Coverage reports
            '.ruff_cache/',   # Ruff cache
            '.mypy_cache/',   # MyPy cache
        ]

        # Combine defaults with user-provided exclusions
        all_exclude_patterns = default_exclusions.copy()
        if exclude_patterns:
            all_exclude_patterns.extend(exclude_patterns)

        # Parse exclusion patterns
        exclude_parser = GitignoreParser(all_exclude_patterns) if all_exclude_patterns else None

        # Expand brace patterns (e.g., "**/*.{py,js}" → ["**/*.py", "**/*.js"])
        expanded_patterns = expand_braces(pattern)

        # Process each expanded pattern
        seen_files = set()  # Avoid duplicates if patterns overlap
        for expanded_pattern in expanded_patterns:
            for file_path in dir_path.glob(expanded_pattern):
                if not file_path.is_file():
                    continue

                # Skip if already processed
                file_str = str(file_path)
                if file_str in seen_files:
                    continue
                seen_files.add(file_str)

                # Check exclusions
                try:
                    rel_path = str(file_path.relative_to(dir_path))
                except ValueError:
                    # File outside base directory
                    continue

                # Skip files inside hidden directories (directories starting with .)
                # But allow hidden files themselves (e.g., .gitignore, .python-version)
                path_parts = Path(rel_path).parts
                if any(part.startswith('.') and part not in [file_path.name] for part in path_parts):
                    # File is inside a hidden directory, skip it
                    continue

                # Check gitignore
                if gitignore and gitignore.matches(rel_path, file_path.is_dir()):
                    continue

                # Check additional exclusions
                if exclude_parser and exclude_parser.matches(rel_path, file_path.is_dir()):
                    continue

                # Check if we have a scanner for this file type
                scanner_class = self.registry.get_scanner(file_path.suffix.lower())
                if scanner_class:
                    # Check if scanner wants to skip this file
                    if scanner_class.should_skip(file_path.name):
                        continue

                    try:
                        results[file_str] = self.scan_file(file_str)
                    except Exception as e:
                        # Continue scanning even if one file fails
                        results[file_str] = [StructureNode(
                            type="error",
                            name=f"Failed to scan: {str(e)}",
                            start_line=1,
                            end_line=1
                        )]
                else:
                    # Unsupported file type - include with basic metadata only
                    try:
                        file_stats = os.stat(file_str)
                        size_bytes = file_stats.st_size
                        if size_bytes < 1024:
                            size_str = f"{size_bytes}B"
                        elif size_bytes < 1024 * 1024:
                            size_str = f"{size_bytes / 1024:.1f}KB"
                        else:
                            size_str = f"{size_bytes / (1024 * 1024):.1f}MB"

                        results[file_str] = [StructureNode(
                            type="file-info",
                            name=file_path.name,
                            start_line=1,
                            end_line=1,
                            file_metadata={
                                "size": size_bytes,
                                "size_formatted": size_str,
                                "extension": file_path.suffix or "(no extension)",
                                "modified": datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                                "unsupported": True
                            }
                        )]
                    except Exception:
                        # If we can't even get metadata, skip the file
                        continue

        return results

    def get_supported_extensions(self) -> list[str]:
        """Get list of all supported file extensions."""
        return self.registry.get_supported_extensions()

    def get_scanner_info(self) -> dict[str, str]:
        """Get mapping of extensions to language names."""
        return self.registry.get_scanner_info()


# For backward compatibility, export StructureNode
__all__ = ["FileScanner", "StructureNode"]
