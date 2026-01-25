"""Rust language support - unified scanner and analyzer.

This module combines RustScanner and RustAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_rust
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class RustLanguage(BaseLanguage):
    """Unified language handler for Rust files (.rs).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract structs, enums, traits, impl blocks, functions with metadata
    - extract_imports(): Find use statements
    - find_entry_points(): Find main functions, async entry points, tests
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Find function/method calls
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_rust.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".rs"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Rust"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip generated protobuf files."""
        if filename.endswith('.pb.rs'):
            return True
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Skip files that should not be analyzed.

        Skips:
        - Generated protobuf files (*.pb.rs)
        - Files in target/ directory (build artifacts)
        - build.rs in target/ (build script output)
        """
        path = Path(file_path)
        filename = path.name.lower()

        # Skip generated protobuf files
        if filename.endswith('.pb.rs'):
            return False

        # Skip files in target/ directory
        if 'target' in path.parts:
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value Rust files for inventory listing.

        Low-value files (unless central):
        - mod.rs files that are small (just re-exports)
        - build.rs files (build scripts)
        """
        filename = Path(file_path).name

        # Small mod.rs files are usually just re-exports
        if filename == "mod.rs" and size < 200:
            return True

        # Small build.rs files
        if filename == "build.rs" and size < 100:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from RustScanner)
    # ===========================================================================

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
                        name="invalid syntax",
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
                name=name + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum definitions
        for match in re.finditer(r'^\s*pub\s+enum\s+(\w+)|^\s*enum\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1) or match.group(2)
            structures.append(StructureNode(
                type="enum",
                name=name + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find trait definitions
        for match in re.finditer(r'^\s*pub\s+trait\s+(\w+)|^\s*trait\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1) or match.group(2)
            structures.append(StructureNode(
                type="trait",
                name=name + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function definitions
        for match in re.finditer(r'^\s*pub\s+(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?fn\s+(\w+)|^\s*(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?fn\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1) or match.group(2)
            structures.append(StructureNode(
                type="function",
                name=name + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from RustAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from Rust file.

        Rust import patterns:
        - use std::collections::HashMap;
        - use crate::module::Type;
        - use super::parent;
        - use self::current;
        - use foo::{bar, baz};  (multiple imports)
        - use foo::bar as baz;  (aliased imports)
        """
        imports = []

        # Pattern for use statements
        # Matches: use path::to::module;
        #          use path::{item1, item2};
        #          use path::item as alias;
        use_pattern = r'^\s*(?:pub\s+)?use\s+((?:std|crate|super|self|::)?[\w:]+(?:::\{[^}]+\})?(?:\s+as\s+\w+)?)\s*;'

        for match in re.finditer(use_pattern, content, re.MULTILINE):
            use_path = match.group(1).strip()
            line = content[:match.start()].count('\n') + 1

            # Handle grouped imports: use foo::{bar, baz}
            if '::{}' in use_path or '::{' in use_path:
                # Extract base path and items
                brace_match = re.match(r'([\w:]+)::\{([^}]+)\}', use_path)
                if brace_match:
                    base_path = brace_match.group(1)
                    items_str = brace_match.group(2)

                    # Parse individual items
                    imported_names = []
                    for item in items_str.split(','):
                        item = item.strip()
                        if ' as ' in item:
                            name, _ = item.split(' as ')
                            imported_names.append(name.strip())
                        else:
                            imported_names.append(item)

                    imports.append(ImportInfo(
                        source_file=file_path,
                        target_module=base_path,
                        import_type="use",
                        line=line,
                        imported_names=imported_names
                    ))
                    continue

            # Handle aliased imports: use foo::bar as baz
            if ' as ' in use_path:
                module_part, alias = use_path.split(' as ')
                module_part = module_part.strip()

                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=module_part,
                    import_type="use_as",
                    line=line,
                    imported_names=[alias.strip()]
                ))
                continue

            # Simple use statement
            import_type = "use"
            if use_path.startswith('super::'):
                import_type = "relative"
            elif use_path.startswith('self::'):
                import_type = "relative"
            elif use_path.startswith('crate::'):
                import_type = "crate"
            elif use_path.startswith('::'):
                import_type = "absolute"
            elif use_path.startswith('std::'):
                import_type = "std"

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=use_path,
                import_type=import_type,
                line=line,
                imported_names=[]
            ))

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in Rust file.

        Entry points:
        - fn main() - standard entry point
        - #[tokio::main] - async Tokio entry point
        - #[async_std::main] - async async-std entry point
        - #[actix_web::main] - Actix Web entry point
        - #[test] functions (test entry points)
        - #[bench] functions (benchmark entry points)
        """
        entry_points = []

        # Pattern 1: Standard fn main()
        main_pattern = r'^\s*(?:pub\s+)?fn\s+main\s*\('
        for match in re.finditer(main_pattern, content, re.MULTILINE):
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="main_function",
                name="main",
                line=line
            ))

        # Pattern 2: Async framework entry points
        # Look for #[framework::main] followed by fn main() or async fn main()
        async_main_pattern = r'#\[(tokio|async_std|actix_web)::(main|test)\]\s*(?:async\s+)?fn\s+(\w+)'
        for match in re.finditer(async_main_pattern, content, re.MULTILINE):
            framework = match.group(1)
            decorator_type = match.group(2)
            func_name = match.group(3)
            line = content[:match.start()].count('\n') + 1

            entry_points.append(EntryPointInfo(
                file=file_path,
                type="async_main" if decorator_type == "main" else "async_test",
                name=func_name,
                line=line,
                framework=framework
            ))

        # Pattern 3: Test functions
        # #[test] or #[cfg(test)]
        test_pattern = r'#\[(?:cfg\(test\)|test)\]\s*(?:async\s+)?fn\s+(\w+)'
        for match in re.finditer(test_pattern, content, re.MULTILINE):
            func_name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            entry_points.append(EntryPointInfo(
                file=file_path,
                type="test",
                name=func_name,
                line=line
            ))

        # Pattern 4: Benchmark functions
        bench_pattern = r'#\[bench\]\s*fn\s+(\w+)'
        for match in re.finditer(bench_pattern, content):
            func_name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            entry_points.append(EntryPointInfo(
                file=file_path,
                type="benchmark",
                name=func_name,
                line=line
            ))

        # Pattern 5: lib.rs public API exports (if file is lib.rs)
        if file_path.endswith('lib.rs'):
            # Look for pub mod statements
            pub_mod_pattern = r'^\s*pub\s+mod\s+(\w+)\s*;'
            for match in re.finditer(pub_mod_pattern, content, re.MULTILINE):
                mod_name = match.group(1)
                line = content[:match.start()].count('\n') + 1

                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="export",
                    name=f"mod {mod_name}",
                    line=line
                ))

            # Look for pub use re-exports
            pub_use_pattern = r'^\s*pub\s+use\s+([\w:]+)'
            for match in re.finditer(pub_use_pattern, content, re.MULTILINE):
                use_path = match.group(1)
                line = content[:match.start()].count('\n') + 1

                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="export",
                    name=f"pub use {use_path}",
                    line=line
                ))

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract function/struct/enum definitions by reusing scan() output.

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

        Override to include Rust-specific types: struct, enum, trait, impl.
        """
        definitions = []

        # Rust-specific types to include
        rust_types = ("struct", "enum", "trait", "impl", "function", "method")

        for node in structures:
            if node.type in rust_types:
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

            # Recurse into children (impl blocks and traits have methods)
            if node.children:
                # For impl and trait blocks, set them as parent
                child_parent = node.name if node.type in ("impl", "trait", "struct") else parent
                definitions.extend(
                    self._structures_to_definitions(file_path, node.children, child_parent)
                )

        return definitions

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        # Structs
        for match in re.finditer(r"^\s*(?:pub\s+)?struct\s+(\w+)", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="struct",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        # Enums
        for match in re.finditer(r"^\s*(?:pub\s+)?enum\s+(\w+)", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="enum",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        # Functions
        for match in re.finditer(r"^\s*(?:pub\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*\(", content, re.MULTILINE):
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

            # Track current function context
            if node.type == "function_item":
                name_node = node.child_by_field_name("name")
                if name_node:
                    current_function = source_bytes[
                        name_node.start_byte : name_node.end_byte
                    ].decode("utf-8")

                for child in node.children:
                    traverse(child, current_function)

                current_function = context_func
                return

            # Function calls
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node:
                    # Simple function call: foo()
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

                    # Method call: foo.bar() or Foo::bar()
                    elif func_node.type == "field_expression":
                        field_node = func_node.child_by_field_name("field")
                        if field_node:
                            callee_name = source_bytes[
                                field_node.start_byte : field_node.end_byte
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

                    # Scoped call: Foo::bar()
                    elif func_node.type == "scoped_identifier":
                        name_node = func_node.child_by_field_name("name")
                        if name_node:
                            callee_name = source_bytes[
                                name_node.start_byte : name_node.end_byte
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

        # Mark cross-file calls
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

        # Simple function call pattern
        for match in re.finditer(r"\b(\w+)\s*\(", content):
            callee_name = match.group(1)
            line = content[: match.start()].count("\n") + 1

            # Skip keywords
            if callee_name in [
                "if", "for", "while", "match", "fn", "struct", "enum",
                "impl", "trait", "use", "pub", "let", "mut", "return",
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

        # Mark cross-file calls
        local_defs = {d.name for d in definitions}
        for call in calls:
            if call.callee_name not in local_defs:
                call.is_cross_file = True

        return calls

    # ===========================================================================
    # Classification (enhanced for Rust)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify Rust file into architectural cluster.

        Rust-specific patterns:
        - main.rs -> entry_points
        - lib.rs -> entry_points
        - tests/ directory -> tests
        - benches/ directory -> tests (benchmarks)
        - mod.rs -> infrastructure (module organization)
        """
        path = Path(file_path)
        filename = path.name

        # Check for standard Rust entry points
        if filename in ('main.rs', 'lib.rs'):
            return "entry_points"

        # Check directory structure
        if 'tests' in path.parts or filename.startswith('test_'):
            return "tests"

        if 'benches' in path.parts or filename.startswith('bench_'):
            return "tests"

        if filename == 'mod.rs':
            return "infrastructure"

        # Check content patterns
        if '#[test]' in content or '#[cfg(test)]' in content:
            return "tests"

        if '#[bench]' in content:
            return "tests"

        if 'fn main(' in content:
            return "entry_points"

        # Fall back to base implementation
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
        """Resolve Rust use path to file path.

        Rust use patterns:
        - crate::module::item -> src/module.rs or src/module/mod.rs
        - super::module -> parent directory
        - self::module -> current module

        External crates are skipped.
        """
        # Skip standard library and external crates
        if not module.startswith(("crate::", "super::", "self::")):
            return None

        # crate:: refers to current crate root (usually src/)
        if module.startswith("crate::"):
            path_parts = module.replace("crate::", "").split("::")
            # Try src/module.rs
            candidate = "src/" + "/".join(path_parts[:-1]) + ".rs" if len(path_parts) > 1 else f"src/{path_parts[0]}.rs"
            if candidate in all_files:
                return candidate
            # Try src/module/mod.rs
            candidate_mod = "src/" + "/".join(path_parts) + "/mod.rs"
            if candidate_mod in all_files:
                return candidate_mod

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format Rust entry point for display.

        Formats:
        - main_function: "fn main() @line"
        - async_main: "async fn main() @line"
        - bin_target: "binary target @line"
        """
        if ep.type == "main_function":
            return f"  {ep.file}:fn main() @{ep.line}"
        elif ep.type == "async_main":
            return f"  {ep.file}:async fn main() @{ep.line}"
        elif ep.type == "bin_target":
            return f"  {ep.file}:binary target @{ep.line}"
        else:
            return super().format_entry_point(ep)
