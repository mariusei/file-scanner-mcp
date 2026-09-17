"""
FILE: languages/toml.py

PROBLEM:
  TOML files (.toml) were claimed by ConfigLanguage, whose scan() returns []
  by design ("configs don't have code structure"). scan_file/scan_directory
  showed nothing for pyproject.toml, Cargo.toml or any other .toml file.

SOLUTION:
  A dedicated tree-sitter-backed handler that turns tables, array tables and
  top-level pairs into real StructureNodes, and takes over the
  .toml-specific import/entry-point extraction that used to live in
  ConfigLanguage (pyproject.toml, Cargo.toml, generic path refs).

SCOPE:
  - `[a.b]` tables and `[[x]]` array tables become nodes; their pairs become
    children. Pairs before the first table header are top-level nodes.
  - A pair's value nests fully when it is an inline table (`{ a = 1 }`, same
    treatment as a JSON object); an array value is always a leaf annotated
    with its item count — see _extract_structure for the documented nesting
    decision.
  - Full-line comments are structure too (in a config file they carry the
    explanation): a single comment line directly above a pair or table
    header is that node's docstring; every other block of consecutive
    comment lines (or a lone line of at least COMMENT_BLOCK_MIN_CHARS)
    becomes a `comment` node placed right before the pair or table that
    follows it — inside the table when a pair follows, top-level when a
    header follows — so a file header separated from the first key by a
    blank line is a `comment` node and focus= prints it verbatim. A comment
    trailing a pair on the same line is left alone (neither a block nor a
    docstring), and comments inside multi-line arrays or inline tables are
    ignored. The rule and the node shape live in base.CommentBlocks, shared
    with YAML.
  - Does not evaluate TOML type/range validity beyond what the grammar parses.
"""

import re
from pathlib import Path

from tree_sitter import Node, Parser
from tree_sitter_language_pack import get_language as get_packed_grammar

from .base import BaseLanguage, CommentBlocks, parent_dir
from .models import (
    CallInfo,
    DefinitionInfo,
    EntryPointInfo,
    ImportInfo,
    StructureNode,
)

# Scalar value truncation, matching the convention used across the other
# declarative-language handlers (CSS/SCSS variable values, selectors, ...).
_MAX_SIGNATURE_LEN = 50
_SIGNATURE_HEAD = 47

_KEY_NODE_TYPES = frozenset({"bare_key", "quoted_key", "dotted_key"})


class TOMLLanguage(BaseLanguage):
    """Unified language handler for TOML files (.toml).

    - scan(): turn tables/array tables/pairs into StructureNodes
    - extract_imports(): pyproject.toml / Cargo.toml file references, plus
      generic relative-path patterns
    - find_entry_points(): pyproject.toml / Cargo.toml project markers
    """

    # Declarative language: the "trivial" lines (closing punctuation, blank
    # lines) are the only thing worth folding — every key/value line IS the
    # content.
    CONDENSE_STRATEGY = "compact"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = get_packed_grammar("toml")

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".toml"]

    @classmethod
    def get_language_name(cls) -> str:
        return "TOML"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (identical to the ConfigLanguage behaviour this replaces)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip lock files and minified TOML."""
        filename_lower = filename.lower()
        if filename_lower in (
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "cargo.lock",
        ):
            return True
        if filename_lower.endswith(".lock"):
            return True
        return ".min." in filename_lower

    def should_analyze(self, file_path: str) -> bool:
        """Skip TOML files that should not be analyzed."""
        filename = Path(file_path).name.lower()
        if filename in (
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "cargo.lock",
        ):
            return False
        if filename.endswith(".lock"):
            return False
        return ".min." not in filename

    # ===========================================================================
    # Regex fallback for severely malformed files
    # ===========================================================================

    REGEX_FALLBACK_PATTERNS = [
        {"pattern": r"^\[\[([^\]]+)\]\]", "type": "array_table"},
        {"pattern": r"^\[(?!\[)([^\]]+)\]", "type": "table"},
        {"pattern": r"^([A-Za-z0-9_-]+)\s*=", "type": "key"},
    ]

    # ===========================================================================
    # Structure Scanning
    # ===========================================================================

    def _extract_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract structure from a TOML document.

        Nesting decision: `[a.b]` tables and `[[x]]` array tables become
        nodes, and every pair inside becomes a child node at full depth —
        including an inline table value (`{ a = 1 }`), which nests exactly
        like a `[table]` would. An array value is always a leaf: its item
        count goes in `signature` rather than expanding each element, the
        same rule as JSON. Pairs written before the first table header are
        top-level nodes, matching how they read in the file.
        """
        comments = CommentBlocks(self._full_line_comments(root, source_code), _MAX_SIGNATURE_LEN)
        structures: list[StructureNode] = []
        for child in root.children:
            if child.type not in ("pair", "table", "table_array_element"):
                continue
            leading, docstring = comments.before(child.start_point[0] + 1)
            structures.extend(leading)
            if child.type == "pair":
                node = self._pair_node(child, source_code)
            else:
                node = self._table_node(child, source_code, child.type != "table", comments)
            node.docstring = docstring
            structures.append(node)
        structures.extend(comments.rest())
        return structures

    def _full_line_comments(self, root: Node, source_code: bytes) -> list[tuple[int, str]]:
        """(line, text) of every comment that has a line to itself, in source
        order: the grammar puts a trailing comment inside its pair, and a
        comment inside an array or inline table under that value, so only
        the document's and the tables' own comment children qualify."""
        comments: list[tuple[int, str]] = []
        for parent in [root, *(c for c in root.children if c.type != "pair")]:
            for node in parent.children:
                if node.type != "comment":
                    continue
                prev = node.prev_sibling
                if prev is None or prev.end_point[0] < node.start_point[0]:
                    text = self._get_node_text(node, source_code).lstrip("#").strip()
                    comments.append((node.start_point[0] + 1, text))
        return sorted(comments)

    def _table_node(
        self, node: Node, source_code: bytes, is_array: bool, comments: CommentBlocks
    ) -> StructureNode:
        key_node: Node | None = None
        children: list[StructureNode] = []
        for child in node.named_children:
            if child.type in _KEY_NODE_TYPES and key_node is None:
                key_node = child
            elif child.type == "pair":
                leading, docstring = comments.before(child.start_point[0] + 1)
                children.extend(leading)
                pair = self._pair_node(child, source_code)
                pair.docstring = docstring
                children.append(pair)

        start_line = node.start_point[0] + 1
        # The TOML grammar extends a table's span through trailing blank
        # lines and comments up to the next header — use the header and the
        # last pair instead, so end_line reflects actual content.
        end_line = max([start_line] + [child.end_line for child in children])

        if key_node is not None:
            name = self._key_text(key_node, source_code)
            synthetic = False
        else:
            name = "(array table)" if is_array else "(table)"
            synthetic = True

        return StructureNode(
            type="array_table" if is_array else "table",
            name=name,
            start_line=start_line,
            end_line=end_line,
            children=children,
            synthetic=synthetic,
        )

    def _pair_node(self, pair: Node, source_code: bytes) -> StructureNode:
        key_node = pair.named_children[0] if pair.named_children else None
        value_node = pair.named_children[1] if len(pair.named_children) > 1 else None
        name = self._key_text(key_node, source_code) if key_node is not None else ""
        start_line = pair.start_point[0] + 1
        end_line = pair.end_point[0] + 1

        if value_node is None:
            return StructureNode(type="key", name=name, start_line=start_line, end_line=end_line)
        if value_node.type == "inline_table":
            children = [
                self._pair_node(child, source_code)
                for child in value_node.named_children
                if child.type == "pair"
            ]
            return StructureNode(
                type="object",
                name=name,
                start_line=start_line,
                end_line=end_line,
                children=children,
            )
        if value_node.type == "array":
            count = value_node.named_child_count
            return StructureNode(
                type="array",
                name=name,
                start_line=start_line,
                end_line=end_line,
                signature=f"{count} item" if count == 1 else f"{count} items",
            )
        return StructureNode(
            type="key",
            name=name,
            start_line=start_line,
            end_line=end_line,
            signature=self._scalar_signature(value_node, source_code),
        )

    def _key_text(self, key_node: Node, source_code: bytes) -> str:
        """Return a key's literal source text (bare_key/dotted_key as-is,
        quoted_key with its surrounding quotes stripped)."""
        text = self._get_node_text(key_node, source_code)
        if (
            key_node.type == "quoted_key"
            and len(text) >= 2
            and text[0] in ('"', "'")
            and text[-1] == text[0]
        ):
            return text[1:-1]
        return text

    def _scalar_signature(self, value_node: Node, source_code: bytes) -> str:
        """Compact, truncated display of a scalar TOML value."""
        text = self._get_node_text(value_node, source_code)
        if len(text) > _MAX_SIGNATURE_LEN:
            text = text[:_SIGNATURE_HEAD] + "..."
        return text

    # ===========================================================================
    # Semantic Analysis - Layer 1
    # (moved from ConfigLanguage._extract_toml_imports / _find_toml_entry_points)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract file path references from TOML config files.

        Handles pyproject.toml ([tool.*] config_file values) and Cargo.toml
        (path dependencies), plus generic relative-path patterns shared with
        every config-like extension.

        Does NOT extract Cargo.toml registry dependency names — those are
        package names, not file imports.
        """
        imports: list[ImportInfo] = []
        filename = Path(file_path).name.lower()

        if filename == "pyproject.toml":
            imports.extend(self._extract_pyproject_imports(file_path, content))
        elif filename == "cargo.toml":
            imports.extend(self._extract_cargo_imports(file_path, content))

        imports.extend(self._extract_path_patterns(file_path, content))
        return imports

    def _extract_pyproject_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        config_pattern = r'config_file\s*=\s*["\']([^"\']+)["\']'
        for match in re.finditer(config_pattern, content):
            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[: match.start()].count("\n") + 1,
                    import_type="config_file",
                )
            )
        return imports

    def _extract_cargo_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        path_dep_pattern = r'path\s*=\s*["\']([^"\']+)["\']'
        for match in re.finditer(path_dep_pattern, content):
            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[: match.start()].count("\n") + 1,
                    import_type="path_dependency",
                )
            )
        return imports

    def _extract_path_patterns(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract generic relative file path patterns from a TOML file.

        Conservative patterns: quoted relative paths with an extension, and
        the same on their own line unquoted. Skips anything that looks like
        a URL.
        """
        imports: list[ImportInfo] = []

        quoted_path_pattern = r'["\'](\./(?:[^/"\s]+/)*[^/"\s]+\.[a-zA-Z0-9]+|\.\./(?:[^/"\s]+/)*[^/"\s]+\.[a-zA-Z0-9]+)["\']'
        for match in re.finditer(quoted_path_pattern, content):
            path = match.group(1)
            if "://" not in path:
                imports.append(
                    ImportInfo(
                        source_file=file_path,
                        target_module=path,
                        line=content[: match.start()].count("\n") + 1,
                        import_type="path_reference",
                    )
                )

        unquoted_path_pattern = (
            r"(?:^|\s)(\./[^\s:]+\.[a-zA-Z0-9]+|\.\./(?:[^/\s]+/)*[^/\s]+\.[a-zA-Z0-9]+)(?:\s|$)"
        )
        for match in re.finditer(unquoted_path_pattern, content, re.MULTILINE):
            path = match.group(1)
            if "://" not in path:
                imports.append(
                    ImportInfo(
                        source_file=file_path,
                        target_module=path,
                        line=content[: match.start()].count("\n") + 1,
                        import_type="path_reference",
                    )
                )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in pyproject.toml / Cargo.toml."""
        entry_points: list[EntryPointInfo] = []
        filename = Path(file_path).name.lower()

        if filename == "pyproject.toml":
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="project_config",
                    name="python_project",
                    line=1,
                    framework="Python",
                )
            )
            match = re.search(r"\[project\.scripts\]", content)
            if match:
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="scripts_section",
                        name="project_scripts",
                        line=content[: match.start()].count("\n") + 1,
                        framework="Python",
                    )
                )
        elif filename == "cargo.toml":
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="project_config",
                    name="rust_project",
                    line=1,
                    framework="Rust",
                )
            )
            for match in re.finditer(r"\[\[bin\]\]", content):
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="bin_target",
                        name="bin",
                        line=content[: match.start()].count("\n") + 1,
                        framework="Rust",
                    )
                )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """TOML files don't have function/class definitions."""
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """TOML files don't have function calls."""
        return []

    # ===========================================================================
    # Classification
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """TOML config files go to the config cluster."""
        return "config"

    # ===========================================================================
    # CodeMap Integration
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> str | None:
        """Resolve a TOML file reference to a file path (direct path matching)."""
        if module in all_files:
            return module

        source_dir = parent_dir(source_file)
        if source_dir != ".":
            candidate = f"{source_dir}/{module}"
            if candidate in all_files:
                return candidate

        return None
