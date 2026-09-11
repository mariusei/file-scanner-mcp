"""
FILE: languages/json.py

PROBLEM:
  JSON files (.json) were claimed by ConfigLanguage, whose scan() returns []
  by design ("configs don't have code structure"). scan_file/scan_directory
  showed nothing for package.json, tsconfig.json or any other .json file,
  even though JSON has an unambiguous tree.

SOLUTION:
  A dedicated tree-sitter-backed handler that turns the JSON document into
  real StructureNodes (object keys, nested objects, arrays, scalars), and
  takes over the .json-specific import/entry-point extraction that used to
  live in ConfigLanguage (package.json, tsconfig.json, generic path refs).

SCOPE:
  - Object keys become "key"/"object"/"array" nodes depending on their value
  - Objects nest fully (every depth becomes real nodes); arrays are leaves
    annotated with their item count — see _extract_structure for the
    documented nesting decision
  - Does not evaluate JSONPath, schemas, or JSON5/JSONC comments
"""

import json as json_module
import re
from pathlib import Path

from tree_sitter import Node, Parser
from tree_sitter_language_pack import get_language as get_packed_grammar

from .base import BaseLanguage
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


class JSONLanguage(BaseLanguage):
    """Unified language handler for JSON files (.json).

    - scan(): turn the object/array tree into StructureNodes
    - extract_imports(): tsconfig.json / package.json file references, plus
      generic relative-path patterns
    - find_entry_points(): package.json / tsconfig.json project markers
    """

    # Declarative languages: the "trivial" lines (closing braces, blank
    # lines) are the only thing worth folding — every key/value line IS
    # the content.
    CONDENSE_STRATEGY = "compact"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = get_packed_grammar("json")

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".json"]

    @classmethod
    def get_language_name(cls) -> str:
        return "JSON"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (identical to the ConfigLanguage behaviour this replaces)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip lock files and minified JSON."""
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
        """Skip JSON files that should not be analyzed."""
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
        {"pattern": r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*:', "type": "key"},
    ]

    # ===========================================================================
    # Structure Scanning
    # ===========================================================================

    def _extract_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract structure from a JSON document.

        Nesting decision: object keys are nodes at every depth (an object
        value recurses into its own key nodes as children), while an array
        value is always a leaf — its item count goes in `signature` rather
        than expanding each element. This keeps deeply nested config objects
        (tsconfig "compilerOptions", package.json "scripts") fully readable
        while an array of many similar items (dependency lists, data rows)
        stays a single line.
        """
        value_node = self._document_value(root)
        if value_node is None:
            return []

        if value_node.type == "object":
            return self._extract_object_members(value_node, source_code)
        if value_node.type == "array":
            return [self._array_node(value_node, source_code, name="(array)", synthetic=True)]

        # A bare top-level scalar is valid JSON but has no key to name it.
        return [
            StructureNode(
                type="key",
                name="(value)",
                start_line=value_node.start_point[0] + 1,
                end_line=value_node.end_point[0] + 1,
                signature=self._scalar_signature(value_node, source_code),
                synthetic=True,
            )
        ]

    def _document_value(self, root: Node) -> Node | None:
        """The single value under the JSON document root, if any."""
        for child in root.children:
            if child.is_named:
                return child
        return None

    def _extract_object_members(self, obj_node: Node, source_code: bytes) -> list[StructureNode]:
        """Convert an object's pairs into StructureNodes."""
        members: list[StructureNode] = []
        for pair in obj_node.named_children:
            if pair.type != "pair":
                continue
            member = self._pair_node(pair, source_code)
            if member is not None:
                members.append(member)
        return members

    def _pair_node(self, pair: Node, source_code: bytes) -> StructureNode | None:
        key_node = pair.named_children[0] if pair.named_children else None
        if key_node is None:
            return None
        value_node = pair.named_children[1] if len(pair.named_children) > 1 else None
        name = self._key_text(key_node, source_code)
        start_line = pair.start_point[0] + 1
        end_line = pair.end_point[0] + 1

        if value_node is None:
            return StructureNode(type="key", name=name, start_line=start_line, end_line=end_line)
        if value_node.type == "object":
            children = self._extract_object_members(value_node, source_code)
            return StructureNode(
                type="object",
                name=name,
                start_line=start_line,
                end_line=end_line,
                children=children,
            )
        if value_node.type == "array":
            return self._array_node(value_node, source_code, name, start_line, end_line)
        return StructureNode(
            type="key",
            name=name,
            start_line=start_line,
            end_line=end_line,
            signature=self._scalar_signature(value_node, source_code),
        )

    def _array_node(
        self,
        array_node: Node,
        source_code: bytes,
        name: str,
        start_line: int | None = None,
        end_line: int | None = None,
        synthetic: bool = False,
    ) -> StructureNode:
        count = array_node.named_child_count
        return StructureNode(
            type="array",
            name=name,
            start_line=start_line if start_line is not None else array_node.start_point[0] + 1,
            end_line=end_line if end_line is not None else array_node.end_point[0] + 1,
            signature=f"{count} item" if count == 1 else f"{count} items",
            synthetic=synthetic,
        )

    def _key_text(self, key_node: Node, source_code: bytes) -> str:
        """A JSON key is always a quoted string; strip the surrounding quotes."""
        text = self._get_node_text(key_node, source_code)
        if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
            return text[1:-1]
        return text

    def _scalar_signature(self, value_node: Node, source_code: bytes) -> str:
        """Compact, truncated display of a scalar JSON value."""
        text = self._get_node_text(value_node, source_code)
        if len(text) > _MAX_SIGNATURE_LEN:
            text = text[:_SIGNATURE_HEAD] + "..."
        return text

    # ===========================================================================
    # Semantic Analysis - Layer 1
    # (moved from ConfigLanguage._extract_json_imports / _find_json_entry_points)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract file path references from JSON config files.

        Handles tsconfig.json (extends/files/include/paths) and
        package.json (scripts referencing local files), plus generic
        relative-path patterns shared with every config-like extension.

        Does NOT extract package.json dependency names — those are
        registry package names, not file imports.
        """
        imports: list[ImportInfo] = []
        filename = Path(file_path).name.lower()

        try:
            data = json_module.loads(content)
        except json_module.JSONDecodeError:
            data = None

        if data is not None:
            if filename == "tsconfig.json":
                imports.extend(self._extract_tsconfig_imports(file_path, content, data))
            elif filename == "package.json":
                imports.extend(self._extract_package_json_imports(file_path, content, data))

        imports.extend(self._extract_path_patterns(file_path, content))
        return imports

    def _extract_tsconfig_imports(
        self, file_path: str, content: str, data: dict
    ) -> list[ImportInfo]:
        imports: list[ImportInfo] = []

        if "extends" in data and isinstance(data["extends"], str):
            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=data["extends"],
                    line=self._find_line(content, data["extends"]),
                    import_type="extends",
                )
            )

        if "files" in data and isinstance(data["files"], list):
            for file_ref in data["files"]:
                if isinstance(file_ref, str):
                    imports.append(
                        ImportInfo(
                            source_file=file_path,
                            target_module=file_ref,
                            line=self._find_line(content, file_ref),
                            import_type="file_reference",
                        )
                    )

        if "include" in data and isinstance(data["include"], list):
            for pattern in data["include"]:
                if isinstance(pattern, str) and not pattern.startswith("*"):
                    imports.append(
                        ImportInfo(
                            source_file=file_path,
                            target_module=pattern,
                            line=self._find_line(content, pattern),
                            import_type="include_pattern",
                        )
                    )

        if "compilerOptions" in data and "paths" in data["compilerOptions"]:
            paths = data["compilerOptions"]["paths"]
            if isinstance(paths, dict):
                for _alias, path_list in paths.items():
                    if isinstance(path_list, list):
                        for path in path_list:
                            if isinstance(path, str):
                                imports.append(
                                    ImportInfo(
                                        source_file=file_path,
                                        target_module=path,
                                        line=self._find_line(content, path),
                                        import_type="path_mapping",
                                    )
                                )

        return imports

    def _extract_package_json_imports(
        self, file_path: str, content: str, data: dict
    ) -> list[ImportInfo]:
        imports: list[ImportInfo] = []

        if "scripts" in data and isinstance(data["scripts"], dict):
            for _script_name, script_cmd in data["scripts"].items():
                if isinstance(script_cmd, str):
                    file_refs = re.findall(
                        r"\b(?:\./)?[\w/.-]+\.(?:js|ts|mjs|cjs|json|jsx|tsx)\b", script_cmd
                    )
                    for ref in file_refs:
                        imports.append(
                            ImportInfo(
                                source_file=file_path,
                                target_module=ref,
                                line=self._find_line(content, ref),
                                import_type="script_file",
                            )
                        )

        return imports

    def _extract_path_patterns(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract generic relative file path patterns from a JSON file.

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
        """Find entry points in package.json / tsconfig.json."""
        entry_points: list[EntryPointInfo] = []
        filename = Path(file_path).name.lower()

        try:
            data = json_module.loads(content)
        except json_module.JSONDecodeError:
            return entry_points

        if filename == "package.json":
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="project_config",
                    name="npm_project",
                    line=1,
                    framework="npm",
                )
            )
            if "main" in data:
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="main_entry",
                        name=data["main"],
                        line=self._find_line(content, data["main"]),
                        framework="npm",
                    )
                )
            if "bin" in data and isinstance(data["bin"], dict):
                for bin_name, _bin_path in data["bin"].items():
                    entry_points.append(
                        EntryPointInfo(
                            file=file_path,
                            type="bin_script",
                            name=bin_name,
                            line=self._find_line(content, bin_name),
                            framework="npm",
                        )
                    )
        elif filename == "tsconfig.json":
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="project_config",
                    name="typescript_project",
                    line=1,
                    framework="TypeScript",
                )
            )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """JSON files don't have function/class definitions."""
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """JSON files don't have function calls."""
        return []

    # ===========================================================================
    # Classification
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """JSON config files go to the config cluster."""
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
        """Resolve a JSON file reference to a file path (direct path matching)."""
        if module in all_files:
            return module

        source_dir = str(Path(source_file).parent)
        if source_dir != ".":
            candidate = f"{source_dir}/{module}"
            if candidate in all_files:
                return candidate

        return None

    # ===========================================================================
    # Helper methods
    # ===========================================================================

    def _find_line(self, content: str, search_str: str) -> int:
        """Find line number of a string in content."""
        try:
            index = content.index(search_str)
            return content[:index].count("\n") + 1
        except ValueError:
            return 0
