"""Swift language scanner with tree-sitter-based structure extraction."""

import re
from typing import Optional

import tree_sitter_swift
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class SwiftScanner(BaseScanner):
    """Scanner for Swift files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_swift.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".swift"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Swift"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Swift source code and extract structure with metadata."""
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
                        name="invalid syntax",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1
                    )
                    parent_structures.append(error_node)
                return

            # class_declaration is used for class, struct, enum, extension, actor
            if node.type == "class_declaration":
                type_node = self._extract_type_declaration(node, source_code)
                if type_node:
                    parent_structures.append(type_node)

            # Protocol declaration
            elif node.type == "protocol_declaration":
                protocol_node = self._extract_protocol(node, source_code)
                if protocol_node:
                    parent_structures.append(protocol_node)

            # Function declaration (standalone)
            elif node.type == "function_declaration":
                func_node = self._extract_function(node, source_code)
                if func_node:
                    parent_structures.append(func_node)

            # Typealias declaration
            elif node.type == "typealias_declaration":
                typealias_node = self._extract_typealias(node, source_code)
                if typealias_node:
                    parent_structures.append(typealias_node)

            # Import declarations
            elif node.type == "import_declaration":
                self._handle_import(node, parent_structures)

            else:
                # Keep traversing for other node types
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_type_declaration(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract type declaration (class, struct, enum, extension, actor).

        In tree-sitter-swift, class_declaration is used for all these types.
        The actual type is determined by the keyword child.
        """
        # Determine the actual type by looking at keywords
        type_kind = "class"  # default
        for child in node.children:
            if child.type == "struct":
                type_kind = "struct"
                break
            elif child.type == "enum":
                type_kind = "enum"
                break
            elif child.type == "class":
                type_kind = "class"
                break
            elif child.type == "extension":
                type_kind = "extension"
                break
            elif child.type == "actor":
                type_kind = "actor"
                break

        # Get the type name
        name = None
        for child in node.children:
            if child.type == "type_identifier":
                name = self._get_node_text(child, source_code)
                break
            elif child.type == "user_type" and type_kind == "extension":
                # Extensions use user_type for the extended type
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        inheritance = self._extract_inheritance(node, source_code)

        signature = None
        if inheritance:
            signature = f": {', '.join(inheritance)}"

        complexity = self._calculate_complexity(node)
        children = self._extract_type_members(node, source_code, type_kind)

        return StructureNode(
            type=type_kind,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            complexity=complexity,
            children=children
        )

    def _extract_protocol(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract protocol declaration."""
        name = None
        for child in node.children:
            if child.type == "type_identifier":
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        inheritance = self._extract_inheritance(node, source_code)

        signature = None
        if inheritance:
            signature = f": {', '.join(inheritance)}"

        complexity = self._calculate_complexity(node)
        children = self._extract_protocol_members(node, source_code)

        return StructureNode(
            type="protocol",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            complexity=complexity,
            children=children
        )

    def _extract_function(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract function declaration."""
        name = None
        for child in node.children:
            if child.type == "simple_identifier":
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        signature = self._extract_function_signature(node, source_code)
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="function",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            complexity=complexity,
            children=[]
        )

    def _extract_typealias(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract typealias declaration."""
        name = None
        alias_type = None

        for child in node.children:
            if child.type == "type_identifier" and name is None:
                name = self._get_node_text(child, source_code)
            elif child.type in ("user_type", "function_type", "tuple_type", "optional_type"):
                alias_type = self._get_node_text(child, source_code)

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        docstring = self._extract_docstring(node, source_code)

        signature = f"= {alias_type}" if alias_type else None

        return StructureNode(
            type="typealias",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_type_members(self, node: Node, source_code: bytes, parent_type: str) -> list[StructureNode]:
        """Extract members from a type declaration."""
        members = []

        # Find the body node
        body = None
        for child in node.children:
            if child.type in ("class_body", "enum_class_body"):
                body = child
                break

        if not body:
            return members

        for child in body.children:
            if child.type == "function_declaration":
                func = self._extract_function(child, source_code)
                if func:
                    func.type = "method"
                    members.append(func)

            elif child.type == "property_declaration":
                prop = self._extract_property(child, source_code)
                if prop:
                    members.append(prop)

            elif child.type == "subscript_declaration":
                subscript = self._extract_subscript(child, source_code)
                if subscript:
                    members.append(subscript)

            elif child.type == "init_declaration":
                init = self._extract_initializer(child, source_code)
                if init:
                    members.append(init)

            elif child.type == "deinit_declaration":
                deinit_node = StructureNode(
                    type="deinitializer",
                    name="deinit",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    docstring=self._extract_docstring(child, source_code),
                    children=[]
                )
                members.append(deinit_node)

            elif child.type == "enum_entry":
                case_node = self._extract_enum_case(child, source_code)
                if case_node:
                    members.append(case_node)

            # Nested types
            elif child.type == "class_declaration":
                nested = self._extract_type_declaration(child, source_code)
                if nested:
                    members.append(nested)

            elif child.type == "protocol_declaration":
                nested = self._extract_protocol(child, source_code)
                if nested:
                    members.append(nested)

        return members

    def _extract_protocol_members(self, node: Node, source_code: bytes) -> list[StructureNode]:
        """Extract members from a protocol declaration."""
        members = []

        # Find protocol body
        body = None
        for child in node.children:
            if child.type == "protocol_body":
                body = child
                break

        if not body:
            return members

        for child in body.children:
            if child.type == "protocol_function_declaration":
                func = self._extract_protocol_function(child, source_code)
                if func:
                    members.append(func)

            elif child.type == "protocol_property_declaration":
                prop = self._extract_property(child, source_code)
                if prop:
                    members.append(prop)

        return members

    def _extract_protocol_function(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract protocol function declaration."""
        name = None
        for child in node.children:
            if child.type == "simple_identifier":
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        signature = self._extract_function_signature(node, source_code)

        return StructureNode(
            type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_property(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract property declaration."""
        name = None

        # Look for pattern with simple_identifier
        for child in node.children:
            if child.type == "pattern":
                for sub in child.children:
                    if sub.type == "simple_identifier":
                        name = self._get_node_text(sub, source_code)
                        break
                if name:
                    break

        if not name:
            # Try value_binding_pattern for let/var declarations
            for child in node.children:
                if child.type == "value_binding_pattern":
                    for sub in child.children:
                        if sub.type == "pattern":
                            for inner in sub.children:
                                if inner.type == "simple_identifier":
                                    name = self._get_node_text(inner, source_code)
                                    break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)

        # Get type annotation
        type_annotation = None
        for child in node.children:
            if child.type == "type_annotation":
                type_annotation = self._get_node_text(child, source_code)
                break

        return StructureNode(
            type="property",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=type_annotation,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            children=[]
        )

    def _extract_subscript(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract subscript declaration."""
        modifiers = self._extract_modifiers(node, source_code)
        docstring = self._extract_docstring(node, source_code)

        # Build signature from parameters
        params = []
        for child in node.children:
            if child.type == "parameter":
                params.append(self._get_node_text(child, source_code))

        signature = f"[{', '.join(params)}]" if params else None

        return StructureNode(
            type="subscript",
            name="subscript",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_initializer(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract initializer declaration."""
        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        signature = self._extract_function_signature(node, source_code)

        # Determine init type (init, init?, init!)
        name = "init"
        node_text = self._get_node_text(node, source_code)
        if "init?" in node_text[:20]:
            name = "init?"
        elif "init!" in node_text[:20]:
            name = "init!"

        return StructureNode(
            type="initializer",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            children=[]
        )

    def _extract_enum_case(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract enum case."""
        name = None
        for child in node.children:
            if child.type == "simple_identifier":
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        # Check for associated values
        signature = None
        for child in node.children:
            if child.type == "enum_type_parameters":
                signature = self._get_node_text(child, source_code)
                break

        docstring = self._extract_docstring(node, source_code)

        return StructureNode(
            type="case",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            children=[]
        )

    def _extract_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers from a declaration."""
        modifiers = []
        modifier_keywords = {
            "public", "private", "internal", "fileprivate", "open",
            "static", "class", "final", "lazy",
            "mutating", "nonmutating",
            "async", "nonisolated",
            "required", "convenience", "override",
            "weak", "unowned", "optional"
        }

        for child in node.children:
            if child.type == "modifiers":
                # Traverse all children of modifiers
                for mod_child in child.children:
                    # Extract text from the deepest level
                    mod_text = self._get_node_text(mod_child, source_code).strip()
                    if mod_text in modifier_keywords:
                        modifiers.append(mod_text)
                    else:
                        # Check leaf nodes
                        for leaf in mod_child.children:
                            leaf_text = self._get_node_text(leaf, source_code).strip()
                            if leaf_text in modifier_keywords:
                                modifiers.append(leaf_text)

            # Also check for 'class' as direct child (for class methods)
            elif child.type == "class" and node.type == "function_declaration":
                modifiers.append("class")

        return modifiers

    def _extract_decorators(self, node: Node, source_code: bytes) -> list[str]:
        """Extract attributes/decorators from a declaration."""
        decorators = []

        for child in node.children:
            if child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type == "attribute":
                        attr_text = self._get_node_text(mod_child, source_code).strip()
                        decorators.append(attr_text)

            elif child.type == "attribute":
                attr_text = self._get_node_text(child, source_code).strip()
                decorators.append(attr_text)

        return decorators

    def _extract_docstring(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract documentation comment preceding a declaration."""
        prev = node.prev_sibling

        # Skip over attributes
        while prev and prev.type in ("modifiers", "attribute"):
            prev = prev.prev_sibling

        comments = []
        while prev and prev.type == "comment":
            comment_text = self._get_node_text(prev, source_code).strip()

            # Handle /// documentation comments
            if comment_text.startswith("///"):
                comment_text = comment_text[3:].strip()
                comments.insert(0, comment_text)
            # Handle // regular comments
            elif comment_text.startswith("//"):
                comment_text = comment_text[2:].strip()
                comments.insert(0, comment_text)
            # Handle /* */ block comments
            elif comment_text.startswith("/*"):
                comment_text = comment_text[2:]
                if comment_text.endswith("*/"):
                    comment_text = comment_text[:-2]
                comment_text = comment_text.strip()
                if comment_text:
                    comments.insert(0, comment_text)

            prev = prev.prev_sibling

        if comments:
            return comments[0]
        return None

    def _extract_inheritance(self, node: Node, source_code: bytes) -> list[str]:
        """Extract inherited types/protocols from a declaration."""
        inheritance = []

        for child in node.children:
            if child.type == "inheritance_specifier":
                for spec_child in child.children:
                    if spec_child.type == "user_type":
                        type_name = self._get_node_text(spec_child, source_code)
                        inheritance.append(type_name)
                    elif spec_child.type == "type_identifier":
                        type_name = self._get_node_text(spec_child, source_code)
                        inheritance.append(type_name)

            elif child.type == "type_constraints":
                for constraint in child.children:
                    if constraint.type == "type_constraint":
                        constraint_text = self._get_node_text(constraint, source_code)
                        inheritance.append(f"where {constraint_text}")

        return inheritance

    def _extract_function_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature with parameters and return type."""
        parts = []
        in_params = False
        has_arrow = False

        for child in node.children:
            if child.type == "(":
                in_params = True
                parts.append("(")
            elif child.type == ")":
                parts.append(")")
                in_params = False
            elif child.type == "parameter" and in_params:
                param_text = self._get_node_text(child, source_code)
                if parts and parts[-1] != "(":
                    parts.append(", ")
                parts.append(param_text)
            elif child.type == "->":
                has_arrow = True
                parts.append(" -> ")
            elif child.type == "throws":
                parts.append(" throws")
            elif child.type == "async":
                parts.append(" async")
            elif child.type == "user_type" and has_arrow:
                # Return type
                parts.append(self._get_node_text(child, source_code))
            elif child.type == "type_identifier" and has_arrow:
                # Simple return type
                parts.append(self._get_node_text(child, source_code))
            elif child.type in ("tuple_type", "optional_type", "function_type") and has_arrow:
                parts.append(self._get_node_text(child, source_code))

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

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
            parent_structures[-1].end_line = node.end_point[0] + 1

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for severely malformed files."""
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find class declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+|open\s+|final\s+)*class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find struct declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+)*struct\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="struct",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find protocol declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+)*protocol\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="protocol",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+)*enum\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="enum",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find extension declarations
        for match in re.finditer(r'^extension\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="extension",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+|static\s+|class\s+)*func\s+(\w+)\s*[<(]', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="function",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        return structures
