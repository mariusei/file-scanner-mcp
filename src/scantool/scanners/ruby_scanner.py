"""Ruby language scanner with full signature and metadata extraction."""

import re
from typing import Optional

import tree_sitter_ruby
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class RubyScanner(BaseScanner):
    """Scanner for Ruby files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_ruby.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".rb", ".rake", ".gemspec"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Ruby"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Ruby source code and extract structure with metadata."""
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

            # Modules
            if node.type == "module":
                module_node = self._extract_module(node, source_code)
                parent_structures.append(module_node)

                # Traverse children for nested structures
                for child in node.children:
                    traverse(child, module_node.children)

            # Classes
            elif node.type == "class":
                class_node = self._extract_class(node, source_code)
                parent_structures.append(class_node)

                # Traverse children for methods
                for child in node.children:
                    traverse(child, class_node.children)

            # Regular methods
            elif node.type == "method":
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Singleton methods (def self.method_name)
            elif node.type == "singleton_method":
                method_node = self._extract_singleton_method(node, source_code)
                parent_structures.append(method_node)

            # Require statements
            elif node.type == "call" and self._is_require_call(node, source_code):
                self._handle_require(node, parent_structures)

            else:
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_module(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract module with metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get comment above module
        docstring = self._extract_comment(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="module",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=docstring,
            complexity=complexity,
            children=[]
        )

    def _extract_class(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract class with full metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get superclass
        superclass_node = node.child_by_field_name("superclass")
        signature = None
        if superclass_node:
            superclass = self._get_node_text(superclass_node, source_code)
            signature = f"< {superclass}"

        # Get comment above class
        docstring = self._extract_comment(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="class",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            complexity=complexity,
            children=[]
        )

    def _extract_method(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract regular method with signature and metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get parameters
        signature = self._extract_method_signature(node, source_code)

        # Get comment above method
        docstring = self._extract_comment(node, source_code)

        # Check for visibility modifiers in name or context
        modifiers = self._extract_visibility_modifiers(node, source_code)

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

    def _extract_singleton_method(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract singleton method (class method) with metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get object (usually 'self')
        object_node = node.child_by_field_name("object")
        receiver = self._get_node_text(object_node, source_code) if object_node else "self"

        # Get parameters
        signature = self._extract_method_signature(node, source_code)

        # Get comment above method
        docstring = self._extract_comment(node, source_code)

        # Singleton methods are class methods
        modifiers = ["class"]

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="method",
            name=f"{receiver}.{name}",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_method_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract method signature with parameters."""
        params_node = node.child_by_field_name("parameters")

        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            # Normalize the signature
            return self._normalize_signature(params_text)

        return "()"

    def _extract_comment(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract comment above or near a declaration."""
        # Strategy 1: Look for comment as previous sibling
        # This finds comments directly above the declaration
        prev = node.prev_sibling
        while prev:
            if prev.type == "comment":
                comment_text = self._get_node_text(prev, source_code)
                comment_text = comment_text.lstrip('#').strip()
                if comment_text:
                    return comment_text
            # Stop at non-whitespace, non-comment nodes
            if prev.type not in ("comment", "\n"):
                break
            prev = prev.prev_sibling

        # Strategy 2: For nodes inside body_statement (like classes inside modules),
        # check parent's previous sibling for comments
        if node.parent and node.parent.type == "body_statement":
            parent_prev = node.parent.prev_sibling
            while parent_prev:
                if parent_prev.type == "comment":
                    comment_text = self._get_node_text(parent_prev, source_code)
                    comment_text = comment_text.lstrip('#').strip()
                    if comment_text:
                        return comment_text
                # Stop at non-comment nodes
                if parent_prev.type not in ("comment", "\n"):
                    break
                parent_prev = parent_prev.prev_sibling

        return None

    def _extract_visibility_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract visibility modifiers (public, private, protected)."""
        modifiers = []

        # In Ruby, visibility is typically determined by context
        # We could check for explicit visibility declarations, but for simplicity
        # we'll return public by default unless we detect private/protected context
        # This would require more complex traversal of the tree

        return modifiers

    def _is_require_call(self, node: Node, source_code: bytes) -> bool:
        """Check if a call node is a require or require_relative statement."""
        method_node = node.child_by_field_name("method")
        if method_node:
            method_name = self._get_node_text(method_node, source_code)
            return method_name in ("require", "require_relative")
        return False

    def _handle_require(self, node: Node, parent_structures: list):
        """Group require statements together."""
        if not parent_structures or parent_structures[-1].type != "requires":
            require_node = StructureNode(
                type="requires",
                name="require statements",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(require_node)
        else:
            # Extend the end line of the existing require group
            parent_structures[-1].end_line = node.end_point[0] + 1

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for severely malformed files."""
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find module definitions
        for match in re.finditer(r'^module\s+(\w+(?:::\w+)*)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="module",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find class definitions
        for match in re.finditer(r'^class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find method definitions
        for match in re.finditer(r'^def\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find singleton method definitions
        for match in re.finditer(r'^def\s+(self\.\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num,
                modifiers=["class"]
            ))

        return structures
