"""
Template for creating a new language scanner.

Copy this file to create your scanner:
    cp _template.py YOUR_LANGUAGE_scanner.py

Then search for "TODO" and fill in the blanks!
"""

import re
from typing import Optional

# TODO: Import tree-sitter for your language
# import tree_sitter_YOUR_LANGUAGE
# from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode


class YourLanguageScanner(BaseScanner):
    """
    Scanner for YOUR_LANGUAGE files.

    TODO: Update this docstring with language-specific details.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # TODO: If using tree-sitter, initialize parser here:
        # self.parser = Parser()
        # self.parser.language = Language(tree_sitter_YOUR_LANGUAGE.language())

        # TODO: If NOT using tree-sitter (like text_scanner.py),
        # you can delete this __init__ method entirely!

    @classmethod
    def get_extensions(cls) -> list[str]:
        """Return list of file extensions this scanner handles."""
        # TODO: Fill in your file extensions
        return [".TODO"]  # Example: [".rb"] for Ruby, [".java"] for Java

    @classmethod
    def get_language_name(cls) -> str:
        """Return the human-readable language name."""
        # TODO: Fill in your language name
        return "TODO Language"  # Example: "Ruby", "Java", "C++"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """
        Scan source code and extract structure.

        This is the main entry point for your scanner.
        """
        try:
            # TODO: Choose one of the two approaches below:

            # ===== APPROACH 1: Using tree-sitter (recommended for most languages) =====
            # Uncomment and modify this section:

            # tree = self.parser.parse(source_code)
            #
            # # Check if we should use fallback due to too many errors
            # if self._should_use_fallback(tree.root_node):
            #     return self._fallback_extract(source_code)
            #
            # return self._extract_structure(tree.root_node, source_code)

            # ===== APPROACH 2: Direct parsing (for simple formats like text, CSV, etc.) =====
            # Uncomment and modify this section:

            # text = source_code.decode("utf-8", errors="ignore")
            # lines = text.split("\n")
            #
            # structures = []
            # # TODO: Add your parsing logic here
            # # Example: detect sections, paragraphs, etc.
            #
            # return structures

            # TODO: Remove this placeholder once you implement one of the approaches
            return [StructureNode(
                type="todo",
                name="Scanner not yet implemented",
                start_line=1,
                end_line=1
            )]

        except Exception as e:
            # Return error node instead of crashing
            return [StructureNode(
                type="error",
                name=f"Failed to parse: {str(e)}",
                start_line=1,
                end_line=1
            )]

    # ===== TREE-SITTER APPROACH: Helper methods =====
    # TODO: If using tree-sitter, implement these methods

    def _extract_structure(self, root, source_code: bytes) -> list[StructureNode]:
        """
        Extract structure using tree-sitter.

        This method traverses the parse tree and extracts interesting nodes.
        """
        structures = []

        def traverse(node, parent_structures: list):
            # Handle parse errors without crashing
            if node.type == "ERROR":
                if self.show_errors:
                    parent_structures.append(StructureNode(
                        type="parse-error",
                        name="⚠ invalid syntax",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1
                    ))
                return

            # TODO: Add detection for your language's structures
            # Examples:

            # if node.type == "class_declaration":  # or "class_definition", depends on language
            #     name_node = node.child_by_field_name("name")
            #     name = self._get_node_text(name_node, source_code) if name_node else "unnamed"
            #
            #     class_node = StructureNode(
            #         type="class",
            #         name=name,
            #         start_line=node.start_point[0] + 1,
            #         end_line=node.end_point[0] + 1,
            #         children=[]
            #     )
            #     parent_structures.append(class_node)
            #
            #     # Recurse into children
            #     for child in node.children:
            #         traverse(child, class_node.children)

            # elif node.type == "function_declaration":  # or "method_definition", etc.
            #     name_node = node.child_by_field_name("name")
            #     name = self._get_node_text(name_node, source_code) if name_node else "unnamed"
            #
            #     # Extract signature if available
            #     signature = self._extract_signature(node, source_code)
            #
            #     func_node = StructureNode(
            #         type="function",
            #         name=name,
            #         start_line=node.start_point[0] + 1,
            #         end_line=node.end_point[0] + 1,
            #         signature=signature,
            #         children=[]
            #     )
            #     parent_structures.append(func_node)

            # else:
            #     # Keep traversing for other nodes
            #     for child in node.children:
            #         traverse(child, parent_structures)

            # TODO: Remove this placeholder
            pass

        traverse(root, structures)
        return structures

    def _extract_signature(self, node, source_code: bytes) -> Optional[str]:
        """
        Extract function/method signature with parameters and return type.

        This is optional but highly valuable for users!
        """
        # TODO: Implement signature extraction
        # Example for languages with parameters and return types:

        # parts = []
        #
        # # Get parameters
        # params = node.child_by_field_name("parameters")
        # if params:
        #     params_text = self._get_node_text(params, source_code)
        #     parts.append(params_text)
        #
        # # Get return type (if your language has them)
        # return_type = node.child_by_field_name("return_type")
        # if return_type:
        #     type_text = self._get_node_text(return_type, source_code).strip()
        #     parts.append(f" -> {type_text}")
        #
        # return "".join(parts) if parts else None

        return None  # TODO: Remove when implemented

    def _extract_decorators(self, node, source_code: bytes) -> list[str]:
        """
        Extract decorators/annotations (Python @decorator, Java @Annotation, etc.).

        This is optional but valuable!
        """
        # TODO: Implement decorator extraction if your language has them
        # Example (Python-style):

        # decorators = []
        # prev = node.prev_sibling
        #
        # while prev and prev.type == "decorator":  # TODO: Adjust type name
        #     dec_text = self._get_node_text(prev, source_code).strip()
        #     decorators.insert(0, dec_text)
        #     prev = prev.prev_sibling
        #
        # return decorators

        return []  # TODO: Remove when implemented

    def _extract_docstring(self, node, source_code: bytes) -> Optional[str]:
        """
        Extract first line of documentation/comment.

        This is optional but very valuable for users!
        """
        # TODO: Implement docstring extraction if your language has them
        # Example (Python-style):

        # body = node.child_by_field_name("body")
        # if body and len(body.children) > 0:
        #     first_stmt = body.children[0]
        #     if first_stmt.type == "expression_statement":
        #         for child in first_stmt.children:
        #             if child.type == "string":
        #                 doc = self._get_node_text(child, source_code)
        #                 # Clean and get first line
        #                 doc = doc.strip('"""').strip("'''").split('\n')[0].strip()
        #                 return doc if doc else None
        #
        # return None

        return None  # TODO: Remove when implemented

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """
        Regex-based extraction for severely malformed files.

        This is used when tree-sitter encounters too many errors.
        """
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # TODO: Add regex patterns for your language
        # Examples:

        # # Find class definitions
        # for match in re.finditer(r'^class\s+(\w+)', text, re.MULTILINE):
        #     line_num = text[:match.start()].count('\n') + 1
        #     structures.append(StructureNode(
        #         type="class",
        #         name=match.group(1) + " ⚠",  # ⚠ indicates fallback mode
        #         start_line=line_num,
        #         end_line=line_num
        #     ))
        #
        # # Find function definitions
        # for match in re.finditer(r'^def\s+(\w+)\s*\((.*?)\)', text, re.MULTILINE):
        #     line_num = text[:match.start()].count('\n') + 1
        #     name = match.group(1)
        #     params = match.group(2)
        #     structures.append(StructureNode(
        #         type="function",
        #         name=name + " ⚠",
        #         start_line=line_num,
        #         end_line=line_num,
        #         signature=f"({params})"
        #     ))

        return structures


# ===== QUICK REFERENCE =====
#
# Useful BaseScanner methods you can use:
#   - self._get_node_text(node, source_code) -> str
#     Extract text from a tree-sitter node
#
#   - self._calculate_complexity(node) -> dict
#     Calculate complexity metrics (lines, depth, branches)
#
#   - self._count_error_nodes(node) -> int
#     Count ERROR nodes in tree
#
#   - self._should_use_fallback(root_node) -> bool
#     Check if there are too many errors (>50%)
#
# StructureNode fields:
#   Required:
#     - type: str (e.g., "class", "function", "method")
#     - name: str (e.g., "UserManager", "create_user")
#     - start_line: int (1-indexed)
#     - end_line: int (1-indexed)
#     - children: list[StructureNode] (can be empty)
#
#   Optional (set these for richer output!):
#     - signature: str (e.g., "(name: str, age: int) -> User")
#     - decorators: list[str] (e.g., ["@property", "@staticmethod"])
#     - docstring: str (first line of documentation)
#     - modifiers: list[str] (e.g., ["async", "static", "public"])
#     - complexity: dict (from self._calculate_complexity)
#
# ===== TESTING YOUR SCANNER =====
#
# 1. Create test file: tests/samples/example.YOUR_EXT
# 2. Test manually:
#    uv run python -c "
#    from scantool.scanner import FileScanner
#    from scantool.formatter import TreeFormatter
#    scanner = FileScanner()
#    formatter = TreeFormatter()
#    structures = scanner.scan_file('tests/samples/example.YOUR_EXT')
#    print(formatter.format('tests/samples/example.YOUR_EXT', structures))
#    "
#
# 3. Create formal test: tests/scanners/test_YOUR_LANGUAGE.py
#
# ===== DEBUGGING TIPS =====
#
# Print tree-sitter parse tree:
#   tree = self.parser.parse(source_code)
#   print(tree.root_node.sexp())
#
# Print node types:
#   def print_types(node, depth=0):
#       print("  " * depth + node.type)
#       for child in node.children:
#           print_types(child, depth + 1)
#   print_types(tree.root_node)
#
# ===== GOOD LUCK! =====
#
# Check python_scanner.py for a full-featured example
# Check text_scanner.py for a simple non-tree-sitter example
