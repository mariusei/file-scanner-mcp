"""File scanner for extracting structure and creating table of contents."""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_rust
import tree_sitter_go
import tree_sitter_markdown
from tree_sitter import Language, Parser, Node


@dataclass
class StructureNode:
    """Represents a node in the file structure."""

    type: str  # e.g., "class", "function", "heading"
    name: str
    start_line: int
    end_line: int
    children: list["StructureNode"]

    def __repr__(self):
        return f"{self.type}: {self.name} ({self.start_line}-{self.end_line})"


class FileScanner:
    """Scans files and extracts their structure."""

    LANGUAGE_MAP = {
        ".py": ("python", Language(tree_sitter_python.language())),
        ".js": ("javascript", Language(tree_sitter_javascript.language())),
        ".jsx": ("javascript", Language(tree_sitter_javascript.language())),
        ".ts": ("typescript", Language(tree_sitter_typescript.language_typescript())),
        ".tsx": ("tsx", Language(tree_sitter_typescript.language_tsx())),
        ".rs": ("rust", Language(tree_sitter_rust.language())),
        ".go": ("go", Language(tree_sitter_go.language())),
        ".md": ("markdown", Language(tree_sitter_markdown.language())),
    }

    def __init__(self):
        self.parser = Parser()

    def scan_file(self, file_path: str) -> Optional[list[StructureNode]]:
        """Scan a file and return its structure."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect language
        suffix = path.suffix.lower()
        if suffix not in self.LANGUAGE_MAP:
            return None

        lang_name, language = self.LANGUAGE_MAP[suffix]
        self.parser.language = language

        # Read and parse file
        with open(file_path, "rb") as f:
            source_code = f.read()

        tree = self.parser.parse(source_code)

        # Extract structure based on language
        if lang_name == "python":
            return self._extract_python_structure(tree.root_node, source_code)
        elif lang_name in ("javascript", "typescript", "tsx"):
            return self._extract_js_structure(tree.root_node, source_code)
        elif lang_name == "rust":
            return self._extract_rust_structure(tree.root_node, source_code)
        elif lang_name == "go":
            return self._extract_go_structure(tree.root_node, source_code)
        elif lang_name == "markdown":
            return self._extract_markdown_structure(tree.root_node, source_code)

        return None

    def _get_node_text(self, node: Node, source_code: bytes) -> str:
        """Extract text from a node."""
        return source_code[node.start_byte:node.end_byte].decode("utf-8")

    def _extract_python_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract structure from Python code."""
        structures = []

        def traverse(node: Node, parent_structures: list):
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                class_node = StructureNode(
                    type="class",
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )
                parent_structures.append(class_node)

                # Traverse children for methods
                for child in node.children:
                    traverse(child, class_node.children)

            elif node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                # Check if this is a method (inside a class)
                type_name = "method" if any(p.type == "class_definition" for p in self._get_ancestors(root, node)) else "function"

                func_node = StructureNode(
                    type=type_name,
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )
                parent_structures.append(func_node)

            elif node.type == "import_statement" or node.type == "import_from_statement":
                # Group imports
                if not parent_structures or parent_structures[-1].type != "imports":
                    import_node = StructureNode(
                        type="imports",
                        name="import statements",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        children=[]
                    )
                    parent_structures.append(import_node)
                else:
                    # Extend the end line of the existing import group
                    parent_structures[-1].end_line = node.end_point[0] + 1

            else:
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

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

    def _extract_js_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract structure from JavaScript/TypeScript code."""
        structures = []

        def traverse(node: Node, parent_structures: list):
            if node.type in ("class_declaration", "class"):
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                class_node = StructureNode(
                    type="class",
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )
                parent_structures.append(class_node)

                for child in node.children:
                    traverse(child, class_node.children)

            elif node.type in ("function_declaration", "method_definition", "arrow_function", "function"):
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "anonymous"

                type_name = "method" if node.type == "method_definition" else "function"

                func_node = StructureNode(
                    type=type_name,
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )
                parent_structures.append(func_node)

            elif node.type in ("import_statement", "import_clause"):
                if not parent_structures or parent_structures[-1].type != "imports":
                    import_node = StructureNode(
                        type="imports",
                        name="import statements",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        children=[]
                    )
                    parent_structures.append(import_node)
                else:
                    parent_structures[-1].end_line = node.end_point[0] + 1

            else:
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_rust_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract structure from Rust code."""
        structures = []

        def traverse(node: Node, parent_structures: list):
            if node.type in ("struct_item", "enum_item", "trait_item", "impl_item"):
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                struct_node = StructureNode(
                    type=node.type.replace("_item", ""),
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )
                parent_structures.append(struct_node)

                for child in node.children:
                    traverse(child, struct_node.children)

            elif node.type == "function_item":
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                func_node = StructureNode(
                    type="function",
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )
                parent_structures.append(func_node)

            elif node.type == "use_declaration":
                if not parent_structures or parent_structures[-1].type != "imports":
                    import_node = StructureNode(
                        type="imports",
                        name="use statements",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        children=[]
                    )
                    parent_structures.append(import_node)
                else:
                    parent_structures[-1].end_line = node.end_point[0] + 1

            else:
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_go_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract structure from Go code."""
        structures = []

        def traverse(node: Node, parent_structures: list):
            if node.type in ("type_declaration", "type_spec"):
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                type_node = StructureNode(
                    type="type",
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )
                parent_structures.append(type_node)

                for child in node.children:
                    traverse(child, type_node.children)

            elif node.type in ("function_declaration", "method_declaration"):
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                type_name = "method" if node.type == "method_declaration" else "function"

                func_node = StructureNode(
                    type=type_name,
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )
                parent_structures.append(func_node)

            elif node.type == "import_declaration":
                if not parent_structures or parent_structures[-1].type != "imports":
                    import_node = StructureNode(
                        type="imports",
                        name="import statements",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        children=[]
                    )
                    parent_structures.append(import_node)
                else:
                    parent_structures[-1].end_line = node.end_point[0] + 1

            else:
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_markdown_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract structure from Markdown files."""
        structures = []
        heading_stack = []  # Stack to track heading hierarchy

        def get_heading_level(node: Node) -> int:
            """Get the level of a heading (1-6)."""
            for child in node.children:
                if child.type == "atx_h1_marker":
                    return 1
                elif child.type == "atx_h2_marker":
                    return 2
                elif child.type == "atx_h3_marker":
                    return 3
                elif child.type == "atx_h4_marker":
                    return 4
                elif child.type == "atx_h5_marker":
                    return 5
                elif child.type == "atx_h6_marker":
                    return 6
            return 1

        def get_heading_text(node: Node) -> str:
            """Extract heading text."""
            for child in node.children:
                if child.type == "inline":
                    return self._get_node_text(child, source_code).strip()
            return "untitled"

        def traverse(node: Node):
            if node.type == "atx_heading":
                level = get_heading_level(node)
                text = get_heading_text(node)

                heading_node = StructureNode(
                    type=f"heading-{level}",
                    name=text,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )

                # Pop headings from stack that are at same or deeper level
                while heading_stack and int(heading_stack[-1][0].type.split("-")[1]) >= level:
                    heading_stack.pop()

                # Add to parent or root
                if heading_stack:
                    heading_stack[-1][0].children.append(heading_node)
                else:
                    structures.append(heading_node)

                # Push to stack with level
                heading_stack.append((heading_node, level))

            elif node.type == "fenced_code_block":
                # Extract code block language if present
                lang = "code"
                info_node = node.child_by_field_name("info_string")
                if info_node:
                    lang = self._get_node_text(info_node, source_code).strip()

                code_node = StructureNode(
                    type="code-block",
                    name=f"```{lang}```",
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )

                # Add to current heading or root
                if heading_stack:
                    heading_stack[-1][0].children.append(code_node)
                else:
                    structures.append(code_node)

            else:
                for child in node.children:
                    traverse(child)

        traverse(root)
        return structures
