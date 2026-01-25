"""Java language support - unified scanner and analyzer.

This module combines JavaScanner and JavaAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_java
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class JavaLanguage(BaseLanguage):
    """Unified language handler for Java files (.java).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract classes, interfaces, enums, methods with signatures and metadata
    - extract_imports(): Find import statements (regular and static)
    - find_entry_points(): Find main methods, Spring annotations, servlets
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Find method calls (not yet implemented)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_java.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".java"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Java"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip compiled Java files."""
        if filename.endswith('.class'):
            return True
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Skip compiled Java files.

        Java doesn't have many common generated file patterns like Go/Rust.
        Most generated code (like Lombok, annotation processors) is still
        valid for analysis. We skip nothing specific at this tier.

        build/ and target/ directories are already filtered by COMMON_SKIP_DIRS.
        """
        filename = Path(file_path).name
        if filename.endswith('.class'):
            return False
        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value Java files for inventory listing.

        Low-value files (unless central):
        - package-info.java (package documentation)
        - module-info.java (module declaration)
        """
        filename = Path(file_path).name

        if filename == "package-info.java":
            return True

        if filename == "module-info.java" and size < 200:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from JavaScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Java source code and extract structure with metadata."""
        try:
            tree = self.parser.parse(source_code)

            # Check if we should use fallback due to too many errors
            if self._should_use_fallback(tree.root_node):
                return self._fallback_extract(source_code)

            return self._extract_structure(tree.root_node, source_code)

        except Exception as e:
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
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find interface definitions
        for match in re.finditer(r'^\s*(?:public\s+)?interface\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="interface",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum definitions
        for match in re.finditer(r'^\s*(?:public\s+)?enum\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="enum",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find method definitions
        for match in re.finditer(r'^\s*(?:public|private|protected)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from JavaAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract import statements from Java file.

        Patterns supported:
        - import foo.bar.Baz;
        - import foo.bar.*;
        - import static foo.bar.Utils.*;
        - import static foo.bar.Utils.method;
        """
        imports = []

        # Pattern 1: Regular imports (import foo.bar.Baz;)
        # Matches: import foo.bar.Baz;
        # Matches: import foo.bar.*;
        regular_import_pattern = r'^\s*import\s+(?!static\s)([a-zA-Z_$][a-zA-Z0-9_.$*]*)\s*;'
        for match in re.finditer(regular_import_pattern, content, re.MULTILINE):
            package = match.group(1).strip()
            line_num = content[:match.start()].count('\n') + 1

            # Determine if wildcard import
            import_type = "wildcard" if package.endswith(".*") else "import"

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=package,
                    line=line_num,
                    import_type=import_type,
                )
            )

        # Pattern 2: Static imports (import static foo.bar.Utils.*;)
        # Matches: import static foo.bar.Utils.*;
        # Matches: import static foo.bar.Utils.method;
        static_import_pattern = r'^\s*import\s+static\s+([a-zA-Z_$][a-zA-Z0-9_.$*]*)\s*;'
        for match in re.finditer(static_import_pattern, content, re.MULTILINE):
            package = match.group(1).strip()
            line_num = content[:match.start()].count('\n') + 1

            # Extract class and member if possible
            # foo.bar.Utils.method -> Utils.method
            # foo.bar.Utils.* -> Utils.*
            parts = package.split('.')
            if len(parts) >= 2:
                imported_name = f"{parts[-2]}.{parts[-1]}"
            else:
                imported_name = package

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=package,
                    line=line_num,
                    import_type="static",
                    imported_names=[imported_name],
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in Java file.

        Entry points:
        - public static void main(String[] args)
        - @SpringBootApplication (Spring Boot entry)
        - @WebServlet (Servlet entry)
        - @RestController (Spring REST API)
        - @Controller (Spring MVC)
        """
        entry_points = []

        # Pattern 1: public static void main(String[] args)
        # Handles variations:
        # - public static void main(String[] args)
        # - public static void main(String args[])
        # - public static void main(String... args)
        main_pattern = r'public\s+static\s+void\s+main\s*\(\s*String\s*(?:\[\s*\]\s*\w+|\w+\s*\[\s*\]|\.{3}\s*\w+)\s*\)'
        for match in re.finditer(main_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Extract class name from file path
            class_name = Path(file_path).stem

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_method",
                    line=line_num,
                    name=f"{class_name}.main",
                )
            )

        # Pattern 2: @SpringBootApplication
        spring_boot_pattern = r'@SpringBootApplication'
        for match in re.finditer(spring_boot_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Find class name after annotation
            class_pattern = r'class\s+(\w+)'
            class_match = re.search(class_pattern, content[match.end():])
            class_name = class_match.group(1) if class_match else "Unknown"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="spring_boot_app",
                    line=line_num,
                    name=class_name,
                    framework="Spring Boot",
                )
            )

        # Pattern 3: @WebServlet
        # Matches: @WebServlet("/path")
        # Matches: @WebServlet(name = "MyServlet", urlPatterns = {"/path"})
        servlet_pattern = r'@WebServlet\s*(?:\([^)]*\))?'
        for match in re.finditer(servlet_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Extract servlet URL pattern if present
            url_match = re.search(r'[@(].*["\']([^"\']+)["\']', match.group(0))
            url_pattern = url_match.group(1) if url_match else None

            # Find class name after annotation
            class_pattern = r'class\s+(\w+)'
            class_match = re.search(class_pattern, content[match.end():])
            class_name = class_match.group(1) if class_match else "Unknown"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="servlet",
                    line=line_num,
                    name=f"{class_name}:{url_pattern}" if url_pattern else class_name,
                    framework="Servlet",
                )
            )

        # Pattern 4: @RestController (Spring REST API)
        rest_controller_pattern = r'@RestController'
        for match in re.finditer(rest_controller_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Find class name
            class_pattern = r'class\s+(\w+)'
            class_match = re.search(class_pattern, content[match.end():])
            class_name = class_match.group(1) if class_match else "Unknown"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="rest_controller",
                    line=line_num,
                    name=class_name,
                    framework="Spring",
                )
            )

        # Pattern 5: @Controller (Spring MVC)
        controller_pattern = r'@Controller\b'
        for match in re.finditer(controller_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Find class name
            class_pattern = r'class\s+(\w+)'
            class_match = re.search(class_pattern, content[match.end():])
            class_name = class_match.group(1) if class_match else "Unknown"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="controller",
                    line=line_num,
                    name=class_name,
                    framework="Spring",
                )
            )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract class/method definitions by reusing scan() output.

        This is the key optimization: instead of re-parsing with tree-sitter,
        we convert the StructureNode output from scan() to DefinitionInfo.
        """
        try:
            structures = self.scan(content.encode("utf-8"))
            if not structures:
                return []
            return self._structures_to_definitions(file_path, structures)
        except Exception:
            # Fallback to regex-based extraction
            return self._extract_definitions_regex(file_path, content)

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        for match in re.finditer(r"^\s*(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="class",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        for match in re.finditer(r"^\s*(?:public\s+)?interface\s+(\w+)", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="interface",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        for match in re.finditer(r"^\s*(?:public|private|protected)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="method",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        return definitions

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Extract method calls from Java file.

        Note: This is a basic implementation that extracts method calls.
        A full implementation would use tree-sitter for accuracy.
        """
        calls = []

        # Simple regex to find method calls: identifier(
        # This is a basic approach - tree-sitter would be more accurate
        call_pattern = r'\b(\w+)\s*\('
        for match in re.finditer(call_pattern, content):
            callee_name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            # Skip keywords and common Java keywords
            if callee_name in (
                "if", "for", "while", "switch", "catch", "synchronized",
                "return", "new", "class", "interface", "enum", "void",
                "int", "long", "double", "float", "boolean", "char",
                "byte", "short", "String", "Integer", "Long", "Double",
                "Float", "Boolean", "Object", "List", "Map", "Set",
            ):
                continue

            calls.append(
                CallInfo(
                    caller_file=file_path,
                    caller_name=None,  # Would need context tracking for this
                    callee_name=callee_name,
                    line=line,
                    is_cross_file=False,
                )
            )

        # Mark cross-file calls
        local_defs = {d.name for d in definitions}
        for call in calls:
            if call.callee_name not in local_defs:
                call.is_cross_file = True

        return calls

    # ===========================================================================
    # Classification (enhanced for Java)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify Java file into architectural cluster."""
        # Use base class classification first
        base_cluster = super().classify_file(file_path, content)

        # Java-specific patterns
        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points - check by annotation or main method
            if any(
                pattern in content
                for pattern in [
                    "@SpringBootApplication",
                    "public static void main",
                    "@WebServlet",
                ]
            ):
                return "entry_points"

            # Controllers and REST APIs
            if any(
                pattern in content
                for pattern in ["@RestController", "@Controller", "@WebServlet"]
            ):
                return "core_logic"

            # Test files - various test frameworks
            if (
                "Test" in Path(file_path).stem
                or name.startswith("test")
                or name.endswith("test.java")
                or "@Test" in content
                or "@junit" in content.lower()
                or "import org.junit" in content
                or "import org.testng" in content
            ):
                return "tests"

            # Models/Entities/DTOs
            if (
                "/models/" in path_lower
                or "/entities/" in path_lower
                or "/dto/" in path_lower
                or "@Entity" in content
                or "@Table" in content
            ):
                return "core_logic"

            # Services
            if "/services/" in path_lower or "@Service" in content:
                return "core_logic"

            # Repositories/DAOs
            if (
                "/repositories/" in path_lower
                or "/dao/" in path_lower
                or "@Repository" in content
            ):
                return "core_logic"

            # Configuration
            if (
                "/config/" in path_lower
                or name.endswith("config.java")
                or name.endswith("configuration.java")
                or "@Configuration" in content
            ):
                return "config"

        return base_cluster

    # ===========================================================================
    # CodeMap Integration
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> Optional[str]:
        """Resolve Java import to file path.

        Java imports are fully qualified class names:
        - com.example.MyClass -> com/example/MyClass.java

        Wildcard imports (.*) are skipped as they don't resolve to specific files.
        Standard library and external packages are skipped.
        """
        # Skip wildcard imports
        if module.endswith(".*"):
            return None

        # Skip java.* and javax.* (standard library)
        if module.startswith(("java.", "javax.", "sun.", "com.sun.")):
            return None

        # Convert package.ClassName to path/ClassName.java
        candidate = module.replace(".", "/") + ".java"
        if candidate in all_files:
            return candidate

        # Try with src/main/java prefix (Maven layout)
        maven_candidate = f"src/main/java/{candidate}"
        if maven_candidate in all_files:
            return maven_candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format Java entry point for display.

        Formats:
        - main_method: "public static void main @line"
        - spring_app: "@SpringBootApplication @line"
        - servlet: "@WebServlet @line"
        - rest_controller: "@RestController @line"
        """
        if ep.type == "main_method":
            return f"  {ep.file}:public static void main @{ep.line}"
        elif ep.type == "spring_boot_app":
            return f"  {ep.file}:@SpringBootApplication @{ep.line}"
        elif ep.type == "servlet":
            return f"  {ep.file}:@WebServlet {ep.name} @{ep.line}"
        elif ep.type == "rest_controller":
            return f"  {ep.file}:@RestController {ep.name} @{ep.line}"
        elif ep.type == "controller":
            return f"  {ep.file}:@Controller {ep.name} @{ep.line}"
        else:
            return super().format_entry_point(ep)
