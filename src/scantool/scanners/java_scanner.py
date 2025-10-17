"""Scanner for Java files."""

import re
from typing import Optional

import tree_sitter_java
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class JavaScanner(BaseScanner):
    """Scanner for Java files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_java.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".java"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Java"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Java source code and extract structure with metadata."""
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

            # Package declaration
            if node.type == "package_declaration":
                self._handle_package(node, parent_structures, source_code)

            # Imports
            elif node.type == "import_declaration":
                self._handle_import(node, parent_structures)

            # Classes
            elif node.type == "class_declaration":
                class_node = self._extract_class(node, source_code, root)
                parent_structures.append(class_node)

                # Traverse children for methods, inner classes, etc.
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

            # Enums
            elif node.type == "enum_declaration":
                enum_node = self._extract_enum(node, source_code)
                parent_structures.append(enum_node)

            # Methods
            elif node.type == "method_declaration":
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Constructors
            elif node.type == "constructor_declaration":
                constructor_node = self._extract_constructor(node, source_code)
                parent_structures.append(constructor_node)

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

        # Get annotations
        decorators = self._extract_annotations(node, source_code)

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)

        # Get superclass and interfaces
        signature_parts = []
        if type_params:
            signature_parts.append(type_params)

        # Get superclass
        superclass = node.child_by_field_name("superclass")
        if superclass:
            superclass_text = self._get_node_text(superclass, source_code).strip()
            signature_parts.append(superclass_text)

        # Get interfaces
        interfaces = node.child_by_field_name("interfaces")
        if interfaces:
            interfaces_text = self._get_node_text(interfaces, source_code).strip()
            signature_parts.append(interfaces_text)

        signature = " ".join(signature_parts) if signature_parts else None

        # Get JavaDoc comment
        docstring = self._extract_javadoc(node, source_code)

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

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get annotations
        decorators = self._extract_annotations(node, source_code)

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)

        # Get extends clause
        signature_parts = []
        if type_params:
            signature_parts.append(type_params)

        extends = node.child_by_field_name("interfaces")
        if extends:
            extends_text = self._get_node_text(extends, source_code).strip()
            signature_parts.append(extends_text)

        signature = " ".join(signature_parts) if signature_parts else None

        # Get JavaDoc comment
        docstring = self._extract_javadoc(node, source_code)

        return StructureNode(
            type="interface",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_enum(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract enum declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get annotations
        decorators = self._extract_annotations(node, source_code)

        # Get interfaces (enums can implement interfaces)
        interfaces = node.child_by_field_name("interfaces")
        signature = None
        if interfaces:
            signature = self._get_node_text(interfaces, source_code).strip()

        # Get JavaDoc comment
        docstring = self._extract_javadoc(node, source_code)

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

        # Get annotations
        decorators = self._extract_annotations(node, source_code)

        # Get signature
        signature = self._extract_method_signature(node, source_code)

        # Get JavaDoc comment
        docstring = self._extract_javadoc(node, source_code)

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

    def _extract_constructor(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract constructor declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get annotations
        decorators = self._extract_annotations(node, source_code)

        # Get signature (parameters)
        params_node = node.child_by_field_name("parameters")
        signature = None
        if params_node:
            signature = self._get_node_text(params_node, source_code)

        # Get JavaDoc comment
        docstring = self._extract_javadoc(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="constructor",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._normalize_signature(signature) if signature else None,
            decorators=decorators,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_method_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract method signature with type parameters, parameters and return type."""
        parts = []

        # Get type parameters (generics)
        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            type_params_text = self._get_node_text(type_params, source_code)
            parts.append(type_params_text)

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Get return type
        return_type_node = node.child_by_field_name("type")
        if return_type_node:
            return_text = self._get_node_text(return_type_node, source_code).strip()
            parts.append(f": {return_text}")

        signature = " ".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers like public, private, static, final, abstract, synchronized."""
        modifiers = []

        for child in node.children:
            if child.type == "modifiers":
                for modifier in child.children:
                    if modifier.type in ("public", "private", "protected", "static",
                                        "final", "abstract", "synchronized", "native",
                                        "strictfp", "transient", "volatile"):
                        modifiers.append(modifier.type)

        return modifiers

    def _extract_annotations(self, node: Node, source_code: bytes) -> list[str]:
        """Extract annotations from a class/method/field."""
        annotations = []

        # First, check for modifiers node which contains annotations
        for child in node.children:
            if child.type == "modifiers":
                # Annotations are inside modifiers node
                for modifier_child in child.children:
                    if modifier_child.type in ("marker_annotation", "annotation"):
                        ann_text = self._get_node_text(modifier_child, source_code).strip()
                        annotations.append(ann_text)
                break  # Found modifiers, no need to continue

        # Also check previous siblings (annotations can sometimes be separate)
        prev = node.prev_sibling
        prev_annotations = []
        while prev:
            if prev.type == "marker_annotation" or prev.type == "annotation":
                ann_text = self._get_node_text(prev, source_code).strip()
                prev_annotations.insert(0, ann_text)  # Insert at beginning to maintain order
                prev = prev.prev_sibling
            else:
                break  # Stop when we hit a non-annotation

        # Prepend any previous sibling annotations
        annotations = prev_annotations + annotations

        return annotations

    def _extract_javadoc(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract first line of JavaDoc comment."""
        prev = node.prev_sibling

        # JavaDoc comments are typically previous siblings
        while prev:
            if prev.type == "block_comment":
                comment_text = self._get_node_text(prev, source_code).strip()
                # Check if it's a JavaDoc comment (/** ... */)
                if comment_text.startswith("/**"):
                    # Extract first meaningful line
                    lines = comment_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        # Remove comment markers
                        line = line.replace("/**", "").replace("*/", "").replace("*", "").strip()
                        if line and not line.startswith("@"):  # Skip JavaDoc tags
                            return line
                return None
            prev = prev.prev_sibling

        return None

    def _extract_type_parameters(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract type parameters (generics) like <T> or <K, V>."""
        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            return self._get_node_text(type_params, source_code)
        return None

    def _handle_package(self, node: Node, parent_structures: list, source_code: bytes):
        """Handle package declaration."""
        package_name_node = None
        for child in node.children:
            if child.type == "scoped_identifier" or child.type == "identifier":
                package_name_node = child
                break

        if package_name_node:
            package_name = self._get_node_text(package_name_node, source_code)
            package_node = StructureNode(
                type="package",
                name=package_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(package_node)

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

        # Find package declaration
        package_match = re.search(r'^\s*package\s+([\w.]+)\s*;', text, re.MULTILINE)
        if package_match:
            line_num = text[:package_match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="package",
                name=package_match.group(1),
                start_line=line_num,
                end_line=line_num
            ))

        # Find class definitions
        for match in re.finditer(r'^\s*(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find interface definitions
        for match in re.finditer(r'^\s*(?:public\s+)?interface\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="interface",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum definitions
        for match in re.finditer(r'^\s*(?:public\s+)?enum\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="enum",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find method definitions
        for match in re.finditer(r'^\s*(?:public|private|protected)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        return structures
