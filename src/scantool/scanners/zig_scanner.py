"""Scanner for Zig source files using tree-sitter."""

import re
from typing import Optional

import tree_sitter_zig
from tree_sitter import Language, Node, Parser

from .base import BaseScanner, StructureNode


class ZigScanner(BaseScanner):
    """Scanner for Zig files with rich metadata extraction."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_zig.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".zig", ".zon"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Zig"

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip Zig cache and build artifacts."""
        skip_patterns = [
            "zig-cache",
            "zig-out",
        ]
        return any(pattern in filename for pattern in skip_patterns)

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
                    name=name + " ⚠",
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
                    name=name + " ⚠",
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
                    name=name + " ⚠",
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
                    name=name + " ⚠",
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
                    name=name + " ⚠",
                    start_line=line_num,
                    end_line=line_num,
                )
            )

        return structures
