"""Go language scanner with type extraction and method receiver support."""

import re
from typing import Optional

import tree_sitter_go
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class GoScanner(BaseScanner):
    """Scanner for Go files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_go.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".go"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Go"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Go source code and extract structure with metadata."""
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
        """Extract structure using tree-sitter."""
        structures = []

        def traverse(node: Node, parent_structures: list):
            # Handle parse errors
            if node.type == "ERROR":
                if self.show_errors:
                    error_node = StructureNode(
                        type="parse-error",
                        name="⚠ invalid syntax",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1
                    )
                    parent_structures.append(error_node)
                return

            # Type declarations (struct, interface)
            if node.type == "type_declaration":
                type_node = self._extract_type(node, source_code)
                if type_node:
                    parent_structures.append(type_node)

            # Function declarations (standalone functions)
            elif node.type == "function_declaration":
                func_node = self._extract_function(node, source_code)
                parent_structures.append(func_node)

            # Method declarations (functions with receivers)
            elif node.type == "method_declaration":
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Import declarations
            elif node.type == "import_declaration":
                self._handle_import(node, parent_structures)

            else:
                # Keep traversing
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_type(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract type declaration (struct, interface, etc.)."""
        # type_declaration has a type_spec child
        type_spec = None
        for child in node.children:
            if child.type == "type_spec":
                type_spec = child
                break

        if not type_spec:
            return None

        # Get type name
        name_node = type_spec.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get type definition (struct, interface, etc.)
        type_node = type_spec.child_by_field_name("type")
        if not type_node:
            return None

        type_kind = type_node.type

        # Map Go type kinds to our structure types
        if type_kind == "struct_type":
            struct_type = "struct"
        elif type_kind == "interface_type":
            struct_type = "interface"
        else:
            # For other types (aliases, etc.), use generic "type"
            struct_type = "type"

        # Extract comments
        docstring = self._extract_comment(node, source_code)

        # Check for exported (public) types
        modifiers = self._extract_type_modifiers(name)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type=struct_type,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_function(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract standalone function declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get signature
        signature = self._extract_signature(node, source_code)

        # Extract comments
        docstring = self._extract_comment(node, source_code)

        # Check for exported (public) functions
        modifiers = self._extract_function_modifiers(name, node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="function",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_method(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract method declaration (function with receiver)."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get receiver
        receiver_node = node.child_by_field_name("receiver")
        receiver_text = None
        if receiver_node:
            receiver_text = self._get_node_text(receiver_node, source_code).strip()

        # Get signature
        signature = self._extract_signature(node, source_code, receiver_text)

        # Extract comments
        docstring = self._extract_comment(node, source_code)

        # Check for exported (public) methods
        modifiers = self._extract_function_modifiers(name, node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_signature(self, node: Node, source_code: bytes, receiver: Optional[str] = None) -> Optional[str]:
        """Extract function/method signature with parameters and return types."""
        parts = []

        # Add receiver for methods
        if receiver:
            parts.append(receiver)
            parts.append(" ")

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Get return type/result
        result_node = node.child_by_field_name("result")
        if result_node:
            result_text = self._get_node_text(result_node, source_code).strip()
            # Go can have named or unnamed return values
            # If it's a parameter_list (multiple returns), keep parentheses
            # If it's a single type, just show the type
            if result_node.type == "parameter_list" or " " in result_text:
                parts.append(f" {result_text}")
            else:
                parts.append(f" {result_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_comment(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract comment immediately preceding a declaration."""
        # In Go, comments are typically previous siblings
        prev = node.prev_sibling

        comments = []
        while prev and prev.type == "comment":
            comment_text = self._get_node_text(prev, source_code).strip()
            # Remove comment markers
            if comment_text.startswith("//"):
                comment_text = comment_text[2:].strip()
            elif comment_text.startswith("/*"):
                comment_text = comment_text[2:].strip()
                if comment_text.endswith("*/"):
                    comment_text = comment_text[:-2].strip()
            if comment_text:
                comments.insert(0, comment_text)
            prev = prev.prev_sibling

        if comments:
            # Return first line
            return comments[0]
        return None

    def _extract_type_modifiers(self, name: str) -> list[str]:
        """Extract modifiers for types (public/private based on capitalization)."""
        modifiers = []
        if name and name[0].isupper():
            modifiers.append("public")
        return modifiers

    def _extract_function_modifiers(self, name: str, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for functions/methods."""
        modifiers = []

        # Public if capitalized
        if name and name[0].isupper():
            modifiers.append("public")

        return modifiers

    def _handle_import(self, node: Node, parent_structures: list):
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

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for severely malformed files."""
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find type declarations
        for match in re.finditer(r'^type\s+(\w+)\s+(struct|interface)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            type_kind = match.group(2)
            structures.append(StructureNode(
                type=type_kind,
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function declarations
        for match in re.finditer(r'^func\s+(\w+)\s*\((.*?)\)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1)
            params = match.group(2)

            structures.append(StructureNode(
                type="function",
                name=name + " ⚠",
                start_line=line_num,
                end_line=line_num,
                signature=f"({params})"
            ))

        # Find method declarations (with receivers)
        for match in re.finditer(r'^func\s+\((\w+\s+\*?\w+)\)\s+(\w+)\s*\((.*?)\)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            receiver = match.group(1)
            name = match.group(2)
            params = match.group(3)

            structures.append(StructureNode(
                type="method",
                name=name + " ⚠",
                start_line=line_num,
                end_line=line_num,
                signature=f"({receiver}) ({params})"
            ))

        return structures
