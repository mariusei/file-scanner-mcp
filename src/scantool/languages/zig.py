"""Zig language support - unified scanner and analyzer.

This module combines ZigScanner and ZigAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_zig
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class ZigLanguage(BaseLanguage):
    """Unified language handler for Zig files (.zig, .zon).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract structs, enums, unions, functions, tests with metadata
    - extract_imports(): Find @import and @embedFile statements
    - find_entry_points(): Find pub fn main, export functions, tests
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Find function calls (not yet implemented)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_zig.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".zig", ".zon"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Zig"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip Zig cache and build artifacts."""
        skip_patterns = [
            "zig-cache",
            "zig-out",
        ]
        return any(pattern in filename for pattern in skip_patterns)

    def should_analyze(self, file_path: str) -> bool:
        """Skip Zig files that should not be analyzed.

        Zig-specific skip patterns:
        - Skip zig-cache and zig-out directories
        """
        path_lower = file_path.lower()

        # Skip cache and build directories
        if '/zig-cache/' in path_lower or '/zig-out/' in path_lower:
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value Zig files for inventory listing.

        Low-value files:
        - Very small files (< 50 bytes)
        """
        if size > 0 and size < 50:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from ZigScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Zig source code and extract structure with metadata."""
        try:
            tree = self.parser.parse(source_code)

            # Check for excessive errors
            if self._should_use_fallback(tree.root_node):
                if self.fallback_on_errors:
                    return self._fallback_extract(source_code)
                return None

            return self._extract_structure(tree.root_node, source_code)

        except Exception as e:
            if self.show_errors:
                print(f"Zig parsing error: {e}")
            if self.fallback_on_errors:
                return self._fallback_extract(source_code)
            return None

    def _extract_structure(
        self, root: Node, source_code: bytes
    ) -> list[StructureNode]:
        """Extract structure using tree-sitter."""
        structures = []

        for node in root.children:
            if node.type == "function_declaration":
                func_node = self._extract_function(node, source_code, root)
                structures.append(func_node)

            elif node.type == "variable_declaration":
                # Check if this is a struct, enum, union, or import
                struct_node = self._extract_variable_declaration(
                    node, source_code, root
                )
                if struct_node:
                    structures.append(struct_node)

            elif node.type == "test_declaration":
                test_node = self._extract_test(node, source_code)
                structures.append(test_node)

        return structures

    def _extract_function(
        self, node: Node, source_code: bytes, root: Node
    ) -> StructureNode:
        """Extract function with signature and metadata."""
        name = "unnamed"
        for child in node.children:
            if child.type == "identifier":
                name = self._get_node_text(child, source_code)
                break

        # Get signature
        signature = self._extract_signature(node, source_code)

        # Get modifiers (pub, inline, export, extern)
        modifiers = self._extract_modifiers(node, source_code)

        # Get doc comment
        docstring = self._extract_doc_comment(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        # Determine if method (inside struct/union)
        is_method = any(
            p.type in ("struct_declaration", "union_declaration")
            for p in self._get_ancestors(root, node)
        )
        type_name = "method" if is_method else "function"

        return StructureNode(
            type=type_name,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[],
        )

    def _extract_variable_declaration(
        self, node: Node, source_code: bytes, root: Node
    ) -> Optional[StructureNode]:
        """Extract struct, enum, union, or import from variable declaration."""
        name = None
        decl_type = None
        decl_node = None

        for child in node.children:
            if child.type == "identifier":
                name = self._get_node_text(child, source_code)
            elif child.type == "struct_declaration":
                decl_type = "struct"
                decl_node = child
            elif child.type == "enum_declaration":
                decl_type = "enum"
                decl_node = child
            elif child.type == "union_declaration":
                decl_type = "union"
                decl_node = child
            elif child.type == "builtin_function":
                # Check if it's an @import
                builtin_id = child.child_by_field_name("function") or next(
                    (c for c in child.children if c.type == "builtin_identifier"),
                    None,
                )
                if builtin_id:
                    builtin_name = self._get_node_text(builtin_id, source_code)
                    if builtin_name == "@import":
                        self._handle_import(node, [])
                        return None

        if not name or not decl_type or not decl_node:
            return None

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get doc comment
        docstring = self._extract_doc_comment(node, source_code)

        # Extract children (methods for structs)
        children = []
        if decl_type == "struct":
            children = self._extract_struct_members(decl_node, source_code, root)

        # Calculate complexity
        complexity = self._calculate_complexity(decl_node)

        return StructureNode(
            type=decl_type,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=children,
        )

    def _extract_struct_members(
        self, node: Node, source_code: bytes, root: Node
    ) -> list[StructureNode]:
        """Extract methods and fields from struct/union."""
        members = []

        for child in node.children:
            if child.type == "function_declaration":
                func = self._extract_function(child, source_code, root)
                func.type = "method"
                members.append(func)

        return members

    def _extract_test(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract test declaration."""
        name = "unnamed test"

        # Test name is in a string node
        for child in node.children:
            if child.type == "string":
                # Get the string content without quotes
                string_content = next(
                    (c for c in child.children if c.type == "string_content"), None
                )
                if string_content:
                    name = self._get_node_text(string_content, source_code)
                break

        return StructureNode(
            type="test",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            children=[],
        )

    def _extract_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature with parameters and return type."""
        params_node = None
        return_type = None

        for child in node.children:
            if child.type == "parameters":
                params_node = child
            elif child.type in (
                "builtin_type",
                "error_union_type",
                "optional_type",
                "identifier",
                "pointer_type",
                "slice_type",
            ):
                # This is likely the return type
                return_type = self._get_node_text(child, source_code)

        if not params_node:
            return None

        # Extract parameters
        params = []
        for child in params_node.children:
            if child.type == "parameter":
                param_name = None
                param_type = None
                for p_child in child.children:
                    if p_child.type == "identifier" and param_name is None:
                        param_name = self._get_node_text(p_child, source_code)
                    elif p_child.type not in (":", ","):
                        param_type = self._get_node_text(p_child, source_code)

                if param_name and param_type:
                    params.append(f"{param_name}: {param_type}")
                elif param_name:
                    params.append(param_name)

        sig = f"({', '.join(params)})"
        if return_type:
            sig += f" {return_type}"

        return self._normalize_signature(sig)

    def _extract_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers like pub, inline, export, extern."""
        modifiers = []

        for child in node.children:
            if child.type == "pub":
                modifiers.append("pub")
            elif child.type == "inline":
                modifiers.append("inline")
            elif child.type == "export":
                modifiers.append("export")
            elif child.type == "extern":
                modifiers.append("extern")
            elif child.type == "const":
                # Don't add const as modifier for variable declarations
                pass

        return modifiers

    def _extract_doc_comment(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract doc comments (/// or //!)."""
        # Look for comments before the node
        start_byte = node.start_byte
        text_before = source_code[:start_byte].decode("utf-8", errors="replace")

        # Find doc comments (///)
        lines = text_before.split("\n")
        doc_lines = []

        for line in reversed(lines[-10:]):  # Check last 10 lines
            stripped = line.strip()
            if stripped.startswith("///"):
                doc_lines.insert(0, stripped[3:].strip())
            elif stripped.startswith("//!"):
                doc_lines.insert(0, stripped[3:].strip())
            elif stripped and not stripped.startswith("//"):
                break

        if doc_lines:
            return doc_lines[0]  # Return first line of doc comment
        return None

    def _handle_import(self, node: Node, parent_structures: list):
        """Group @import statements together."""
        if not parent_structures or parent_structures[-1].type != "imports":
            import_node = StructureNode(
                type="imports",
                name="import statements",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
            )
            parent_structures.append(import_node)
        else:
            parent_structures[-1].end_line = node.end_point[0] + 1

    def _get_ancestors(self, root: Node, target: Node) -> list[Node]:
        """Get all ancestor nodes of a target node."""
        ancestors = []

        def find_path(node: Node, path: list[Node]) -> bool:
            if node == target:
                ancestors.extend(path)
                return True
            for child in node.children:
                if find_path(child, path + [node]):
                    return True
            return False

        find_path(root, [])
        return ancestors

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for severely malformed files."""
        text = source_code.decode("utf-8", errors="replace")
        structures = []

        # Find struct definitions
        for match in re.finditer(
            r"^\s*(pub\s+)?const\s+(\w+)\s*=\s*struct\s*\{", text, re.MULTILINE
        ):
            line_num = text[: match.start()].count("\n") + 1
            name = match.group(2)
            modifiers = ["pub"] if match.group(1) else []
            structures.append(
                StructureNode(
                    type="struct",
                    name=name + " (fallback)",
                    start_line=line_num,
                    end_line=line_num,
                    modifiers=modifiers,
                )
            )

        # Find enum definitions
        for match in re.finditer(
            r"^\s*(pub\s+)?const\s+(\w+)\s*=\s*enum\s*[\(\{]", text, re.MULTILINE
        ):
            line_num = text[: match.start()].count("\n") + 1
            name = match.group(2)
            modifiers = ["pub"] if match.group(1) else []
            structures.append(
                StructureNode(
                    type="enum",
                    name=name + " (fallback)",
                    start_line=line_num,
                    end_line=line_num,
                    modifiers=modifiers,
                )
            )

        # Find union definitions
        for match in re.finditer(
            r"^\s*(pub\s+)?const\s+(\w+)\s*=\s*union\s*[\(\{]", text, re.MULTILINE
        ):
            line_num = text[: match.start()].count("\n") + 1
            name = match.group(2)
            modifiers = ["pub"] if match.group(1) else []
            structures.append(
                StructureNode(
                    type="union",
                    name=name + " (fallback)",
                    start_line=line_num,
                    end_line=line_num,
                    modifiers=modifiers,
                )
            )

        # Find function definitions
        for match in re.finditer(
            r"^\s*(pub\s+)?(inline\s+)?(export\s+)?(extern\s+)?fn\s+(\w+)",
            text,
            re.MULTILINE,
        ):
            line_num = text[: match.start()].count("\n") + 1
            name = match.group(5)
            modifiers = []
            if match.group(1):
                modifiers.append("pub")
            if match.group(2):
                modifiers.append("inline")
            if match.group(3):
                modifiers.append("export")
            if match.group(4):
                modifiers.append("extern")
            structures.append(
                StructureNode(
                    type="function",
                    name=name + " (fallback)",
                    start_line=line_num,
                    end_line=line_num,
                    modifiers=modifiers,
                )
            )

        # Find test declarations
        for match in re.finditer(r'^\s*test\s+"([^"]+)"', text, re.MULTILINE):
            line_num = text[: match.start()].count("\n") + 1
            name = match.group(1)
            structures.append(
                StructureNode(
                    type="test",
                    name=name + " (fallback)",
                    start_line=line_num,
                    end_line=line_num,
                )
            )

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from ZigAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract import statements from Zig file.

        Patterns supported:
        - const x = @import("module");
        - const x = @import("path/file.zig");
        - @embedFile("path/to/file")
        """
        imports = []

        # Pattern: @import("module")
        import_pattern = r'@import\s*\(\s*"([^"]+)"\s*\)'
        for match in re.finditer(import_pattern, content):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Determine import type
            if module == "std" or module == "builtin":
                import_type = "std"
            elif module.endswith(".zig"):
                import_type = "local"
            else:
                import_type = "package"

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type=import_type,
                )
            )

        # Pattern: @embedFile("path")
        embed_pattern = r'@embedFile\s*\(\s*"([^"]+)"\s*\)'
        for match in re.finditer(embed_pattern, content):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type="embed",
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in Zig file.

        Entry points:
        - pub fn main() - main function
        - export fn ... - exported functions
        - test "name" { } - test blocks
        """
        entry_points = []

        # Pattern 1: pub fn main()
        main_pattern = r'^\s*pub\s+fn\s+main\s*\('
        for match in re.finditer(main_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_function",
                    name="main",
                    line=line_num,
                )
            )

        # Pattern 2: export fn name()
        export_pattern = r'^\s*export\s+fn\s+(\w+)\s*\('
        for match in re.finditer(export_pattern, content, re.MULTILINE):
            name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="export",
                    name=name,
                    line=line_num,
                )
            )

        # Pattern 3: test "name" { }
        test_pattern = r'^\s*test\s+"([^"]+)"'
        for match in re.finditer(test_pattern, content, re.MULTILINE):
            name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="test",
                    name=name,
                    line=line_num,
                )
            )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract function/struct/enum definitions by reusing scan() output.

        This is the key optimization: instead of re-parsing with tree-sitter,
        we convert the StructureNode output from scan() to DefinitionInfo.
        """
        try:
            structures = self.scan(content.encode("utf-8"))
            if not structures:
                return []
            return self._structures_to_definitions(file_path, structures)
        except Exception:
            # Fallback to regex-based extraction
            return self._extract_definitions_regex(file_path, content)

    def _structures_to_definitions(
        self, file_path: str, structures: list[StructureNode], parent: str = None
    ) -> list[DefinitionInfo]:
        """Convert StructureNode list to DefinitionInfo list.

        Overrides base class to handle Zig-specific types (struct, enum, union).
        """
        definitions = []

        for node in structures:
            # Include Zig-specific types: struct, enum, union
            if node.type in ("class", "function", "method", "struct", "enum", "union"):
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
                # For Zig, struct/enum/union can contain methods
                child_parent = node.name if node.type in ("class", "struct", "enum", "union") else parent
                definitions.extend(
                    self._structures_to_definitions(file_path, node.children, child_parent)
                )

        return definitions

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        # Find struct definitions
        for match in re.finditer(
            r"^\s*(pub\s+)?const\s+(\w+)\s*=\s*struct\s*\{", content, re.MULTILINE
        ):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="struct",
                    name=match.group(2),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        # Find function definitions
        for match in re.finditer(
            r"^\s*(pub\s+)?(inline\s+)?(export\s+)?(extern\s+)?fn\s+(\w+)",
            content,
            re.MULTILINE,
        ):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="function",
                    name=match.group(5),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        return definitions

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Extract function calls using tree-sitter."""
        try:
            source_bytes = content.encode("utf-8")
            tree = self.parser.parse(source_bytes)
            return self._extract_calls_tree_sitter(
                file_path, tree.root_node, source_bytes, definitions
            )
        except Exception:
            return self._extract_calls_regex(file_path, content, definitions)

    def _extract_calls_tree_sitter(
        self,
        file_path: str,
        root: Node,
        source_bytes: bytes,
        definitions: list[DefinitionInfo],
    ) -> list[CallInfo]:
        """Extract calls using tree-sitter AST with caller context tracking."""
        calls = []

        def get_callee_name(node: Node) -> Optional[str]:
            """Extract the callee name from a call expression's function node."""
            if node.type == "identifier":
                return self._get_node_text(node, source_bytes)
            elif node.type == "field_expression":
                # Get the last identifier (the actual function name)
                for child in reversed(node.children):
                    if child.type == "identifier":
                        return self._get_node_text(child, source_bytes)
            return None

        def traverse(node: Node, current_func: Optional[str] = None):
            # Track function context
            if node.type == "function_declaration":
                # Find the function name (direct identifier child)
                func_name = None
                for child in node.children:
                    if child.type == "identifier":
                        func_name = self._get_node_text(child, source_bytes)
                        break

                if func_name:
                    # Traverse children with this function as context
                    for child in node.children:
                        traverse(child, func_name)
                    return

            # Extract call expressions
            if node.type == "call_expression":
                callee_name = None
                # First child is the function being called
                for child in node.children:
                    if child.type in ("identifier", "field_expression"):
                        callee_name = get_callee_name(child)
                        break

                if callee_name and current_func:
                    calls.append(
                        CallInfo(
                            caller_file=file_path,
                            caller_name=current_func,
                            callee_name=callee_name,
                            line=node.start_point[0] + 1,
                            is_cross_file=False,
                        )
                    )

            # Recurse into children
            for child in node.children:
                traverse(child, current_func)

        traverse(root)

        # Mark cross-file calls
        local_defs = {d.name for d in definitions}
        for call in calls:
            if call.callee_name not in local_defs:
                call.is_cross_file = True

        return calls

    def _extract_calls_regex(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Fallback: Extract calls using regex (without caller context)."""
        calls = []

        call_pattern = r'\b(\w+)\s*\('
        for match in re.finditer(call_pattern, content):
            callee_name = match.group(1)
            line = content[: match.start()].count("\n") + 1

            # Skip keywords and common constructs
            if callee_name in [
                "if", "while", "for", "switch", "fn", "pub", "const",
                "var", "return", "break", "continue", "defer", "errdefer",
                "catch", "try", "struct", "enum", "union", "error",
            ]:
                continue

            calls.append(
                CallInfo(
                    caller_file=file_path,
                    caller_name=None,
                    callee_name=callee_name,
                    line=line,
                    is_cross_file=False,
                )
            )

        local_defs = {d.name for d in definitions}
        for call in calls:
            if call.callee_name not in local_defs:
                call.is_cross_file = True

        return calls

    # ===========================================================================
    # Classification (enhanced for Zig)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify Zig file into architectural cluster.

        Uses base class heuristics plus Zig-specific patterns.
        """
        # Use base class classification
        base_cluster = super().classify_file(file_path, content)

        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points
            if name == "main.zig":
                return "entry_points"

            # Check for pub fn main
            if re.search(r'pub\s+fn\s+main\s*\(', content):
                return "entry_points"

            # Build files
            if name == "build.zig":
                return "config"

            # Test files
            if re.search(r'test\s+"[^"]+"\s*\{', content):
                return "tests"

            # Source files in src/
            if '/src/' in path_lower:
                return "core_logic"

        return base_cluster

    # ===========================================================================
    # CodeMap Integration
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> Optional[str]:
        """Resolve Zig @import to file path.

        Zig imports:
        - @import("std") -> standard library (skip)
        - @import("file.zig") -> local file
        - @import("../path/file.zig") -> relative path
        """
        # Skip standard library
        if module == "std" or module == "builtin":
            return None

        # Direct file match
        if module in all_files:
            return module

        # Try relative to source file
        source_dir = str(Path(source_file).parent)
        if source_dir != ".":
            candidate = f"{source_dir}/{module}"
            if candidate in all_files:
                return candidate

        # Try src/ prefix
        candidate = f"src/{module}"
        if candidate in all_files:
            return candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format Zig entry point for display.

        Formats:
        - main_function: "pub fn main() @line"
        - test: "test \"name\" @line"
        - export: "export fn name @line"
        """
        if ep.type == "main_function":
            return f"  {ep.file}:pub fn main() @{ep.line}"
        elif ep.type == "test":
            return f"  {ep.file}:test \"{ep.name}\" @{ep.line}"
        elif ep.type == "export":
            return f"  {ep.file}:export {ep.name} @{ep.line}"
        else:
            return super().format_entry_point(ep)
