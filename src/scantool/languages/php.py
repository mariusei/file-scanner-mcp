"""PHP language support - unified scanner and analyzer.

This module combines PHPScanner and PHPAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_php
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class PHPLanguage(BaseLanguage):
    """Unified language handler for PHP files (.php, .phtml, etc.).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract classes, interfaces, traits, enums, functions, methods
    - extract_imports(): Find use statements, require/include
    - find_entry_points(): Find index.php, Laravel routes, controllers
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Not implemented (uses base class default)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_php.language_php())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".php", ".phtml", ".php3", ".php4", ".php5", ".phps"]

    @classmethod
    def get_language_name(cls) -> str:
        return "PHP"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip compiled/cached PHP files."""
        # .phps is for syntax highlighting, not executable
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Skip PHP files that should not be analyzed.

        - Skip Blade cached files in Laravel storage/framework/views
        - Skip compiled PHP files
        """
        path_lower = file_path.lower()

        # Skip Laravel Blade cache files
        if 'storage/framework/views' in path_lower:
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value PHP files for inventory listing.

        Low-value files (unless central):
        - Small config files
        - Blade cache files
        """
        filename = Path(file_path).name

        # Very small files are likely boilerplate
        if size > 0 and size < 50:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from PHPScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan PHP source code and extract structure with metadata."""
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

            # Namespace declaration
            if node.type == "namespace_definition":
                self._handle_namespace(node, parent_structures, source_code)

            # Use statements (imports)
            elif node.type == "namespace_use_declaration":
                self._handle_use(node, parent_structures)

            # Classes
            elif node.type == "class_declaration":
                class_node = self._extract_class(node, source_code, root)
                parent_structures.append(class_node)

                # Traverse children for methods and properties
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

            # Traits
            elif node.type == "trait_declaration":
                trait_node = self._extract_trait(node, source_code)
                parent_structures.append(trait_node)

                # Traverse children for methods
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, trait_node.children)

            # Enums (PHP 8.1+)
            elif node.type == "enum_declaration":
                enum_node = self._extract_enum(node, source_code)
                parent_structures.append(enum_node)

            # Methods (in classes/traits)
            elif node.type == "method_declaration":
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Standalone functions
            elif node.type == "function_definition":
                # Only capture top-level functions, not methods
                if not self._is_in_class_or_trait(root, node):
                    function_node = self._extract_function(node, source_code)
                    parent_structures.append(function_node)

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

        # Get attributes (PHP 8+)
        decorators = self._extract_attributes(node, source_code)

        # Get base class and interfaces
        signature_parts = []

        # Get base class (extends)
        base_clause = node.child_by_field_name("base_clause")
        if base_clause:
            base_text = self._get_node_text(base_clause, source_code).strip()
            signature_parts.append(base_text)

        # Get interfaces (implements)
        interface_clause = node.child_by_field_name("interface_clause")
        if interface_clause:
            interface_text = self._get_node_text(interface_clause, source_code).strip()
            signature_parts.append(interface_text)

        signature = " ".join(signature_parts) if signature_parts else None

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

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

        # Get attributes (PHP 8+)
        decorators = self._extract_attributes(node, source_code)

        # Get extends clause
        base_clause = node.child_by_field_name("base_clause")
        signature = None
        if base_clause:
            signature = self._get_node_text(base_clause, source_code).strip()

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

        return StructureNode(
            type="interface",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            children=[]
        )

    def _extract_trait(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract trait declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get attributes (PHP 8+)
        decorators = self._extract_attributes(node, source_code)

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

        return StructureNode(
            type="trait",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            decorators=decorators,
            docstring=docstring,
            children=[]
        )

    def _extract_enum(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract enum declaration (PHP 8.1+)."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get type (backed enum)
        signature_parts = []
        for child in node.children:
            if child.type == "primitive_type":
                type_text = self._get_node_text(child, source_code)
                signature_parts.append(f": {type_text}")

        # Get interfaces (implements)
        interface_clause = node.child_by_field_name("interface_clause")
        if interface_clause:
            interface_text = self._get_node_text(interface_clause, source_code).strip()
            signature_parts.append(interface_text)

        signature = " ".join(signature_parts) if signature_parts else None

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

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

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

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

    def _extract_function(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract standalone function with signature and metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get signature
        signature = self._extract_function_signature(node, source_code)

        # Get PHPDoc comment
        docstring = self._extract_phpdoc(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="function",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            complexity=complexity,
            children=[]
        )

    def _extract_method_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract method signature with parameters and return type."""
        parts = []

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Get return type
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_text = self._get_node_text(return_type_node, source_code).strip()
            parts.append(f" {return_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_function_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature with parameters and return type."""
        parts = []

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Get return type
        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_text = self._get_node_text(return_type_node, source_code).strip()
            parts.append(f" {return_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers like public, private, protected, static, final, abstract."""
        modifiers = []

        for child in node.children:
            if child.type in ("visibility_modifier", "final_modifier", "abstract_modifier", "static_modifier"):
                modifier_text = self._get_node_text(child, source_code).strip()
                modifiers.append(modifier_text)

        return modifiers

    def _extract_attributes(self, node: Node, source_code: bytes) -> list[str]:
        """Extract PHP 8 attributes from a class/method/function."""
        attributes = []

        # In PHP, attributes are children of the node, appearing before the keyword
        for child in node.children:
            if child.type == "attribute_list":
                attr_text = self._get_node_text(child, source_code).strip()
                attributes.append(attr_text)

        return attributes

    def _extract_phpdoc(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract first line of PHPDoc comment."""
        prev = node.prev_sibling

        # PHPDoc comments are typically previous siblings
        while prev:
            if prev.type == "comment":
                comment_text = self._get_node_text(prev, source_code).strip()
                # Check if it's a PHPDoc comment (/** ... */)
                if comment_text.startswith("/**"):
                    # Extract first meaningful line
                    lines = comment_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        # Remove comment markers
                        line = line.replace("/**", "").replace("*/", "").replace("*", "").strip()
                        if line and not line.startswith("@"):  # Skip PHPDoc tags
                            return line
                return None
            prev = prev.prev_sibling

        return None

    def _handle_namespace(self, node: Node, parent_structures: list, source_code: bytes):
        """Handle namespace declaration."""
        namespace_name_node = node.child_by_field_name("name")

        if namespace_name_node:
            namespace_name = self._get_node_text(namespace_name_node, source_code)
            namespace_node = StructureNode(
                type="namespace",
                name=namespace_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(namespace_node)

    def _handle_use(self, node: Node, parent_structures: list):
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

    def _is_in_class_or_trait(self, root: Node, target: Node) -> bool:
        """Check if a node is inside a class or trait."""
        ancestors = self._get_ancestors(root, target)
        return any(ancestor.type in ("class_declaration", "trait_declaration") for ancestor in ancestors)

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

        # Find namespace declaration
        namespace_match = re.search(r'^\s*namespace\s+([\w\\]+)\s*;', text, re.MULTILINE)
        if namespace_match:
            line_num = text[:namespace_match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="namespace",
                name=namespace_match.group(1),
                start_line=line_num,
                end_line=line_num
            ))

        # Find class definitions
        for match in re.finditer(r'^\s*(?:abstract\s+)?(?:final\s+)?class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find interface definitions
        for match in re.finditer(r'^\s*interface\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="interface",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find trait definitions
        for match in re.finditer(r'^\s*trait\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="trait",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum definitions
        for match in re.finditer(r'^\s*enum\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="enum",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find method definitions
        for match in re.finditer(r'^\s*(?:public|private|protected)\s+(?:static\s+)?function\s+(\w+)\s*\(', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find standalone function definitions
        for match in re.finditer(r'^\s*function\s+(\w+)\s*\(', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="function",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from PHPAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from PHP file.

        Patterns supported:
        - use Foo\\Bar\\Baz;
        - use Foo\\Bar\\Baz as Alias;
        - use Foo\\Bar\\{ClassA, ClassB};
        - require 'path/to/file.php';
        - require_once 'path/to/file.php';
        - include 'path/to/file.php';
        - include_once 'path/to/file.php';
        """
        imports = []

        # Pattern 1: use statements (namespace imports)
        # use Foo\Bar\Baz;
        # use Foo\Bar\Baz as Alias;
        use_pattern = r'^\s*use\s+([\w\\]+)(?:\s+as\s+\w+)?\s*;'
        for match in re.finditer(use_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type="use",
                )
            )

        # Pattern 2: grouped use statements
        # use Foo\Bar\{ClassA, ClassB, ClassC};
        grouped_use_pattern = r'^\s*use\s+([\w\\]+)\s*\{([^}]+)\}\s*;'
        for match in re.finditer(grouped_use_pattern, content, re.MULTILINE):
            base_namespace = match.group(1).rstrip('\\')  # Remove trailing backslash
            grouped_items_str = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            # Parse grouped items
            items = [item.strip() for item in grouped_items_str.split(',') if item.strip()]

            for item in items:
                # Remove 'as Alias' if present
                if ' as ' in item:
                    item = item.split(' as ')[0].strip()

                # Construct full namespace
                full_namespace = f"{base_namespace}\\{item}"

                imports.append(
                    ImportInfo(
                        source_file=file_path,
                        target_module=full_namespace,
                        line=line_num,
                        import_type="use_grouped",
                    )
                )

        # Pattern 3: require/include statements
        # require 'path/to/file.php';
        # require_once 'path/to/file.php';
        # include 'path/to/file.php';
        # include_once 'path/to/file.php';
        require_pattern = r'(require|require_once|include|include_once)\s*[\(\s]+[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(require_pattern, content, re.MULTILINE):
            keyword = match.group(1)
            file_path_str = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            # Determine if relative import
            is_relative = file_path_str.startswith(('./', '../'))
            import_type = f"{keyword}_relative" if is_relative else keyword

            # Resolve relative paths (for PHP file includes, not Python dot imports)
            target_module = file_path_str
            if is_relative:
                resolved = self._resolve_php_relative_path(file_path, file_path_str)
                if resolved:
                    target_module = resolved

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=target_module,
                    line=line_num,
                    import_type=import_type,
                )
            )

        # Pattern 4: use function statements
        # use function App\Utils\validateEmail;
        use_function_pattern = r'^\s*use\s+function\s+([\w\\]+)\s*;'
        for match in re.finditer(use_function_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type="use_function",
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in PHP file.

        Entry points:
        - index.php files
        - Laravel Route::get/post/etc definitions
        - Symfony controller classes (class name ends with Controller)
        - public function __invoke() (single-action controllers)
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        # Pattern 1: index.php files
        if filename == "index.php":
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="entry_file",
                    name="index.php",
                    line=1,
                )
            )

        # Pattern 2: Laravel routes
        # Route::get('/path', ...);
        # Route::post('/path', ...);
        # Route::put('/path', ...);
        # Route::delete('/path', ...);
        # Route::patch('/path', ...);
        # Route::any('/path', ...);
        route_pattern = r'Route::(get|post|put|delete|patch|any|resource|group)\s*\(\s*[\'"]([^\'"]*)[\'"]'
        for match in re.finditer(route_pattern, content):
            method = match.group(1)
            route_path = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="route",
                    name=f"{method.upper()} {route_path}",
                    line=line_num,
                    framework="Laravel",
                )
            )

        # Pattern 3: Symfony/Laravel controllers
        # class UserController extends Controller
        # class SomethingController
        controller_pattern = r'^\s*(?:final\s+)?class\s+(\w*Controller)\s*(?:extends|implements|\{)'
        for match in re.finditer(controller_pattern, content, re.MULTILINE):
            controller_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="controller",
                    name=controller_name,
                    line=line_num,
                )
            )

        # Pattern 4: Single-action controllers (__invoke)
        invoke_pattern = r'^\s*public\s+function\s+__invoke\s*\('
        for match in re.finditer(invoke_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="invokable",
                    name="__invoke",
                    line=line_num,
                )
            )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract function/class definitions by reusing scan() output.

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

    def _structures_to_definitions(
        self, file_path: str, structures: list[StructureNode], parent: str = None
    ) -> list[DefinitionInfo]:
        """Convert StructureNode list to DefinitionInfo list.

        PHP-specific override that includes interface, trait, and enum types.
        """
        definitions = []

        # PHP structure types that should become definitions
        php_types = ("class", "function", "method", "interface", "trait", "enum")

        for node in structures:
            if node.type in php_types:
                definitions.append(
                    DefinitionInfo(
                        file=file_path,
                        type=node.type,
                        name=node.name,
                        line=node.start_line,
                        signature=node.signature,
                        parent=parent,
                    )
                )

            # Recurse into children
            if node.children:
                # Set parent for child methods in class-like structures
                child_parent = node.name if node.type in ("class", "interface", "trait", "enum") else parent
                definitions.extend(
                    self._structures_to_definitions(file_path, node.children, child_parent)
                )

        return definitions

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        # Classes
        for match in re.finditer(r"^\s*(?:abstract\s+)?(?:final\s+)?class\s+(\w+)", content, re.MULTILINE):
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

        # Interfaces
        for match in re.finditer(r"^\s*interface\s+(\w+)", content, re.MULTILINE):
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

        # Traits
        for match in re.finditer(r"^\s*trait\s+(\w+)", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="trait",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        # Functions
        for match in re.finditer(r"^\s*function\s+(\w+)\s*\(", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="function",
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
        """Extract function/method calls using tree-sitter."""
        try:
            source_bytes = content.encode("utf-8")
            tree = self.parser.parse(source_bytes)
            return self._extract_calls_tree_sitter(
                file_path, tree.root_node, source_bytes, definitions
            )
        except Exception:
            return self._extract_calls_regex(file_path, content, definitions)

    def _extract_calls_tree_sitter(
        self,
        file_path: str,
        root: Node,
        source_bytes: bytes,
        definitions: list[DefinitionInfo],
    ) -> list[CallInfo]:
        """Extract calls using tree-sitter AST with caller context tracking."""
        calls = []

        def traverse(node: Node, current_func: Optional[str] = None):
            # Track function/method context
            if node.type in ("function_definition", "method_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    func_name = self._get_node_text(name_node, source_bytes)
                    # Traverse children with this function as context
                    for child in node.children:
                        traverse(child, func_name)
                    return

            # Extract function calls
            if node.type == "function_call_expression":
                func_node = node.child_by_field_name("function")
                callee_name = None

                if func_node:
                    # Simple function call: foo()
                    if func_node.type == "name":
                        callee_name = self._get_node_text(func_node, source_bytes)
                    # Qualified call: \Namespace\func() or Namespace\func()
                    elif func_node.type == "qualified_name":
                        # Get the last part of the qualified name
                        for child in reversed(func_node.children):
                            if child.type == "name":
                                callee_name = self._get_node_text(child, source_bytes)
                                break

                if callee_name and current_func:
                    calls.append(
                        CallInfo(
                            caller_file=file_path,
                            caller_name=current_func,
                            callee_name=callee_name,
                            line=node.start_point[0] + 1,
                            is_cross_file=False,
                        )
                    )

            # Extract method calls: $obj->method() or Class::method()
            if node.type == "member_call_expression":
                name_node = node.child_by_field_name("name")
                if name_node and current_func:
                    callee_name = self._get_node_text(name_node, source_bytes)
                    calls.append(
                        CallInfo(
                            caller_file=file_path,
                            caller_name=current_func,
                            callee_name=callee_name,
                            line=node.start_point[0] + 1,
                            is_cross_file=False,
                        )
                    )

            # Extract static method calls: ClassName::method()
            if node.type == "scoped_call_expression":
                name_node = node.child_by_field_name("name")
                if name_node and current_func:
                    callee_name = self._get_node_text(name_node, source_bytes)
                    calls.append(
                        CallInfo(
                            caller_file=file_path,
                            caller_name=current_func,
                            callee_name=callee_name,
                            line=node.start_point[0] + 1,
                            is_cross_file=False,
                        )
                    )

            # Recurse into children
            for child in node.children:
                traverse(child, current_func)

        traverse(root)

        # Mark cross-file calls
        local_defs = {d.name for d in definitions}
        for call in calls:
            if call.callee_name not in local_defs:
                call.is_cross_file = True

        return calls

    def _extract_calls_regex(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Fallback: Extract calls using regex (without caller context)."""
        calls = []

        for match in re.finditer(r"\b(\w+)\s*\(", content):
            callee_name = match.group(1)
            line = content[: match.start()].count("\n") + 1

            # Skip keywords
            if callee_name in [
                "if", "else", "elseif", "while", "for", "foreach", "switch",
                "case", "function", "class", "interface", "trait", "enum",
                "return", "echo", "print", "array", "list", "isset", "unset",
                "empty", "eval", "exit", "die", "include", "require",
                "include_once", "require_once", "new", "clone", "throw",
            ]:
                continue

            calls.append(
                CallInfo(
                    caller_file=file_path,
                    caller_name=None,
                    callee_name=callee_name,
                    line=line,
                    is_cross_file=False,
                )
            )

        local_defs = {d.name for d in definitions}
        for call in calls:
            if call.callee_name not in local_defs:
                call.is_cross_file = True

        return calls

    # ===========================================================================
    # Classification (enhanced for PHP)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify PHP file into architectural cluster.

        Uses base class heuristics plus PHP-specific patterns.
        """
        name = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # PHP-specific patterns (check these FIRST before base class)
        # Order matters! More specific patterns should come first

        # Views/Templates (check before index.php to avoid false positives)
        if "views/" in path_lower or "templates/" in path_lower or name.endswith(".blade.php"):
            return "presentation"

        # Config
        if "config/" in path_lower or name.startswith("config."):
            return "config"

        # Tests (check before other patterns)
        if "tests/" in path_lower or name.endswith("test.php"):
            return "tests"

        # Migrations/Seeders
        if "migrations/" in path_lower or "seeders/" in path_lower:
            return "database"

        # Entry points
        if name == "index.php":
            return "entry_points"

        # Controllers
        if "controllers/" in path_lower or name.endswith("controller.php"):
            return "entry_points"

        # Routes
        if "routes/" in path_lower or name in ["web.php", "api.php", "console.php"]:
            return "entry_points"

        # Models
        if "models/" in path_lower or "entities/" in path_lower:
            return "core_logic"

        # Services
        if "services/" in path_lower or name.endswith("service.php"):
            return "core_logic"

        # Middleware
        if "middleware/" in path_lower:
            return "core_logic"

        # Use base class classification for remaining patterns (utilities, etc.)
        return super().classify_file(file_path, content)

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
        """Resolve PHP use statement to file path.

        PHP uses namespace imports like:
        - App\\Models\\User -> app/Models/User.php (Laravel)
        - Foo\\Bar\\Baz -> Foo/Bar/Baz.php

        Vendor namespaces are skipped.
        """
        # Skip vendor packages (common third-party prefixes)
        vendor_prefixes = (
            "Illuminate\\", "Symfony\\", "Doctrine\\", "Monolog\\",
            "PHPUnit\\", "Carbon\\", "GuzzleHttp\\", "Psr\\",
        )
        if any(module.startswith(p) for p in vendor_prefixes):
            return None

        # Convert namespace to file path
        # App\Models\User -> app/Models/User.php (lowercase first segment for Laravel)
        parts = module.split("\\")
        candidate = "/".join(parts) + ".php"
        if candidate in all_files:
            return candidate

        # Laravel style: App -> app
        if len(parts) > 0 and parts[0] == "App":
            parts[0] = "app"
            candidate = "/".join(parts) + ".php"
            if candidate in all_files:
                return candidate

        return None

    def _resolve_php_relative_path(
        self, current_file: str, relative_path: str
    ) -> Optional[str]:
        """Resolve PHP relative file path (e.g., './config.php', '../utils.php').

        Unlike Python's dot imports, PHP uses Unix-style relative paths.

        Args:
            current_file: Path of file doing the include/require
            relative_path: Relative path string (e.g., './config.php')

        Returns:
            Resolved absolute path or None
        """
        import os.path as osp

        # Get directory of current file
        current_dir = "/".join(current_file.split("/")[:-1])

        # Normalize the path
        # ./config.php -> config.php
        # ../utils.php -> (parent)/utils.php
        if relative_path.startswith('./'):
            relative_path = relative_path[2:]
        elif relative_path.startswith('../'):
            # Go up directories
            parts = current_dir.split('/') if current_dir else []
            path_parts = relative_path.split('/')
            for part in path_parts:
                if part == '..':
                    if parts:
                        parts.pop()
                else:
                    parts.append(part)
            return '/'.join(parts) if parts else None

        # Combine current directory with relative path
        if current_dir:
            return f"{current_dir}/{relative_path}"
        return relative_path

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format PHP entry point for display.

        Formats:
        - index: "index.php"
        - artisan_command: "artisan ClassName @line"
        - controller: "Controller ClassName @line"
        - route_file: "routes @line"
        """
        if ep.type == "index":
            return f"  {ep.file}:index.php"
        elif ep.type == "artisan_command":
            return f"  {ep.file}:artisan {ep.name} @{ep.line}"
        elif ep.type == "controller":
            return f"  {ep.file}:Controller {ep.name} @{ep.line}"
        elif ep.type == "route_file":
            return f"  {ep.file}:routes @{ep.line}"
        else:
            return super().format_entry_point(ep)
