"""Scanner for Rust files."""

import re
from typing import Optional

import tree_sitter_rust
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class RustScanner(BaseScanner):
    """Scanner for Rust files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_rust.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".rs"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Rust"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Rust source code and extract structure."""
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
            if node.type == "struct_item":
                struct_node = self._extract_struct(node, source_code)
                parent_structures.append(struct_node)

            # Enums
            elif node.type == "enum_item":
                enum_node = self._extract_enum(node, source_code)
                parent_structures.append(enum_node)

            # Traits
            elif node.type == "trait_item":
                trait_node = self._extract_trait(node, source_code)
                parent_structures.append(trait_node)

                # Traverse children for trait methods
                for child in node.children:
                    traverse(child, trait_node.children)

            # Impl blocks
            elif node.type == "impl_item":
                impl_node = self._extract_impl(node, source_code)
                parent_structures.append(impl_node)

                # Traverse children for methods
                for child in node.children:
                    traverse(child, impl_node.children)

            # Functions (both standalone and in impl blocks)
            elif node.type == "function_item":
                func_node = self._extract_function(node, source_code, root)
                parent_structures.append(func_node)

            # Use statements (imports)
            elif node.type == "use_declaration":
                self._handle_import(node, parent_structures)

            else:
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_struct(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract struct with metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)
        signature = f"<{type_params}>" if type_params else None

        # Get attributes
        attributes = self._extract_attributes(node, source_code)

        # Get doc comments
        docstring = self._extract_doc_comment(node, source_code)

        # Get modifiers (pub, etc.)
        modifiers = self._extract_modifiers(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="struct",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=attributes,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_enum(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract enum with metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)
        signature = f"<{type_params}>" if type_params else None

        # Get attributes
        attributes = self._extract_attributes(node, source_code)

        # Get doc comments
        docstring = self._extract_doc_comment(node, source_code)

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="enum",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=attributes,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_trait(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract trait with metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get type parameters
        type_params = self._extract_type_parameters(node, source_code)
        signature = f"<{type_params}>" if type_params else None

        # Get attributes
        attributes = self._extract_attributes(node, source_code)

        # Get doc comments
        docstring = self._extract_doc_comment(node, source_code)

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        return StructureNode(
            type="trait",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=attributes,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_impl(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract impl block with metadata."""
        # Get the type being implemented
        type_node = node.child_by_field_name("type")
        type_name = self._get_node_text(type_node, source_code) if type_node else "unknown"

        # Check if it's a trait impl
        trait_node = node.child_by_field_name("trait")
        if trait_node:
            trait_name = self._get_node_text(trait_node, source_code)
            name = f"{trait_name} for {type_name}"
        else:
            name = type_name

        # Get type parameters
        type_params = self._extract_type_parameters(node, source_code)
        signature = f"<{type_params}>" if type_params else None

        # Get attributes
        attributes = self._extract_attributes(node, source_code)

        # Get doc comments
        docstring = self._extract_doc_comment(node, source_code)

        return StructureNode(
            type="impl",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=attributes,
            docstring=docstring,
            children=[]
        )

    def _extract_function(self, node: Node, source_code: bytes, root: Node) -> StructureNode:
        """Extract function with signature and metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Determine if it's a method or function
        is_method = any(p.type in ("impl_item", "trait_item") for p in self._get_ancestors(root, node))
        type_name = "method" if is_method else "function"

        # Get signature (parameters and return type)
        signature = self._extract_signature(node, source_code)

        # Get attributes
        attributes = self._extract_attributes(node, source_code)

        # Get doc comments
        docstring = self._extract_doc_comment(node, source_code)

        # Get modifiers (pub, async, unsafe, const)
        modifiers = self._extract_modifiers(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type=type_name,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=attributes,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature with parameters and return type."""
        parts = []

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)
        if type_params:
            parts.append(f"<{type_params}>")

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Get return type
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_text = self._get_node_text(return_type_node, source_code).strip()
            # Ensure proper formatting
            if not return_text.startswith("->"):
                return_text = f"-> {return_text}"
            elif not return_text.startswith("-> "):
                return_text = return_text.replace("->", "-> ", 1)
            parts.append(f" {return_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_type_parameters(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract type parameters (generics and lifetimes)."""
        type_params_node = node.child_by_field_name("type_parameters")
        if type_params_node:
            text = self._get_node_text(type_params_node, source_code).strip()
            # Remove outer brackets
            if text.startswith("<") and text.endswith(">"):
                text = text[1:-1]
            return text
        return None

    def _extract_attributes(self, node: Node, source_code: bytes) -> list[str]:
        """Extract attributes like #[derive(...)], #[test], etc."""
        attributes = []
        prev = node.prev_sibling

        while prev:
            if prev.type == "attribute_item":
                attr_text = self._get_node_text(prev, source_code).strip()
                attributes.insert(0, attr_text)  # Insert at beginning to maintain order
                prev = prev.prev_sibling
            elif prev.type in ("line_comment", "block_comment"):
                # Skip comments
                prev = prev.prev_sibling
            else:
                break

        return attributes

    def _extract_doc_comment(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract doc comments (/// or /**/)."""
        prev = node.prev_sibling

        # Collect all consecutive doc comments
        doc_lines = []
        while prev:
            if prev.type == "line_comment":
                comment_text = self._get_node_text(prev, source_code).strip()
                if comment_text.startswith("///"):
                    # Remove /// and whitespace
                    doc_text = comment_text[3:].strip()
                    if doc_text:
                        doc_lines.insert(0, doc_text)
                    prev = prev.prev_sibling
                else:
                    break
            elif prev.type == "block_comment":
                comment_text = self._get_node_text(prev, source_code).strip()
                if comment_text.startswith("/**") and not comment_text.startswith("/***"):
                    # Remove /** and */ and extract first line
                    doc_text = comment_text[3:-2].strip()
                    lines = [line.strip().lstrip('*').strip() for line in doc_text.split('\n')]
                    for line in lines:
                        if line:
                            return line
                    break
                else:
                    break
            elif prev.type == "attribute_item":
                # Skip attributes
                prev = prev.prev_sibling
            else:
                break

        # Return first non-empty doc line
        if doc_lines:
            return doc_lines[0]

        return None

    def _extract_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers like pub, async, unsafe, const."""
        modifiers = []

        # Check all children for modifiers
        for child in node.children:
            # Visibility modifier
            if child.type == "visibility_modifier":
                vis_text = self._get_node_text(child, source_code).strip()
                if vis_text == "pub":
                    modifiers.append("pub")
                elif vis_text.startswith("pub("):
                    modifiers.append(vis_text)
            # Function modifiers (async, unsafe, const, extern)
            elif child.type == "function_modifiers":
                for mod_child in child.children:
                    if mod_child.type in ("async", "unsafe", "const", "extern"):
                        modifiers.append(mod_child.type)
            # Direct modifiers (for other contexts)
            elif child.type in ("async", "unsafe", "const", "extern"):
                modifiers.append(child.type)

        return modifiers

    def _handle_import(self, node: Node, parent_structures: list):
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
        for match in re.finditer(r'^\s*pub\s+struct\s+(\w+)|^\s*struct\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1) or match.group(2)
            structures.append(StructureNode(
                type="struct",
                name=name + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum definitions
        for match in re.finditer(r'^\s*pub\s+enum\s+(\w+)|^\s*enum\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1) or match.group(2)
            structures.append(StructureNode(
                type="enum",
                name=name + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find trait definitions
        for match in re.finditer(r'^\s*pub\s+trait\s+(\w+)|^\s*trait\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1) or match.group(2)
            structures.append(StructureNode(
                type="trait",
                name=name + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function definitions
        for match in re.finditer(r'^\s*pub\s+(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?fn\s+(\w+)|^\s*(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?fn\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1) or match.group(2)
            structures.append(StructureNode(
                type="function",
                name=name + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        return structures
