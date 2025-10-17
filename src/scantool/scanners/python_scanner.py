"""Python language scanner with full signature and metadata extraction."""

import re
from typing import Optional

import tree_sitter_python
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class PythonScanner(BaseScanner):
    """Scanner for Python files with rich metadata extraction."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_python.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".py", ".pyw"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Python"

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip common Python files that are typically auto-generated or empty."""
        # Skip if filename matches these patterns
        if filename == "__init__.py":
            # Note: Some __init__.py files have content, but many are empty
            # We still scan them, just noting they're often boilerplate
            pass

        # Skip Python cache/compiled files (shouldn't match .py extension anyway)
        if filename.endswith(('.pyc', '.pyo', '.pyd')):
            return True

        return False

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Python source code and extract structure with metadata."""
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
            if node.type == "class_definition":
                class_node = self._extract_class(node, source_code, root)
                parent_structures.append(class_node)

                # Traverse children for methods
                for child in node.children:
                    traverse(child, class_node.children)

            # Functions/Methods
            elif node.type == "function_definition":
                func_node = self._extract_function(node, source_code, root)
                parent_structures.append(func_node)

            # Imports
            elif node.type in ("import_statement", "import_from_statement"):
                self._handle_import(node, parent_structures)

            else:
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_class(self, node: Node, source_code: bytes, root: Node) -> StructureNode:
        """Extract class with full metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get decorators
        decorators = self._extract_decorators(node, source_code)

        # Get base classes
        superclasses = self._extract_superclasses(node, source_code)
        signature = f"({', '.join(superclasses)})" if superclasses else None

        # Get docstring
        docstring = self._extract_docstring(node, source_code)

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
            children=[]
        )

    def _extract_function(self, node: Node, source_code: bytes, root: Node) -> StructureNode:
        """Extract function/method with signature and metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Determine if it's a method or function
        is_method = any(p.type == "class_definition" for p in self._get_ancestors(root, node))
        type_name = "method" if is_method else "function"

        # Get signature
        signature = self._extract_signature(node, source_code)

        # Get decorators
        decorators = self._extract_decorators(node, source_code)

        # Get docstring
        docstring = self._extract_docstring(node, source_code)

        # Get modifiers (async, static, etc.)
        modifiers = self._extract_modifiers(node, decorators)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type=type_name,
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

    def _extract_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature with parameters and return type."""
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
            # Ensure proper formatting: " -> Type"
            if not return_text.startswith("->"):
                return_text = f"-> {return_text}"
            elif not return_text.startswith("-> "):
                return_text = return_text.replace("->", "-> ", 1)
            parts.append(f" {return_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_decorators(self, node: Node, source_code: bytes) -> list[str]:
        """Extract decorators from a function/class definition."""
        decorators = []
        prev = node.prev_sibling

        while prev and prev.type == "decorator":
            dec_text = self._get_node_text(prev, source_code).strip()
            decorators.insert(0, dec_text)  # Insert at beginning to maintain order
            prev = prev.prev_sibling

        return decorators

    def _extract_docstring(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract first line of docstring."""
        body = node.child_by_field_name("body")
        if not body or len(body.children) == 0:
            return None

        # First statement in body
        first_stmt = body.children[0]
        if first_stmt.type == "expression_statement":
            for child in first_stmt.children:
                if child.type == "string":
                    docstring = self._get_node_text(child, source_code)
                    # Strip quotes and get first non-empty line
                    docstring = docstring.strip('"""').strip("'''").strip('"').strip("'")
                    lines = [line.strip() for line in docstring.split('\n')]
                    # Find first non-empty line
                    for line in lines:
                        if line:
                            return line
                    return None

        return None

    def _extract_superclasses(self, node: Node, source_code: bytes) -> list[str]:
        """Extract base class names."""
        superclasses = []
        argument_list = node.child_by_field_name("superclasses")

        if argument_list:
            for child in argument_list.children:
                if child.type in ("identifier", "attribute"):
                    superclasses.append(self._get_node_text(child, source_code))

        return superclasses

    def _extract_modifiers(self, node: Node, decorators: list[str]) -> list[str]:
        """Extract modifiers like async, static, classmethod."""
        modifiers = []

        # Check for async
        for child in node.children:
            if child.type == "async":
                modifiers.append("async")
                break

        # Check decorators for common patterns
        for dec in decorators:
            if "@staticmethod" in dec:
                modifiers.append("static")
            elif "@classmethod" in dec:
                modifiers.append("classmethod")
            elif "@property" in dec:
                modifiers.append("property")
            elif "@abstractmethod" in dec:
                modifiers.append("abstract")

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

        # Find class definitions
        for match in re.finditer(r'^class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function definitions
        for match in re.finditer(r'^(async\s+)?def\s+(\w+)\s*\((.*?)\)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            is_async = match.group(1) is not None
            name = match.group(2)
            params = match.group(3)

            modifiers = ["async"] if is_async else []

            structures.append(StructureNode(
                type="function",
                name=name + " ⚠",
                start_line=line_num,
                end_line=line_num,
                signature=f"({params})",
                modifiers=modifiers
            ))

        return structures
