"""TypeScript/JavaScript language support - unified scanner and analyzer.

This module combines TypeScriptScanner and TypeScriptAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_typescript
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class TypeScriptLanguage(BaseLanguage):
    """Unified language handler for TypeScript/JavaScript files.

    Provides both structure scanning and semantic analysis:
    - scan(): Extract classes, interfaces, functions, methods with signatures and metadata
    - extract_imports(): Find import/require statements
    - find_entry_points(): Find exports, app instances
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Find function/method calls
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        # tree-sitter-typescript provides both typescript and tsx parsers
        # Use language_tsx for all TypeScript files as it's a superset that handles both
        self.parser.language = Language(tree_sitter_typescript.language_tsx())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]

    @classmethod
    def get_language_name(cls) -> str:
        return "TypeScript/JavaScript"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

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

    def should_analyze(self, file_path: str) -> bool:
        """Skip TypeScript/JavaScript files that should not be analyzed."""
        filename = Path(file_path).name.lower()

        # Skip minified files
        if filename.endswith(('.min.js', '.min.mjs', '.min.cjs')):
            return False

        # Skip TypeScript declaration files
        if filename.endswith('.d.ts'):
            return False

        # Skip webpack/rollup bundles
        if 'bundle' in filename or 'chunk' in filename:
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value TypeScript/JavaScript files for inventory listing.

        Low-value files (unless central):
        - index.ts/index.js that only re-export (small size)
        - Type declaration files (.d.ts) - already skipped by should_analyze
        - Config files (vite.config.ts, etc.) unless large
        - Test setup files (setupTests.ts, etc.)
        """
        filename = Path(file_path).name.lower()

        # Small index files are usually just re-exports
        if filename in ("index.ts", "index.js", "index.tsx", "index.jsx") and size < 200:
            return True

        # Test setup files
        if filename in ("setuptests.ts", "setuptests.js", "jest.setup.ts", "jest.setup.js") and size < 300:
            return True

        # Very small config files
        config_files = ("vite.config.ts", "vitest.config.ts", "jest.config.ts",
                       "tsconfig.json", "tsconfig.node.json")
        if filename in config_files and size < 500:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from TypeScriptScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan TypeScript/TSX source code and extract structure with metadata."""
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
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find interface definitions
        for match in re.finditer(r'^\s*(?:export\s+)?interface\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="interface",
                name=match.group(1) + " (fallback)",
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
                name=name + " (fallback)",
                start_line=line_num,
                end_line=line_num,
                signature=f"{generics}({params})"
            ))

        # Find arrow functions
        for match in re.finditer(r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="function",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from TypeScriptAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract import/require statements from TypeScript/JavaScript file.

        Patterns supported:
        - import x from 'module'
        - import { x, y } from 'module'
        - import * as x from 'module'
        - const x = require('module')
        - export { x } from 'module'
        - import('module') (dynamic import)
        """
        imports = []

        # Pattern 1: import ... from 'module'
        import_from_pattern = r'^\s*import\s+(?:(?:\{[^}]+\}|\*\s+as\s+\w+|\w+)(?:\s*,\s*\{[^}]+\})?)\s+from\s+[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(import_from_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Determine if relative import
            is_relative = module.startswith('./')
            import_type = "relative" if is_relative else "es6_import"

            # Resolve relative imports
            target_module = module
            if is_relative:
                resolved = self._resolve_relative_import(file_path, module)
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

        # Pattern 2: import 'module' (side-effect import)
        import_pattern = r'^\s*import\s+[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(import_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            is_relative = module.startswith('./')
            import_type = "relative" if is_relative else "es6_import"

            target_module = module
            if is_relative:
                resolved = self._resolve_relative_import(file_path, module)
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

        # Pattern 3: require('module')
        require_pattern = r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
        for match in re.finditer(require_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            is_relative = module.startswith('./')
            import_type = "relative" if is_relative else "require"

            target_module = module
            if is_relative:
                resolved = self._resolve_relative_import(file_path, module)
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

        # Pattern 4: export ... from 'module'
        export_from_pattern = r'^\s*export\s+(?:\{[^}]+\}|\*(?:\s+as\s+\w+)?)\s+from\s+[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(export_from_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            is_relative = module.startswith('./')
            import_type = "relative" if is_relative else "export_from"

            target_module = module
            if is_relative:
                resolved = self._resolve_relative_import(file_path, module)
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

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in TypeScript/JavaScript file.

        Entry points:
        - export default (main export)
        - Framework app instances (Express, Fastify, Next.js, etc.)
        - export { ... } with main exports
        """
        entry_points = []

        # Pattern 1: export default
        default_export_pattern = r'^\s*export\s+default\s+(\w+)'
        for match in re.finditer(default_export_pattern, content, re.MULTILINE):
            name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="export",
                    line=line_num,
                    name=name,
                )
            )

        # Pattern 2: Framework app instances
        # Express: const app = express()
        # Fastify: const app = fastify()
        # Next.js: export default function App()
        framework_patterns = [
            (r'const\s+(\w+)\s*=\s*express\s*\(', "Express"),
            (r'const\s+(\w+)\s*=\s*fastify\s*\(', "Fastify"),
            (r'const\s+(\w+)\s*=\s*new\s+Hono\s*\(', "Hono"),
            (r'export\s+default\s+function\s+(\w+)\s*\(', "React/Next.js"),
        ]

        for pattern, framework in framework_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                name = match.group(1)
                line_num = content[:match.start()].count('\n') + 1
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="app_instance",
                        line=line_num,
                        name=name,
                        framework=framework,
                    )
                )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract function/class/interface definitions by reusing scan() output.

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

        Override to include TypeScript interfaces.
        """
        definitions = []

        for node in structures:
            # Include interface type for TypeScript (in addition to class, function, method)
            if node.type in ("class", "function", "method", "interface"):
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
                # For both class and interface, set child_parent to node name
                child_parent = node.name if node.type in ("class", "interface") else parent
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
        for match in re.finditer(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", content, re.MULTILINE):
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
        for match in re.finditer(r"^\s*(?:export\s+)?interface\s+(\w+)", content, re.MULTILINE):
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

        # Functions
        for match in re.finditer(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(", content, re.MULTILINE):
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

        # Arrow functions
        for match in re.finditer(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(", content, re.MULTILINE):
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
        """Extract function/method calls using tree-sitter.

        Note: This still needs tree-sitter parsing because call sites are
        not captured in the structure scan (which only captures definitions).
        """
        try:
            source_bytes = content.encode("utf-8")
            tree = self.parser.parse(source_bytes)
            return self._extract_calls_tree_sitter(
                file_path, tree.root_node, source_bytes, definitions
            )
        except Exception:
            return self._extract_calls_regex(file_path, content, definitions)

    def _extract_calls_tree_sitter(
        self, file_path: str, root, source_bytes: bytes, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Extract calls using tree-sitter AST."""
        calls = []
        current_function = None

        def traverse(node, context_func=None):
            nonlocal current_function

            # Track function context
            if node.type in ("function_declaration", "method_definition", "arrow_function"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    current_function = source_bytes[
                        name_node.start_byte : name_node.end_byte
                    ].decode("utf-8")

                for child in node.children:
                    traverse(child, current_function)

                current_function = context_func
                return

            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node:
                    if func_node.type == "identifier":
                        callee_name = source_bytes[
                            func_node.start_byte : func_node.end_byte
                        ].decode("utf-8")
                        line = node.start_point[0] + 1

                        calls.append(
                            CallInfo(
                                caller_file=file_path,
                                caller_name=context_func,
                                callee_name=callee_name,
                                line=line,
                                is_cross_file=False,
                            )
                        )

                    elif func_node.type == "member_expression":
                        # obj.method()
                        prop_node = func_node.child_by_field_name("property")
                        if prop_node:
                            callee_name = source_bytes[
                                prop_node.start_byte : prop_node.end_byte
                            ].decode("utf-8")
                            line = node.start_point[0] + 1

                            calls.append(
                                CallInfo(
                                    caller_file=file_path,
                                    caller_name=context_func,
                                    callee_name=callee_name,
                                    line=line,
                                    is_cross_file=False,
                                )
                            )

            for child in node.children:
                traverse(child, context_func)

        traverse(root)

        local_defs = {d.name for d in definitions}
        for call in calls:
            if call.callee_name not in local_defs:
                call.is_cross_file = True

        return calls

    def _extract_calls_regex(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Fallback: Extract calls using regex."""
        calls = []

        for match in re.finditer(r"\b(\w+)\s*\(", content):
            callee_name = match.group(1)
            line = content[: match.start()].count("\n") + 1

            # Skip keywords
            if callee_name in [
                "if", "for", "while", "function", "class", "return", "console",
                "switch", "catch", "new", "typeof", "import", "export",
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
    # Classification (enhanced for TypeScript/JavaScript)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify TypeScript/JavaScript file into architectural cluster."""
        cluster = super().classify_file(file_path, content)

        if cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points
            if name in ["index.ts", "index.tsx", "main.ts", "app.ts", "app.tsx", "server.ts"]:
                return "entry_points"

            # Config
            if name in ["config.ts", "settings.ts", "env.ts"]:
                return "config"

            # Types
            if "/types/" in path_lower or name.endswith(".types.ts"):
                return "utilities"

            # Components (React/Vue)
            if "/components/" in path_lower:
                return "core_logic"

            # Routes/Controllers
            if "/routes/" in path_lower or "/controllers/" in path_lower:
                return "core_logic"

        return cluster

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
        """Resolve TypeScript/JavaScript import to file path.

        Handles:
        - Relative imports: ./foo -> foo.ts, foo.tsx, foo/index.ts
        - Path-resolved imports already contain slashes
        - Node module imports are skipped (no leading ./)
        """
        # Skip node_modules packages (non-relative imports)
        if not module.startswith(".") and "/" not in module:
            return None

        # Already resolved to path (contains /)
        if "/" in module:
            path = module

            # Try with various extensions
            extensions = [".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"]
            for ext in extensions:
                candidate = f"{path}{ext}"
                if candidate in all_files:
                    return candidate

            # Try as directory with index file
            for ext in extensions:
                candidate = f"{path}/index{ext}"
                if candidate in all_files:
                    return candidate

            return None

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format TypeScript/JavaScript entry point for display."""
        if ep.type == "export":
            return f"  {ep.file}:{ep.name}"
        elif ep.type == "app_instance":
            return f"  {ep.file}:{ep.framework} {ep.name} @{ep.line}"
        else:
            return super().format_entry_point(ep)
