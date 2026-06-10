"""Base language class that unifies scanner and analyzer functionality.

This module provides the BaseLanguage class that combines:
- Structure scanning (tree-sitter based AST extraction)
- Semantic analysis (imports, entry points, definitions, calls)

Each language implementation inherits from BaseLanguage and provides
a single file per language instead of separate scanner + analyzer files.
"""

import re
import textwrap
from abc import ABC, abstractmethod
from typing import Optional

from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)

# ===========================================================================
# Excerpt condensation (shared machinery for condense_excerpt)
# ===========================================================================

# Node types that carry intent/method, matched against tree-sitter type names
# across grammars (if_statement, call_expression, method_invocation,
# let_declaration, ...). Underscores are normalized to spaces before matching.
_SIGNIFICANT_NODE = re.compile(
    r"\b(if|else|elif|for|foreach|while|do|switch|case|match|when|guard|loop"
    r"|try|catch|except|finally|return|break|continue|throw|raise|yield|defer"
    r"|call|invocation|invoke|new|await|macro"
    r"|assignment|augmented"
    r"|function|method|class|struct|enum|interface|impl|trait|lambda|closure"
    r"|let|const|short_var|local)\b"
)

# Lines containing only closing syntax/punctuation — dropped silently
# (nesting stays visible through indentation, as in Python)
_PUNCT_ONLY_LINE = re.compile(r"^[\s)\]}>;,]*$")

# Field names pointing at a node's body — lines from node start to body start
# form the header (multi-line conditions/signatures) and are kept together
_BODY_FIELDS = ("body", "consequence", "block")


def limit_skeleton_depth(skeleton: list[str], max_depth: int) -> list[str]:
    """Cut skeleton lines nested deeper than max_depth levels.

    Indentation widths are mapped to nesting levels by rank, so this works
    for 1-space AST skeletons and tab/2/4-space generic skeletons alike.
    Cut blocks leave a single "…" marker. Measured rationale: shallow
    skeletons are fact-dense — see experiments/entropy_metrics/.
    """
    def width(line: str) -> int:
        ws = line[: len(line) - len(line.lstrip())]
        return len(ws.expandtabs(4))

    levels = {w: rank for rank, w in enumerate(sorted({width(l) for l in skeleton}))}

    out: list[str] = []
    marker = " " * max_depth + "…"
    for line in skeleton:
        if levels[width(line)] < max_depth:
            out.append(line)
        elif not out or out[-1] != marker:
            out.append(marker)
    return out


class BaseLanguage(ABC):
    """Unified base class for language support.

    Combines the functionality of BaseScanner and BaseAnalyzer into a single
    interface. Each language provides one implementation file that handles
    both structure scanning and semantic analysis.

    Key methods:
    - scan(): Extract structure (classes, functions, methods) from source
    - extract_imports(): Find import statements
    - find_entry_points(): Find main functions, exports, etc.
    - extract_definitions(): Get function/class definitions (can reuse scan())
    - extract_calls(): Find function/method calls
    """

    def __init__(self, show_errors: bool = True, fallback_on_errors: bool = True):
        """Initialize language handler with error handling options.

        Args:
            show_errors: Include ERROR nodes in output
            fallback_on_errors: Use regex fallback if too many parse errors
        """
        self.show_errors = show_errors
        self.fallback_on_errors = fallback_on_errors

    # ===========================================================================
    # Metadata (REQUIRED - classmethod)
    # ===========================================================================

    @classmethod
    @abstractmethod
    def get_extensions(cls) -> list[str]:
        """Return list of file extensions this language handles.

        Examples:
            ['.py', '.pyw']  # Python
            ['.ts', '.tsx']  # TypeScript
            ['.swift']       # Swift
        """
        pass

    @classmethod
    @abstractmethod
    def get_language_name(cls) -> str:
        """Return the human-readable language name.

        Examples: 'Python', 'TypeScript', 'Swift'
        """
        pass

    @classmethod
    def get_priority(cls) -> int:
        """Return priority for this language (higher = preferred).

        Used when multiple languages claim the same extension.
        Default: 0
        """
        return 0

    # ===========================================================================
    # Skip/Filter Logic (OPTIONAL - combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Check if file should be skipped for scanning.

        Override to skip files like:
        - __init__.py (Python empty init files)
        - *.min.js (JavaScript minified files)
        - *.d.ts (TypeScript declaration files)

        Args:
            filename: Just the filename (not full path)

        Returns:
            True if file should be skipped (not scanned)
        """
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Check if file should be analyzed for semantic information.

        Override to skip certain files from import/entry point analysis.
        This is similar to should_skip but operates on full paths and
        is called during CodeMap analysis.

        Args:
            file_path: Relative path to the file

        Returns:
            True if file should be analyzed
        """
        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Check if file is low-value for inventory listing.

        Unlike should_analyze (which skips analysis entirely), this identifies
        files that CAN be analyzed but are low-value for overview displays.
        Used by preview_directory to filter noise.

        NOTE: Central/hot files should NEVER be excluded, regardless of
        this method's return value. Caller must check centrality.

        Override for patterns like:
        - Empty __init__.py (Python)
        - Type declarations *.d.ts (TypeScript)
        - Re-export index files

        Args:
            file_path: Relative path to the file
            size: File size in bytes (0 = unknown)

        Returns:
            True if file is low-value for inventory (can be hidden)
        """
        if size > 0 and size < 50:
            return True
        return False

    # ===========================================================================
    # Structure Scanning (REQUIRED - from BaseScanner)
    # ===========================================================================

    @abstractmethod
    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan source code and extract structure.

        This is the primary scanning method that extracts classes, functions,
        methods, and other structural elements from source code.

        Args:
            source_code: Raw file content as bytes

        Returns:
            List of StructureNode objects representing the file structure,
            or None if the file couldn't be parsed
        """
        pass

    #: Condensation strategy for salient excerpts:
    #: - None: no condensation, verbatim display (prose, config — every line
    #:   is content)
    #: - "skeleton": fold-by-default; keep lines where significant nodes start
    #:   (imperative languages with control flow)
    #: - "compact": keep-by-default; drop only blanks, comment-only lines and
    #:   closing punctuation (declarative languages — CSS, SQL — where
    #:   "trivial" lines ARE the content)
    CONDENSE_STRATEGY: Optional[str] = None

    def _fragment_prefix(self) -> str:
        """Prefix needed for a detached excerpt to parse (e.g. PHP's '<?php')."""
        return ""

    def condense_excerpt(self, excerpt_lines: list[str]) -> Optional[list[str]]:
        """Condense a salient code excerpt into a compact skeleton.

        Abstractive alternative to verbatim excerpts, driven by
        CONDENSE_STRATEGY and the language's tree-sitter parser (regex-only
        languages fall back to verbatim). Python overrides this with an
        AST-based variant. Measurements in experiments/condensation/.

        Args:
            excerpt_lines: The excerpt as source lines (one node's region)

        Returns:
            Skeleton lines, or None to fall back to verbatim display
        """
        parser = getattr(self, "parser", None)
        if self.CONDENSE_STRATEGY is None or parser is None:
            return None

        source = textwrap.dedent("\n".join(excerpt_lines))
        lines = source.split("\n")
        prefix = self._fragment_prefix()
        try:
            tree = parser.parse((prefix + source).encode("utf-8", errors="replace"))
        except Exception:
            return None
        offset = prefix.count("\n")

        if self.CONDENSE_STRATEGY == "skeleton":
            out, folded = self._skeleton_lines(tree, lines, offset)
        else:
            out, folded = self._compact_lines(tree, lines, offset)

        # Nothing recognized or nothing saved → verbatim (with line numbers)
        # is strictly better
        if not out or not folded:
            return None
        return out

    def _skeleton_lines(self, tree, lines: list[str], offset: int) -> tuple[list[str], bool]:
        """Fold-by-default: keep rows where significant nodes start."""
        keep = self._significant_rows(tree, offset, len(lines))
        if not keep:
            return [], False

        out: list[str] = []
        folded = False
        for i, line in enumerate(lines):
            if _PUNCT_ONLY_LINE.match(line):
                folded = folded or bool(line.strip())
                continue
            if i in keep:
                out.append(line.rstrip())
            else:
                folded = True
                indent = len(line) - len(line.lstrip())
                if not out or out[-1].strip() != "…":
                    out.append(" " * indent + "…")
        return out, folded

    def _compact_lines(self, tree, lines: list[str], offset: int) -> tuple[list[str], bool]:
        """Keep-by-default: drop blanks, comment-only lines and closers."""
        comment_rows = self._comment_only_rows(tree, lines, offset)

        out: list[str] = []
        folded = False
        for i, line in enumerate(lines):
            if _PUNCT_ONLY_LINE.match(line):
                folded = folded or bool(line.strip())
                continue
            if i in comment_rows:
                folded = True
                indent = len(line) - len(line.lstrip())
                if not out or out[-1].strip() != "…":
                    out.append(" " * indent + "…")
            else:
                out.append(line.rstrip())
        return out, folded

    def _significant_rows(self, tree, offset: int, n_lines: int) -> set[int]:
        """Rows where information-bearing nodes start (incl. multi-line headers)."""
        rows: set[int] = set()
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if _SIGNIFICANT_NODE.search(node.type.replace("_", " ")):
                start = node.start_point[0] - offset
                end = start
                for field in _BODY_FIELDS:
                    body = node.child_by_field_name(field)
                    if body is not None:
                        body_row = body.start_point[0] - offset
                        if body_row > start:
                            end = body_row - 1
                        break
                rows.update(range(max(0, start), min(end, n_lines - 1) + 1))
            stack.extend(node.children)
        return rows

    def _comment_only_rows(self, tree, lines: list[str], offset: int) -> set[int]:
        """Rows whose entire non-whitespace content lies inside a comment."""
        rows: set[int] = set()
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            if "comment" in node.type:
                r1, c1 = node.start_point[0] - offset, node.start_point[1]
                r2, c2 = node.end_point[0] - offset, node.end_point[1]
                for row in range(max(0, r1), min(r2, len(lines) - 1) + 1):
                    line = lines[row]
                    if not line.strip():
                        continue
                    first = len(line) - len(line.lstrip())
                    last = len(line.rstrip())
                    starts_before = row > r1 or c1 <= first
                    ends_after = row < r2 or c2 >= last
                    if starts_before and ends_after:
                        rows.add(row)
            else:
                stack.extend(node.children)
        return rows

    # ===========================================================================
    # Semantic Analysis - Layer 1 (REQUIRED - from BaseAnalyzer)
    # ===========================================================================

    @abstractmethod
    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract import statements from file.

        Args:
            file_path: Relative path to the file
            content: File content as string

        Returns:
            List of ImportInfo objects
        """
        pass

    @abstractmethod
    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in the file.

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

    # ===========================================================================
    # Semantic Analysis - Layer 2 (OPTIONAL - default implementations)
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract function/class definitions from file.

        Default implementation converts scan() output to DefinitionInfo.
        Override for more precise control or when scan() isn't suitable.

        Args:
            file_path: Relative path to the file
            content: File content as string

        Returns:
            List of DefinitionInfo objects
        """
        try:
            structures = self.scan(content.encode("utf-8"))
            if not structures:
                return []
            return self._structures_to_definitions(file_path, structures)
        except Exception:
            # Fallback to regex-based extraction
            return self._extract_definitions_regex(file_path, content)

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Regex fallback when scan() fails. Default: no fallback."""
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Extract function/method calls from file.

        Default implementation parses with tree-sitter and delegates to
        _extract_calls_tree_sitter, with _extract_calls_regex as fallback
        for malformed files. Languages without a parser or those hooks
        yield no calls (no call graph).

        Args:
            file_path: Relative path to the file
            content: File content as string
            definitions: List of known definitions from this file

        Returns:
            List of CallInfo objects
        """
        parser = getattr(self, "parser", None)
        ts_hook = getattr(self, "_extract_calls_tree_sitter", None)
        if parser is None or ts_hook is None:
            return []
        try:
            source_bytes = content.encode("utf-8")
            tree = parser.parse(source_bytes)
            return ts_hook(file_path, tree.root_node, source_bytes, definitions)
        except Exception:
            regex_hook = getattr(self, "_extract_calls_regex", None)
            return regex_hook(file_path, content, definitions) if regex_hook else []

    def _structures_to_definitions(
        self, file_path: str, structures: list[StructureNode], parent: str = None
    ) -> list[DefinitionInfo]:
        """Convert StructureNode list to DefinitionInfo list.

        Helper for default extract_definitions() implementation.
        """
        definitions = []

        for node in structures:
            if node.type in ("class", "function", "method"):
                definitions.append(
                    DefinitionInfo(
                        file=file_path,
                        type=node.type,
                        name=node.name,
                        line=node.start_line,
                        signature=node.signature,
                        parent=parent,
                    )
                )

            # Recurse into children
            if node.children:
                child_parent = node.name if node.type == "class" else parent
                definitions.extend(
                    self._structures_to_definitions(file_path, node.children, child_parent)
                )

        return definitions

    # ===========================================================================
    # Classification (OPTIONAL)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify file into architectural cluster.

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
        path_lower = file_path.lower()
        name = file_path.split("/")[-1].lower()

        # Entry points
        entry_names = [
            "main.py", "server.py", "app.py", "__main__.py",
            "index.ts", "main.tsx", "app.tsx", "main.go"
        ]
        if name in entry_names:
            return "entry_points"

        # Tests
        if name.startswith("test_") or "_test." in name or "/tests/" in path_lower:
            return "tests"

        # Config
        config_names = ["config.py", "settings.py", "constants.py", "config.ts", "settings.ts"]
        if name in config_names:
            return "config"

        # Plugins
        plugin_dirs = ["/scanners/", "/plugins/", "/extensions/", "/languages/"]
        if any(plugin_dir in path_lower for plugin_dir in plugin_dirs):
            return "plugins"

        # Utilities
        if "/utils/" in path_lower or "/helpers/" in path_lower or "utils." in name or "helper." in name:
            return "utilities"

        # Core logic
        core_keywords = ["scanner", "parser", "formatter", "analyzer", "processor", "engine"]
        if any(keyword in name for keyword in core_keywords):
            return "core_logic"

        return "other"

    # ===========================================================================
    # CodeMap Integration (OPTIONAL)
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> Optional[str]:
        """Resolve import module to actual file path.

        Override for language-specific resolution:
        - Python: dot.separated.module -> path/to/module.py
        - Swift: Type references -> file defining Type
        - Go: github.com/pkg -> pkg/file.go
        - TypeScript: ./relative -> relative.ts or relative/index.ts

        Args:
            module: Module/type name to resolve
            source_file: Path of file doing the import
            all_files: List of all files in project
            definitions_map: Map of type/definition names to file paths

        Returns:
            Resolved file path, or None if external/unresolvable
        """
        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format entry point for display.

        Override for language-specific formatting.

        Args:
            ep: EntryPointInfo object to format

        Returns:
            Formatted string for display (with leading 2-space indent)
        """
        line_str = f" @{ep.line}" if ep.line else ""
        return f"  {ep.file}:{ep.name or ep.type}{line_str}"

    def get_file_extension(self) -> str:
        """Return primary file extension for this language.

        Returns:
            Primary extension (e.g., ".py", ".swift", ".go")
        """
        exts = self.get_extensions()
        return exts[0] if exts else ""

    # ===========================================================================
    # Helper methods (from BaseScanner)
    # ===========================================================================

    def _get_node_text(self, node, source_code: bytes) -> str:
        """Extract text from a tree-sitter node."""
        try:
            return source_code[node.start_byte:node.end_byte].decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return source_code[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _get_ancestors(self, root, target) -> list:
        """Get all ancestor nodes of a target node."""
        ancestors = []

        def find_path(node, path: list) -> bool:
            if node == target:
                ancestors.extend(path)
                return True
            for child in node.children:
                if find_path(child, path + [node]):
                    return True
            return False

        find_path(root, [])
        return ancestors

    def _handle_import(self, node, parent_structures: list):
        """Group import statements together."""
        if not parent_structures or parent_structures[-1].type != "imports":
            import_node = StructureNode(
                type="imports",
                name="import statements",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(import_node)
        else:
            # Extend the end line of the existing import group
            parent_structures[-1].end_line = node.end_point[0] + 1

    def _normalize_signature(self, signature: str) -> str:
        """Normalize a signature to single line for tree formatting."""
        if not signature:
            return signature
        normalized = signature.replace('\n', ' ').replace('\r', ' ')
        return ' '.join(normalized.split())

    # Error-ratio sample size for fallback detection. Full trees can run to
    # millions of nodes (a 4MB generated markdown table is 1.3M nodes) and
    # the ratio stabilizes long before this.
    _FALLBACK_SAMPLE_LIMIT = 2000

    def _should_use_fallback(self, root_node) -> bool:
        """Determine if we should use regex fallback due to too many errors.

        Single walk with early exit — the previous implementation walked the
        entire tree twice and dominated scan time on table-heavy markdown.
        """
        if not self.fallback_on_errors:
            return False
        total = 0
        errors = 0
        stack = [root_node]
        while stack and total < self._FALLBACK_SAMPLE_LIMIT:
            node = stack.pop()
            total += 1
            if node.type == "ERROR":
                errors += 1
            stack.extend(node.children)
        return total > 0 and (errors / total) > 0.5

    def _calculate_complexity(self, node) -> dict:
        """Calculate complexity metrics for a node.

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
            if n.type in (
                "if_statement", "for_statement", "while_statement",
                "switch_statement", "case_statement", "match_statement"
            ):
                stats["branches"] += 1
            for child in n.children:
                traverse_depth(child, depth + 1)

        traverse_depth(node, 0)
        return stats

    def _resolve_relative_import(
        self, current_file: str, relative_import: str
    ) -> Optional[str]:
        """Resolve relative import to absolute file path.

        Args:
            current_file: Path of file doing the import
            relative_import: Relative import string

        Returns:
            Resolved path or None
        """
        if not relative_import.startswith("."):
            return None

        dots = len(relative_import) - len(relative_import.lstrip("."))
        rest = relative_import.lstrip(".")

        parts = current_file.split("/")[:-1]  # Remove filename

        for _ in range(dots - 1):
            if not parts:
                return None
            parts.pop()

        if rest:
            parts.extend(rest.split("."))

        return "/".join(parts) if parts else None
