"""Scanner for C# files."""

import re
from typing import Optional

import tree_sitter_c_sharp
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class CSharpScanner(BaseScanner):
    """Scanner for C# files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_c_sharp.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".cs", ".csx"]

    @classmethod
    def get_language_name(cls) -> str:
        return "C#"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan C# source code and extract structure with metadata."""
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

            # Using directives
            if node.type == "using_directive":
                self._handle_using(node, parent_structures)

            # Namespace declaration
            elif node.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
                self._handle_namespace(node, parent_structures, source_code, root, traverse)

            # Classes
            elif node.type == "class_declaration":
                class_node = self._extract_class(node, source_code)
                parent_structures.append(class_node)

                # Traverse children for methods, properties, nested classes, etc.
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, class_node.children)

            # Interfaces
            elif node.type == "interface_declaration":
                interface_node = self._extract_interface(node, source_code)
                parent_structures.append(interface_node)

                # Traverse children for method signatures, properties
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, interface_node.children)

            # Structs
            elif node.type == "struct_declaration":
                struct_node = self._extract_struct(node, source_code)
                parent_structures.append(struct_node)

                # Traverse children for methods, properties, etc.
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, struct_node.children)

            # Enums
            elif node.type == "enum_declaration":
                enum_node = self._extract_enum(node, source_code)
                parent_structures.append(enum_node)

            # Methods
            elif node.type == "method_declaration":
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Properties
            elif node.type == "property_declaration":
                property_node = self._extract_property(node, source_code)
                parent_structures.append(property_node)

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

    def _extract_class(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract class with full metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)

        # Get base class and interfaces
        signature_parts = []
        if type_params:
            signature_parts.append(type_params)

        # Get base list (base class and interfaces)
        base_list = node.child_by_field_name("bases")
        if base_list:
            base_text = self._get_node_text(base_list, source_code).strip()
            # Remove the colon if present
            base_text = base_text.lstrip(':').strip()
            signature_parts.append(f": {base_text}")

        signature = " ".join(signature_parts) if signature_parts else None

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)

        # Get base interfaces
        signature_parts = []
        if type_params:
            signature_parts.append(type_params)

        base_list = node.child_by_field_name("bases")
        if base_list:
            base_text = self._get_node_text(base_list, source_code).strip()
            base_text = base_text.lstrip(':').strip()
            signature_parts.append(f": {base_text}")

        signature = " ".join(signature_parts) if signature_parts else None

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

    def _extract_struct(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract struct declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)

        # Get interfaces
        signature_parts = []
        if type_params:
            signature_parts.append(type_params)

        base_list = node.child_by_field_name("bases")
        if base_list:
            base_text = self._get_node_text(base_list, source_code).strip()
            base_text = base_text.lstrip(':').strip()
            signature_parts.append(f": {base_text}")

        signature = " ".join(signature_parts) if signature_parts else None

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

        return StructureNode(
            type="struct",
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

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get base type (enums can have a base type like : byte)
        # Look for base_list child node
        signature = None
        for child in node.children:
            if child.type == "base_list":
                base_text = self._get_node_text(child, source_code).strip()
                base_text = base_text.lstrip(':').strip()
                signature = f": {base_text}"
                break

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

    def _extract_property(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract property declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get property type
        type_node = node.child_by_field_name("type")
        signature = None
        if type_node:
            type_text = self._get_node_text(type_node, source_code).strip()
            signature = f": {type_text}"

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

        return StructureNode(
            type="property",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_constructor(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract constructor declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get signature (parameters)
        params_node = node.child_by_field_name("parameters")
        signature = None
        if params_node:
            signature = self._get_node_text(params_node, source_code)

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

        # Get return type (it's a child before the method name)
        # Could be generic_name, predefined_type, identifier, etc.
        return_type = None
        name_node = node.child_by_field_name("name")
        for child in node.children:
            # Stop when we reach the name
            if child == name_node:
                break
            # Skip modifiers
            if child.type == "modifier":
                continue
            # This must be the return type
            if child.type in ("generic_name", "predefined_type", "identifier", "nullable_type",
                            "array_type", "qualified_name", "tuple_type"):
                return_type = self._get_node_text(child, source_code).strip()
                break

        # Get type parameters (generics on method)
        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            type_params_text = self._get_node_text(type_params, source_code)
            parts.append(type_params_text)

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Add return type at the end
        if return_type:
            parts.append(f": {return_type}")

        signature = " ".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers like public, private, static, readonly, async, virtual, override, abstract."""
        modifiers = []

        for child in node.children:
            if child.type == "modifier":
                # Modifier is wrapped - get the actual keyword
                modifier_text = self._get_node_text(child, source_code).strip()
                if modifier_text:
                    modifiers.append(modifier_text)

        return modifiers

    def _extract_attributes(self, node: Node, source_code: bytes) -> list[str]:
        """Extract attributes (C# decorators) from a class/method/property."""
        attributes = []

        # In C#, attributes are children of the node, appearing before modifiers
        for child in node.children:
            if child.type == "attribute_list":
                attr_text = self._get_node_text(child, source_code).strip()
                attributes.append(attr_text)

        return attributes

    def _extract_xml_doc(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract first line of XML documentation comment (///)."""
        # Try to find comments before the node
        start_byte = node.start_byte

        # Look backwards in source to find XML doc comments
        text = source_code.decode('utf-8', errors='replace')
        lines_before = text[:start_byte].split('\n')

        # Collect XML doc comment lines (///)
        doc_lines = []
        for line in reversed(lines_before):
            stripped = line.strip()
            if stripped.startswith('///'):
                # Remove /// and extract content
                content = stripped[3:].strip()
                # Extract from <summary> tags if present
                if '<summary>' in content:
                    content = content.replace('<summary>', '').strip()
                if '</summary>' in content:
                    content = content.replace('</summary>', '').strip()
                if content and not content.startswith('<') and not content.startswith('/'):
                    doc_lines.insert(0, content)
            elif stripped and not stripped.startswith('//'):
                # Stop at first non-comment line
                break

        # Return first meaningful line
        for line in doc_lines:
            if line and not line.startswith('<') and not line.startswith('/'):
                return line

        return None

    def _extract_type_parameters(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract type parameters (generics) like <T> or <TKey, TValue>."""
        # Try field-based access first
        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            return self._get_node_text(type_params, source_code)

        # Fallback: look for type_parameter_list child
        for child in node.children:
            if child.type == "type_parameter_list":
                return self._get_node_text(child, source_code)

        return None

    def _handle_namespace(self, node: Node, parent_structures: list, source_code: bytes, root: Node, traverse_func):
        """Handle namespace declaration."""
        name_node = node.child_by_field_name("name")

        if name_node:
            namespace_name = self._get_node_text(name_node, source_code)
            namespace_node = StructureNode(
                type="namespace",
                name=namespace_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                children=[]
            )
            parent_structures.append(namespace_node)

            # Traverse children within namespace
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    traverse_func(child, namespace_node.children)
            else:
                # File-scoped namespace - traverse remaining children
                for child in node.children:
                    if child.start_point[0] > node.start_point[0]:
                        traverse_func(child, namespace_node.children)

    def _handle_using(self, node: Node, parent_structures: list):
        """Group using directives together."""
        if not parent_structures or parent_structures[-1].type != "imports":
            import_node = StructureNode(
                type="imports",
                name="using directives",
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

        # Find namespace declaration
        namespace_match = re.search(r'^\s*namespace\s+([\w.]+)', text, re.MULTILINE)
        if namespace_match:
            line_num = text[:namespace_match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="namespace",
                name=namespace_match.group(1),
                start_line=line_num,
                end_line=line_num
            ))

        # Find class definitions
        for match in re.finditer(r'^\s*(?:public\s+)?(?:abstract\s+)?(?:sealed\s+)?class\s+(\w+)', text, re.MULTILINE):
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

        # Find struct definitions
        for match in re.finditer(r'^\s*(?:public\s+)?struct\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="struct",
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
        for match in re.finditer(r'^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:async\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find property definitions
        for match in re.finditer(r'^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\{', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="property",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        return structures
