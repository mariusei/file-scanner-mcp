"""Scanner for PHP files."""

import re
from typing import Optional

import tree_sitter_php
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class PHPScanner(BaseScanner):
    """Scanner for PHP files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_php.language_php())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".php", ".phtml", ".php3", ".php4", ".php5", ".phps"]

    @classmethod
    def get_language_name(cls) -> str:
        return "PHP"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan PHP source code and extract structure with metadata."""
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

            # Namespace declaration
            if node.type == "namespace_definition":
                self._handle_namespace(node, parent_structures, source_code)

            # Use statements (imports)
            elif node.type == "namespace_use_declaration":
                self._handle_use(node, parent_structures)

            # Classes
            elif node.type == "class_declaration":
                class_node = self._extract_class(node, source_code, root)
                parent_structures.append(class_node)

                # Traverse children for methods and properties
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, class_node.children)

            # Interfaces
            elif node.type == "interface_declaration":
                interface_node = self._extract_interface(node, source_code)
                parent_structures.append(interface_node)

                # Traverse children for method signatures
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, interface_node.children)

            # Traits
            elif node.type == "trait_declaration":
                trait_node = self._extract_trait(node, source_code)
                parent_structures.append(trait_node)

                # Traverse children for methods
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, trait_node.children)

            # Enums (PHP 8.1+)
            elif node.type == "enum_declaration":
                enum_node = self._extract_enum(node, source_code)
                parent_structures.append(enum_node)

            # Methods (in classes/traits)
            elif node.type == "method_declaration":
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Standalone functions
            elif node.type == "function_definition":
                # Only capture top-level functions, not methods
                if not self._is_in_class_or_trait(root, node):
                    function_node = self._extract_function(node, source_code)
                    parent_structures.append(function_node)

            else:
                # Keep traversing
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_class(self, node: Node, source_code: bytes, root: Node) -> StructureNode:
        """Extract class with full metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes (PHP 8+)
        decorators = self._extract_attributes(node, source_code)

        # Get base class and interfaces
        signature_parts = []

        # Get base class (extends)
        base_clause = node.child_by_field_name("base_clause")
        if base_clause:
            base_text = self._get_node_text(base_clause, source_code).strip()
            signature_parts.append(base_text)

        # Get interfaces (implements)
        interface_clause = node.child_by_field_name("interface_clause")
        if interface_clause:
            interface_text = self._get_node_text(interface_clause, source_code).strip()
            signature_parts.append(interface_text)

        signature = " ".join(signature_parts) if signature_parts else None

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="class",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            complexity=complexity,
            modifiers=modifiers,
            children=[]
        )

    def _extract_interface(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract interface declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get attributes (PHP 8+)
        decorators = self._extract_attributes(node, source_code)

        # Get extends clause
        base_clause = node.child_by_field_name("base_clause")
        signature = None
        if base_clause:
            signature = self._get_node_text(base_clause, source_code).strip()

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

        return StructureNode(
            type="interface",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            children=[]
        )

    def _extract_trait(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract trait declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get attributes (PHP 8+)
        decorators = self._extract_attributes(node, source_code)

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

        return StructureNode(
            type="trait",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            decorators=decorators,
            docstring=docstring,
            children=[]
        )

    def _extract_enum(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract enum declaration (PHP 8.1+)."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get type (backed enum)
        signature_parts = []
        for child in node.children:
            if child.type == "primitive_type":
                type_text = self._get_node_text(child, source_code)
                signature_parts.append(f": {type_text}")

        # Get interfaces (implements)
        interface_clause = node.child_by_field_name("interface_clause")
        if interface_clause:
            interface_text = self._get_node_text(interface_clause, source_code).strip()
            signature_parts.append(interface_text)

        signature = " ".join(signature_parts) if signature_parts else None

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

        return StructureNode(
            type="enum",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_method(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract method with signature and metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get signature
        signature = self._extract_method_signature(node, source_code)

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_function(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract standalone function with signature and metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get signature
        signature = self._extract_function_signature(node, source_code)

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="function",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            complexity=complexity,
            children=[]
        )

    def _extract_method_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract method signature with parameters and return type."""
        parts = []

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Get return type
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_text = self._get_node_text(return_type_node, source_code).strip()
            parts.append(f" {return_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_function_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature with parameters and return type."""
        parts = []

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Get return type
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_text = self._get_node_text(return_type_node, source_code).strip()
            parts.append(f" {return_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers like public, private, protected, static, final, abstract."""
        modifiers = []

        for child in node.children:
            if child.type in ("visibility_modifier", "final_modifier", "abstract_modifier", "static_modifier"):
                modifier_text = self._get_node_text(child, source_code).strip()
                modifiers.append(modifier_text)

        return modifiers

    def _extract_attributes(self, node: Node, source_code: bytes) -> list[str]:
        """Extract PHP 8 attributes from a class/method/function."""
        attributes = []

        # In PHP, attributes are children of the node, appearing before the keyword
        for child in node.children:
            if child.type == "attribute_list":
                attr_text = self._get_node_text(child, source_code).strip()
                attributes.append(attr_text)

        return attributes

    def _extract_phpdoc(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract first line of PHPDoc comment."""
        prev = node.prev_sibling

        # PHPDoc comments are typically previous siblings
        while prev:
            if prev.type == "comment":
                comment_text = self._get_node_text(prev, source_code).strip()
                # Check if it's a PHPDoc comment (/** ... */)
                if comment_text.startswith("/**"):
                    # Extract first meaningful line
                    lines = comment_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        # Remove comment markers
                        line = line.replace("/**", "").replace("*/", "").replace("*", "").strip()
                        if line and not line.startswith("@"):  # Skip PHPDoc tags
                            return line
                return None
            prev = prev.prev_sibling

        return None

    def _handle_namespace(self, node: Node, parent_structures: list, source_code: bytes):
        """Handle namespace declaration."""
        namespace_name_node = node.child_by_field_name("name")

        if namespace_name_node:
            namespace_name = self._get_node_text(namespace_name_node, source_code)
            namespace_node = StructureNode(
                type="namespace",
                name=namespace_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(namespace_node)

    def _handle_use(self, node: Node, parent_structures: list):
        """Group use statements together."""
        if not parent_structures or parent_structures[-1].type != "imports":
            import_node = StructureNode(
                type="imports",
                name="use statements",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(import_node)
        else:
            # Extend the end line of the existing import group
            parent_structures[-1].end_line = node.end_point[0] + 1

    def _is_in_class_or_trait(self, root: Node, target: Node) -> bool:
        """Check if a node is inside a class or trait."""
        ancestors = self._get_ancestors(root, target)
        return any(ancestor.type in ("class_declaration", "trait_declaration") for ancestor in ancestors)

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
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find namespace declaration
        namespace_match = re.search(r'^\s*namespace\s+([\w\\]+)\s*;', text, re.MULTILINE)
        if namespace_match:
            line_num = text[:namespace_match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="namespace",
                name=namespace_match.group(1),
                start_line=line_num,
                end_line=line_num
            ))

        # Find class definitions
        for match in re.finditer(r'^\s*(?:abstract\s+)?(?:final\s+)?class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find interface definitions
        for match in re.finditer(r'^\s*interface\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="interface",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find trait definitions
        for match in re.finditer(r'^\s*trait\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="trait",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum definitions
        for match in re.finditer(r'^\s*enum\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="enum",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find method definitions
        for match in re.finditer(r'^\s*(?:public|private|protected)\s+(?:static\s+)?function\s+(\w+)\s*\(', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find standalone function definitions
        for match in re.finditer(r'^\s*function\s+(\w+)\s*\(', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="function",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        return structures
