"""Scanner for C and C++ files."""

import re
from typing import Optional

import tree_sitter_cpp
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class CCppScanner(BaseScanner):
    """Scanner for C and C++ files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_cpp.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"]

    @classmethod
    def get_language_name(cls) -> str:
        return "C/C++"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan C/C++ source code and extract structure with metadata."""
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

            # Structs
            if node.type == "struct_specifier":
                struct_node = self._extract_struct(node, source_code)
                if struct_node:
                    parent_structures.append(struct_node)
                    # Traverse children for nested declarations
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            traverse(child, struct_node.children)

            # Classes (C++)
            elif node.type == "class_specifier":
                class_node = self._extract_class(node, source_code)
                if class_node:
                    parent_structures.append(class_node)
                    # Traverse children for methods and nested structures
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            traverse(child, class_node.children)

            # Enums
            elif node.type == "enum_specifier":
                enum_node = self._extract_enum(node, source_code)
                if enum_node:
                    parent_structures.append(enum_node)

            # Namespaces (C++)
            elif node.type == "namespace_definition":
                namespace_node = self._extract_namespace(node, source_code)
                if namespace_node:
                    parent_structures.append(namespace_node)
                    # Traverse children
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            traverse(child, namespace_node.children)

            # Functions (both declarations and definitions)
            elif node.type == "function_definition":
                func_node = self._extract_function(node, source_code, root)
                if func_node:
                    parent_structures.append(func_node)

            # Function declarations
            elif node.type == "declaration":
                # Check if this is a function declaration
                func_node = self._extract_function_declaration(node, source_code, root)
                if func_node:
                    parent_structures.append(func_node)

            # Method definitions (inside classes)
            elif node.type == "field_declaration":
                method_node = self._extract_method(node, source_code)
                if method_node:
                    parent_structures.append(method_node)

            # Preprocessor includes
            elif node.type == "preproc_include":
                self._handle_include(node, parent_structures, source_code)

            else:
                # Keep traversing for top-level structures
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_struct(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract struct declaration."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous struct
            return None

        name = self._get_node_text(name_node, source_code)

        # Get comment
        comment = self._extract_comment(node, source_code)

        return StructureNode(
            type="struct",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=comment,
            children=[]
        )

    def _extract_class(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract C++ class declaration."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous class
            return None

        name = self._get_node_text(name_node, source_code)

        # Get base classes
        bases = self._extract_base_classes(node, source_code)
        signature = bases if bases else None

        # Get comment
        comment = self._extract_comment(node, source_code)

        # Get modifiers (from declaration context)
        modifiers = self._extract_class_modifiers(node, source_code)

        return StructureNode(
            type="class",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=comment,
            modifiers=modifiers,
            children=[]
        )

    def _extract_enum(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract enum declaration."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous enum
            return None

        name = self._get_node_text(name_node, source_code)

        # Get comment
        comment = self._extract_comment(node, source_code)

        return StructureNode(
            type="enum",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=comment,
            children=[]
        )

    def _extract_namespace(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract C++ namespace declaration."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous namespace
            name = "<anonymous>"
        else:
            name = self._get_node_text(name_node, source_code)

        # Get comment
        comment = self._extract_comment(node, source_code)

        return StructureNode(
            type="namespace",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=comment,
            children=[]
        )

    def _extract_function(self, node: Node, source_code: bytes, root: Node) -> Optional[StructureNode]:
        """Extract function definition."""
        declarator = node.child_by_field_name("declarator")
        if not declarator:
            return None

        # Get function name from declarator
        name = self._extract_function_name(declarator, source_code)
        if not name:
            return None

        # Determine if it's a method or function
        is_method = any(p.type in ("class_specifier", "struct_specifier") for p in self._get_ancestors(root, node))
        type_name = "method" if is_method else "function"

        # Get signature
        signature = self._extract_function_signature(declarator, source_code)

        # Get return type
        return_type = self._extract_return_type(node, source_code)
        if return_type and signature:
            signature = f"{return_type} {signature}"

        # Get comment
        comment = self._extract_comment(node, source_code)

        # Get modifiers
        modifiers = self._extract_function_modifiers(node, source_code)

        # Get attributes
        attributes = self._extract_attributes(node, source_code)
        if attributes:
            modifiers.extend(attributes)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type=type_name,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._normalize_signature(signature) if signature else None,
            docstring=comment,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_function_declaration(self, node: Node, source_code: bytes, root: Node) -> Optional[StructureNode]:
        """Extract function declaration (not definition)."""
        # Find declarator in the declaration
        declarator = None
        for child in node.children:
            if child.type == "function_declarator":
                declarator = child
                break
            # Look deeper if needed
            if child.type == "init_declarator":
                for subchild in child.children:
                    if subchild.type == "function_declarator":
                        declarator = subchild
                        break

        if not declarator:
            return None

        # Get function name
        name = self._extract_function_name(declarator, source_code)
        if not name:
            return None

        # Determine if it's a method or function
        is_method = any(p.type in ("class_specifier", "struct_specifier") for p in self._get_ancestors(root, node))
        type_name = "method" if is_method else "function"

        # Get signature
        signature = self._extract_function_signature(declarator, source_code)

        # Get return type
        return_type = self._extract_return_type(node, source_code)
        if return_type and signature:
            signature = f"{return_type} {signature}"

        # Get comment
        comment = self._extract_comment(node, source_code)

        # Get modifiers
        modifiers = self._extract_function_modifiers(node, source_code)

        return StructureNode(
            type=type_name,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._normalize_signature(signature) if signature else None,
            docstring=comment,
            modifiers=modifiers,
            children=[]
        )

    def _extract_method(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract method from field declaration."""
        # Check if this field declaration is actually a method
        declarator = None
        for child in node.children:
            if child.type == "function_declarator":
                declarator = child
                break

        if not declarator:
            return None

        # Get method name
        name = self._extract_function_name(declarator, source_code)
        if not name:
            return None

        # Get signature
        signature = self._extract_function_signature(declarator, source_code)

        # Get return type
        return_type = self._extract_return_type(node, source_code)
        if return_type and signature:
            signature = f"{return_type} {signature}"

        # Get comment
        comment = self._extract_comment(node, source_code)

        # Get modifiers (public, private, protected, virtual, static, const)
        modifiers = self._extract_method_modifiers(node, source_code)

        return StructureNode(
            type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._normalize_signature(signature) if signature else None,
            docstring=comment,
            modifiers=modifiers,
            children=[]
        )

    def _extract_function_name(self, declarator: Node, source_code: bytes) -> Optional[str]:
        """Extract function name from declarator."""
        # The declarator can have different structures
        # Look for identifier or field_identifier
        for child in declarator.children:
            if child.type in ("identifier", "field_identifier", "destructor_name"):
                return self._get_node_text(child, source_code)
            elif child.type == "qualified_identifier":
                # Get last part of qualified name
                for subchild in reversed(child.children):
                    if subchild.type == "identifier":
                        return self._get_node_text(subchild, source_code)
            elif child.type in ("pointer_declarator", "reference_declarator"):
                # Recurse into pointer/reference declarators
                name = self._extract_function_name(child, source_code)
                if name:
                    return name

        return None

    def _extract_function_signature(self, declarator: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature (parameters)."""
        params_node = declarator.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            return params_text
        return None

    def _extract_return_type(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract return type from function node."""
        type_node = node.child_by_field_name("type")
        if type_node:
            return_type = self._get_node_text(type_node, source_code).strip()
            return return_type
        return None

    def _extract_base_classes(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract base classes from class declaration."""
        parts = []

        for child in node.children:
            if child.type == "base_class_clause":
                # Get full base class clause text
                base_text = self._get_node_text(child, source_code).strip()
                # Remove leading colon if present
                if base_text.startswith(":"):
                    base_text = base_text[1:].strip()
                parts.append(base_text)

        return ": " + ", ".join(parts) if parts else None

    def _extract_comment(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract comment before node."""
        prev = node.prev_sibling

        # Look for comment nodes before this node
        while prev:
            if prev.type == "comment":
                comment_text = self._get_node_text(prev, source_code).strip()
                # Parse comment (// or /* */)
                if comment_text.startswith("//"):
                    return comment_text[2:].strip()
                elif comment_text.startswith("/*"):
                    # Extract first line of block comment
                    lines = comment_text[2:-2].strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        # Remove leading asterisks
                        if line.startswith("*"):
                            line = line[1:].strip()
                        if line:
                            return line
                return None
            prev = prev.prev_sibling

        return None

    def _extract_class_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for classes."""
        modifiers = []

        # Look at parent to see if it's a template
        parent = node.parent
        if parent and parent.type == "template_declaration":
            modifiers.append("template")

        return modifiers

    def _extract_function_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for functions (static, inline, virtual, const, etc.)."""
        modifiers = []

        # Check for storage class specifiers
        for child in node.children:
            if child.type == "storage_class_specifier":
                modifier_text = self._get_node_text(child, source_code)
                modifiers.append(modifier_text)
            elif child.type == "type_qualifier":
                qualifier_text = self._get_node_text(child, source_code)
                modifiers.append(qualifier_text)
            elif child.type == "virtual":
                modifiers.append("virtual")

        # Check declarator for const
        declarator = node.child_by_field_name("declarator")
        if declarator:
            for child in declarator.children:
                if child.type == "type_qualifier" and "const" in self._get_node_text(child, source_code):
                    if "const" not in modifiers:
                        modifiers.append("const")

        return modifiers

    def _extract_method_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for methods (public, private, protected, virtual, static, const)."""
        modifiers = []

        # Check for access specifiers (handled at class level typically)
        # Check for storage class specifiers and qualifiers
        for child in node.children:
            if child.type == "storage_class_specifier":
                modifier_text = self._get_node_text(child, source_code)
                modifiers.append(modifier_text)
            elif child.type == "type_qualifier":
                qualifier_text = self._get_node_text(child, source_code)
                modifiers.append(qualifier_text)
            elif child.type == "virtual_specifier":
                modifiers.append("virtual")
            elif child.type == "virtual":
                modifiers.append("virtual")

        return modifiers

    def _extract_attributes(self, node: Node, source_code: bytes) -> list[str]:
        """Extract C++ attributes like [[nodiscard]], __attribute__, etc."""
        attributes = []

        for child in node.children:
            if child.type == "attribute_declaration":
                attr_text = self._get_node_text(child, source_code).strip()
                attributes.append(attr_text)
            elif child.type == "attribute_specifier":
                attr_text = self._get_node_text(child, source_code).strip()
                attributes.append(attr_text)

        return attributes

    def _handle_include(self, node: Node, parent_structures: list, source_code: bytes):
        """Group include statements together."""
        if not parent_structures or parent_structures[-1].type != "includes":
            include_node = StructureNode(
                type="includes",
                name="#include directives",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(include_node)
        else:
            # Extend the end line of the existing include group
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
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find struct definitions
        for match in re.finditer(r'\bstruct\s+(\w+)\s*\{', text):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="struct",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find class definitions
        for match in re.finditer(r'\bclass\s+(\w+)', text):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum definitions
        for match in re.finditer(r'\benum\s+(?:class\s+)?(\w+)', text):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="enum",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find namespace definitions
        for match in re.finditer(r'\bnamespace\s+(\w+)', text):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="namespace",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function definitions (basic pattern)
        for match in re.finditer(r'\b(\w+)\s+(\w+)\s*\([^)]*\)\s*\{', text):
            line_num = text[:match.start()].count('\n') + 1
            return_type = match.group(1)
            func_name = match.group(2)
            structures.append(StructureNode(
                type="function",
                name=func_name + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        return structures
