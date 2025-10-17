"""TypeScript and TSX language scanner with type annotations and JSDoc extraction."""

import re
from typing import Optional

import tree_sitter_typescript
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class TypeScriptScanner(BaseScanner):
    """
    Scanner for TypeScript and TSX files.

    Extracts:
    - Classes and interfaces
    - Functions and methods
    - Type annotations
    - JSDoc comments
    - Import statements
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        # tree-sitter-typescript provides both typescript and tsx parsers
        # Use language_tsx for all TypeScript files as it's a superset that handles both
        self.parser.language = Language(tree_sitter_typescript.language_tsx())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]

    @classmethod
    def get_language_name(cls) -> str:
        return "TypeScript/JavaScript"

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip common TypeScript/JavaScript files that should be ignored."""
        # Skip minified files (auto-generated, unreadable)
        if filename.endswith(('.min.js', '.min.mjs', '.min.cjs')):
            return True

        # Skip TypeScript declaration files (type-only, no implementation)
        if filename.endswith('.d.ts'):
            return True

        # Skip webpack/rollup bundles (auto-generated)
        if 'bundle' in filename.lower() or 'chunk' in filename.lower():
            return True

        return False

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan TypeScript/TSX source code and extract structure with metadata."""
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

            # Classes
            if node.type == "class_declaration":
                class_node = self._extract_class(node, source_code, root)
                parent_structures.append(class_node)

                # Traverse children for methods
                for child in node.children:
                    traverse(child, class_node.children)

            # Interfaces
            elif node.type == "interface_declaration":
                interface_node = self._extract_interface(node, source_code)
                parent_structures.append(interface_node)

                # Traverse children for interface members
                for child in node.children:
                    traverse(child, interface_node.children)

            # Functions
            elif node.type in ("function_declaration", "function_signature"):
                func_node = self._extract_function(node, source_code, root)
                parent_structures.append(func_node)

            # Methods (inside classes)
            elif node.type in ("method_definition", "method_signature"):
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Arrow functions (const foo = () => {})
            elif node.type == "lexical_declaration":
                arrow_func = self._extract_arrow_function(node, source_code)
                if arrow_func:
                    parent_structures.append(arrow_func)

            # Export statements (may contain other structures)
            elif node.type == "export_statement":
                # Traverse children to find what's being exported
                for child in node.children:
                    traverse(child, parent_structures)

            # Imports
            elif node.type == "import_statement":
                self._handle_import(node, parent_structures)

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

        # Get decorators (TypeScript uses decorators too)
        decorators = self._extract_decorators(node, source_code)

        # Get heritage (extends, implements)
        heritage = self._extract_heritage(node, source_code)
        signature = heritage if heritage else None

        # Get JSDoc comment
        docstring = self._extract_jsdoc(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        # Check for modifiers
        modifiers = self._extract_class_modifiers(node, source_code)

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

        # Get heritage (extends)
        heritage = self._extract_heritage(node, source_code)
        signature = heritage if heritage else None

        # Get JSDoc comment
        docstring = self._extract_jsdoc(node, source_code)

        return StructureNode(
            type="interface",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            children=[]
        )

    def _extract_function(self, node: Node, source_code: bytes, root: Node) -> StructureNode:
        """Extract function with signature and metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get signature
        signature = self._extract_signature(node, source_code)

        # Get JSDoc comment
        docstring = self._extract_jsdoc(node, source_code)

        # Get modifiers (async, export, etc.)
        modifiers = self._extract_function_modifiers(node, source_code)

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
        """Extract method from class."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get signature
        signature = self._extract_signature(node, source_code)

        # Get JSDoc comment
        docstring = self._extract_jsdoc(node, source_code)

        # Get decorators
        decorators = self._extract_decorators(node, source_code)

        # Get modifiers (async, static, private, public, etc.)
        modifiers = self._extract_method_modifiers(node, source_code)

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

    def _extract_arrow_function(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract arrow function assigned to a const/let/var."""
        # Look for pattern: const/let/var name = () => {}
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")

                if value_node and value_node.type == "arrow_function":
                    name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                    # Get signature
                    signature = self._extract_arrow_signature(value_node, source_code)

                    # Get JSDoc comment (from lexical_declaration)
                    docstring = self._extract_jsdoc(node, source_code)

                    # Check for async
                    modifiers = []
                    for n in value_node.children:
                        if n.type == "async":
                            modifiers.append("async")
                            break

                    # Calculate complexity
                    complexity = self._calculate_complexity(value_node)

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

        return None

    def _extract_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract function/method signature with parameters and return type."""
        parts = []

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Get return type annotation
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_text = self._get_node_text(return_type_node, source_code).strip()
            # TypeScript uses : Type syntax
            if not return_text.startswith(":"):
                return_text = f": {return_text}"
            parts.append(f" {return_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_arrow_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract arrow function signature."""
        parts = []

        # Get parameters
        for child in node.children:
            if child.type == "formal_parameters":
                params_text = self._get_node_text(child, source_code)
                parts.append(params_text)
                break

        # Get return type
        for child in node.children:
            if child.type == "type_annotation":
                type_text = self._get_node_text(child, source_code).strip()
                parts.append(f" {type_text}")
                break

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_decorators(self, node: Node, source_code: bytes) -> list[str]:
        """Extract decorators from a function/class/method."""
        decorators = []
        prev = node.prev_sibling

        while prev and prev.type == "decorator":
            dec_text = self._get_node_text(prev, source_code).strip()
            decorators.insert(0, dec_text)  # Insert at beginning to maintain order
            prev = prev.prev_sibling

        return decorators

    def _extract_jsdoc(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract first line of JSDoc comment."""
        prev = node.prev_sibling

        # JSDoc comments are typically previous siblings
        while prev:
            if prev.type == "comment":
                comment_text = self._get_node_text(prev, source_code).strip()
                # Check if it's a JSDoc comment (/** ... */)
                if comment_text.startswith("/**"):
                    # Extract first meaningful line
                    lines = comment_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        # Remove comment markers
                        line = line.replace("/**", "").replace("*/", "").replace("*", "").strip()
                        if line and not line.startswith("@"):  # Skip JSDoc tags
                            return line
                return None
            prev = prev.prev_sibling

        return None

    def _extract_heritage(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract extends/implements clause."""
        parts = []

        for child in node.children:
            if child.type == "class_heritage":
                heritage_text = self._get_node_text(child, source_code).strip()
                parts.append(heritage_text)
            elif child.type == "extends_clause":
                extends_text = self._get_node_text(child, source_code).strip()
                parts.append(extends_text)
            elif child.type == "implements_clause":
                implements_text = self._get_node_text(child, source_code).strip()
                parts.append(implements_text)

        return " ".join(parts) if parts else None

    def _extract_class_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for classes (export, abstract, etc.)."""
        modifiers = []

        for child in node.children:
            if child.type == "export":
                modifiers.append("export")
            elif child.type == "abstract":
                modifiers.append("abstract")

        return modifiers

    def _extract_function_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for functions (async, export, etc.)."""
        modifiers = []

        for child in node.children:
            if child.type == "async":
                modifiers.append("async")
            elif child.type == "export":
                modifiers.append("export")

        return modifiers

    def _extract_method_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for methods (async, static, private, public, etc.)."""
        modifiers = []

        for child in node.children:
            if child.type == "async":
                modifiers.append("async")
            elif child.type == "static":
                modifiers.append("static")
            elif child.type == "readonly":
                modifiers.append("readonly")
            elif child.type == "accessibility_modifier":
                # public, private, protected
                modifier_text = self._get_node_text(child, source_code)
                modifiers.append(modifier_text)

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

        # Find class definitions
        for match in re.finditer(r'^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find interface definitions
        for match in re.finditer(r'^\s*(?:export\s+)?interface\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="interface",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function definitions
        for match in re.finditer(r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(<[^>]+>)?\s*\((.*?)\)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1)
            generics = match.group(2) or ""
            params = match.group(3)

            structures.append(StructureNode(
                type="function",
                name=name + " ⚠",
                start_line=line_num,
                end_line=line_num,
                signature=f"{generics}({params})"
            ))

        # Find arrow functions
        for match in re.finditer(r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="function",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        return structures
