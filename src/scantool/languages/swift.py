"""Swift language support - unified scanner and analyzer.

This module combines SwiftScanner and SwiftAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_swift
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class SwiftLanguage(BaseLanguage):
    """Unified language handler for Swift files (.swift).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract classes, structs, enums, protocols, functions with metadata
    - extract_imports(): Find import statements and type references
    - find_entry_points(): Find @main, main.swift, AppDelegate, SwiftUI App
    - extract_definitions(): Convert scan() output to DefinitionInfo
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_swift.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".swift"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Swift"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip generated Swift files."""
        filename_lower = filename.lower()
        if ".generated.swift" in filename_lower or "generated" in filename_lower:
            return True
        return False

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip Swift files that should not be analyzed.

        Swift-specific skip patterns:
        - Skip generated files (*.generated.swift)
        - Skip Pods directory (CocoaPods)
        - Skip Carthage checkouts
        - Skip build directories
        """
        filename = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # Skip generated files
        if ".generated.swift" in filename or "generated" in filename:
            return False

        # Skip Pods directory (CocoaPods) - handle both /pods/ and pods/ at start
        if "/pods/" in path_lower or path_lower.startswith("pods/"):
            return False

        # Skip Carthage checkouts - handle both with and without leading /
        if "/carthage/checkouts/" in path_lower or path_lower.startswith("carthage/checkouts/"):
            return False

        # Skip build directories - handle both with and without leading /
        if "/.build/" in path_lower or path_lower.startswith(".build/"):
            return False
        if "/deriveddata/" in path_lower or path_lower.startswith("deriveddata/"):
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value Swift files for inventory listing.

        Low-value files (unless central):
        - Empty extension files
        - Generated files
        """
        filename = Path(file_path).name.lower()

        # Small extension-only files
        if "+extension.swift" in filename and size < 200:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from SwiftScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Swift source code and extract structure with metadata."""
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

            # class_declaration is used for class, struct, enum, extension, actor
            if node.type == "class_declaration":
                type_node = self._extract_type_declaration(node, source_code)
                if type_node:
                    parent_structures.append(type_node)

            # Protocol declaration
            elif node.type == "protocol_declaration":
                protocol_node = self._extract_protocol(node, source_code)
                if protocol_node:
                    parent_structures.append(protocol_node)

            # Function declaration (standalone)
            elif node.type == "function_declaration":
                func_node = self._extract_function(node, source_code)
                if func_node:
                    parent_structures.append(func_node)

            # Typealias declaration
            elif node.type == "typealias_declaration":
                typealias_node = self._extract_typealias(node, source_code)
                if typealias_node:
                    parent_structures.append(typealias_node)

            # Import declarations
            elif node.type == "import_declaration":
                self._handle_import(node, parent_structures)

            else:
                # Keep traversing for other node types
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_type_declaration(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract type declaration (class, struct, enum, extension, actor).

        In tree-sitter-swift, class_declaration is used for all these types.
        The actual type is determined by the keyword child.
        """
        # Determine the actual type by looking at keywords
        type_kind = "class"  # default
        for child in node.children:
            if child.type == "struct":
                type_kind = "struct"
                break
            elif child.type == "enum":
                type_kind = "enum"
                break
            elif child.type == "class":
                type_kind = "class"
                break
            elif child.type == "extension":
                type_kind = "extension"
                break
            elif child.type == "actor":
                type_kind = "actor"
                break

        # Get the type name
        name = None
        for child in node.children:
            if child.type == "type_identifier":
                name = self._get_node_text(child, source_code)
                break
            elif child.type == "user_type" and type_kind == "extension":
                # Extensions use user_type for the extended type
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        inheritance = self._extract_inheritance(node, source_code)

        signature = None
        if inheritance:
            signature = f": {', '.join(inheritance)}"

        complexity = self._calculate_complexity(node)
        children = self._extract_type_members(node, source_code, type_kind)

        return StructureNode(
            type=type_kind,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            complexity=complexity,
            children=children
        )

    def _extract_protocol(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract protocol declaration."""
        name = None
        for child in node.children:
            if child.type == "type_identifier":
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        inheritance = self._extract_inheritance(node, source_code)

        signature = None
        if inheritance:
            signature = f": {', '.join(inheritance)}"

        complexity = self._calculate_complexity(node)
        children = self._extract_protocol_members(node, source_code)

        return StructureNode(
            type="protocol",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            complexity=complexity,
            children=children
        )

    def _extract_function(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract function declaration."""
        name = None
        for child in node.children:
            if child.type == "simple_identifier":
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        signature = self._extract_function_signature(node, source_code)
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="function",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            complexity=complexity,
            children=[]
        )

    def _extract_typealias(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract typealias declaration."""
        name = None
        alias_type = None

        for child in node.children:
            if child.type == "type_identifier" and name is None:
                name = self._get_node_text(child, source_code)
            elif child.type in ("user_type", "function_type", "tuple_type", "optional_type"):
                alias_type = self._get_node_text(child, source_code)

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        docstring = self._extract_docstring(node, source_code)

        signature = f"= {alias_type}" if alias_type else None

        return StructureNode(
            type="typealias",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_type_members(self, node: Node, source_code: bytes, parent_type: str) -> list[StructureNode]:
        """Extract members from a type declaration."""
        members = []

        # Find the body node
        body = None
        for child in node.children:
            if child.type in ("class_body", "enum_class_body"):
                body = child
                break

        if not body:
            return members

        for child in body.children:
            if child.type == "function_declaration":
                func = self._extract_function(child, source_code)
                if func:
                    func.type = "method"
                    members.append(func)

            elif child.type == "property_declaration":
                prop = self._extract_property(child, source_code)
                if prop:
                    members.append(prop)

            elif child.type == "subscript_declaration":
                subscript = self._extract_subscript(child, source_code)
                if subscript:
                    members.append(subscript)

            elif child.type == "init_declaration":
                init = self._extract_initializer(child, source_code)
                if init:
                    members.append(init)

            elif child.type == "deinit_declaration":
                deinit_node = StructureNode(
                    type="deinitializer",
                    name="deinit",
                    start_line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    docstring=self._extract_docstring(child, source_code),
                    children=[]
                )
                members.append(deinit_node)

            elif child.type == "enum_entry":
                case_node = self._extract_enum_case(child, source_code)
                if case_node:
                    members.append(case_node)

            # Nested types
            elif child.type == "class_declaration":
                nested = self._extract_type_declaration(child, source_code)
                if nested:
                    members.append(nested)

            elif child.type == "protocol_declaration":
                nested = self._extract_protocol(child, source_code)
                if nested:
                    members.append(nested)

        return members

    def _extract_protocol_members(self, node: Node, source_code: bytes) -> list[StructureNode]:
        """Extract members from a protocol declaration."""
        members = []

        # Find protocol body
        body = None
        for child in node.children:
            if child.type == "protocol_body":
                body = child
                break

        if not body:
            return members

        for child in body.children:
            if child.type == "protocol_function_declaration":
                func = self._extract_protocol_function(child, source_code)
                if func:
                    members.append(func)

            elif child.type == "protocol_property_declaration":
                prop = self._extract_property(child, source_code)
                if prop:
                    members.append(prop)

        return members

    def _extract_protocol_function(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract protocol function declaration."""
        name = None
        for child in node.children:
            if child.type == "simple_identifier":
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        signature = self._extract_function_signature(node, source_code)

        return StructureNode(
            type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_property(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract property declaration."""
        name = None

        # Look for pattern with simple_identifier
        for child in node.children:
            if child.type == "pattern":
                for sub in child.children:
                    if sub.type == "simple_identifier":
                        name = self._get_node_text(sub, source_code)
                        break
                if name:
                    break

        if not name:
            # Try value_binding_pattern for let/var declarations
            for child in node.children:
                if child.type == "value_binding_pattern":
                    for sub in child.children:
                        if sub.type == "pattern":
                            for inner in sub.children:
                                if inner.type == "simple_identifier":
                                    name = self._get_node_text(inner, source_code)
                                    break

        if not name:
            return None

        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)

        # Get type annotation
        type_annotation = None
        for child in node.children:
            if child.type == "type_annotation":
                type_annotation = self._get_node_text(child, source_code)
                break

        return StructureNode(
            type="property",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=type_annotation,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            children=[]
        )

    def _extract_subscript(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract subscript declaration."""
        modifiers = self._extract_modifiers(node, source_code)
        docstring = self._extract_docstring(node, source_code)

        # Build signature from parameters
        params = []
        for child in node.children:
            if child.type == "parameter":
                params.append(self._get_node_text(child, source_code))

        signature = f"[{', '.join(params)}]" if params else None

        return StructureNode(
            type="subscript",
            name="subscript",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_initializer(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract initializer declaration."""
        modifiers = self._extract_modifiers(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        signature = self._extract_function_signature(node, source_code)

        # Determine init type (init, init?, init!)
        name = "init"
        node_text = self._get_node_text(node, source_code)
        if "init?" in node_text[:20]:
            name = "init?"
        elif "init!" in node_text[:20]:
            name = "init!"

        return StructureNode(
            type="initializer",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            decorators=decorators,
            children=[]
        )

    def _extract_enum_case(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract enum case."""
        name = None
        for child in node.children:
            if child.type == "simple_identifier":
                name = self._get_node_text(child, source_code)
                break

        if not name:
            return None

        # Check for associated values
        signature = None
        for child in node.children:
            if child.type == "enum_type_parameters":
                signature = self._get_node_text(child, source_code)
                break

        docstring = self._extract_docstring(node, source_code)

        return StructureNode(
            type="case",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            children=[]
        )

    def _extract_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers from a declaration."""
        modifiers = []
        modifier_keywords = {
            "public", "private", "internal", "fileprivate", "open",
            "static", "class", "final", "lazy",
            "mutating", "nonmutating",
            "async", "nonisolated",
            "required", "convenience", "override",
            "weak", "unowned", "optional"
        }

        for child in node.children:
            if child.type == "modifiers":
                # Traverse all children of modifiers
                for mod_child in child.children:
                    # Extract text from the deepest level
                    mod_text = self._get_node_text(mod_child, source_code).strip()
                    if mod_text in modifier_keywords:
                        modifiers.append(mod_text)
                    else:
                        # Check leaf nodes
                        for leaf in mod_child.children:
                            leaf_text = self._get_node_text(leaf, source_code).strip()
                            if leaf_text in modifier_keywords:
                                modifiers.append(leaf_text)

            # Also check for 'class' as direct child (for class methods)
            elif child.type == "class" and node.type == "function_declaration":
                modifiers.append("class")

        return modifiers

    def _extract_decorators(self, node: Node, source_code: bytes) -> list[str]:
        """Extract attributes/decorators from a declaration."""
        decorators = []

        for child in node.children:
            if child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type == "attribute":
                        attr_text = self._get_node_text(mod_child, source_code).strip()
                        decorators.append(attr_text)

            elif child.type == "attribute":
                attr_text = self._get_node_text(child, source_code).strip()
                decorators.append(attr_text)

        return decorators

    def _extract_docstring(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract documentation comment preceding a declaration."""
        prev = node.prev_sibling

        # Skip over attributes
        while prev and prev.type in ("modifiers", "attribute"):
            prev = prev.prev_sibling

        comments = []
        while prev and prev.type == "comment":
            comment_text = self._get_node_text(prev, source_code).strip()

            # Handle /// documentation comments
            if comment_text.startswith("///"):
                comment_text = comment_text[3:].strip()
                comments.insert(0, comment_text)
            # Handle // regular comments
            elif comment_text.startswith("//"):
                comment_text = comment_text[2:].strip()
                comments.insert(0, comment_text)
            # Handle /* */ block comments
            elif comment_text.startswith("/*"):
                comment_text = comment_text[2:]
                if comment_text.endswith("*/"):
                    comment_text = comment_text[:-2]
                comment_text = comment_text.strip()
                if comment_text:
                    comments.insert(0, comment_text)

            prev = prev.prev_sibling

        if comments:
            return comments[0]
        return None

    def _extract_inheritance(self, node: Node, source_code: bytes) -> list[str]:
        """Extract inherited types/protocols from a declaration."""
        inheritance = []

        for child in node.children:
            if child.type == "inheritance_specifier":
                for spec_child in child.children:
                    if spec_child.type == "user_type":
                        type_name = self._get_node_text(spec_child, source_code)
                        inheritance.append(type_name)
                    elif spec_child.type == "type_identifier":
                        type_name = self._get_node_text(spec_child, source_code)
                        inheritance.append(type_name)

            elif child.type == "type_constraints":
                for constraint in child.children:
                    if constraint.type == "type_constraint":
                        constraint_text = self._get_node_text(constraint, source_code)
                        inheritance.append(f"where {constraint_text}")

        return inheritance

    def _extract_function_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature with parameters and return type."""
        parts = []
        in_params = False
        has_arrow = False

        for child in node.children:
            if child.type == "(":
                in_params = True
                parts.append("(")
            elif child.type == ")":
                parts.append(")")
                in_params = False
            elif child.type == "parameter" and in_params:
                param_text = self._get_node_text(child, source_code)
                if parts and parts[-1] != "(":
                    parts.append(", ")
                parts.append(param_text)
            elif child.type == "->":
                has_arrow = True
                parts.append(" -> ")
            elif child.type == "throws":
                parts.append(" throws")
            elif child.type == "async":
                parts.append(" async")
            elif child.type == "user_type" and has_arrow:
                # Return type
                parts.append(self._get_node_text(child, source_code))
            elif child.type == "type_identifier" and has_arrow:
                # Simple return type
                parts.append(self._get_node_text(child, source_code))
            elif child.type in ("tuple_type", "optional_type", "function_type") and has_arrow:
                parts.append(self._get_node_text(child, source_code))

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

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
            parent_structures[-1].end_line = node.end_point[0] + 1

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for severely malformed files."""
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find class declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+|open\s+|final\s+)*class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find struct declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+)*struct\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="struct",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find protocol declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+)*protocol\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="protocol",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+)*enum\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="enum",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find extension declarations
        for match in re.finditer(r'^extension\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="extension",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function declarations
        for match in re.finditer(r'^(?:public\s+|private\s+|internal\s+|static\s+|class\s+)*func\s+(\w+)\s*[<(]', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="function",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from SwiftAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract import statements AND type references from Swift file.

        For Swift, we extract both:
        1. Module imports (import Foundation, etc.) - external dependencies
        2. Type references - local dependencies within the same module

        Type references create edges in the dependency graph, allowing
        CodeMap to understand relationships between Swift files even though
        Swift doesn't have explicit file-to-file imports.
        """
        imports = []

        # Pattern 1: Regular import and @testable import
        import_pattern = r'^(?:@testable\s+)?import\s+(?:(?:struct|class|enum|protocol|func|typealias|var|let)\s+)?([^\s;]+)'

        for match in re.finditer(import_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            import_type = "import"
            if '@testable' in match.group(0):
                import_type = "@testable import"

            selective_match = re.search(r'import\s+(struct|class|enum|protocol|func|typealias|var|let)\s+', match.group(0))
            if selective_match:
                import_type = f"import {selective_match.group(1)}"

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type=import_type,
                    imported_names=[],
                )
            )

        # Extract type references (for intra-module dependencies)
        type_refs = self._extract_type_references(content)

        for type_name in type_refs:
            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=type_name,  # Type name, will be resolved to file
                    line=0,  # Line unknown for type references
                    import_type="type_reference",  # Special marker for CodeMap
                    imported_names=[type_name],
                )
            )

        return imports

    def _extract_type_references(self, content: str) -> set[str]:
        """
        Extract type names referenced in Swift file.

        Finds types used in:
        - Property declarations: var name: TypeName
        - Function parameters: func foo(param: TypeName)
        - Return types: func foo() -> TypeName
        - Generic constraints: where T: TypeName
        - Inheritance: class Foo: TypeName
        - Type instantiation: TypeName()
        - Type casting: as TypeName, as? TypeName
        """
        references = set()

        # Common Swift standard library types to exclude
        stdlib_types = {
            # Primitives
            'Int', 'Int8', 'Int16', 'Int32', 'Int64',
            'UInt', 'UInt8', 'UInt16', 'UInt32', 'UInt64',
            'Float', 'Double', 'Bool', 'String', 'Character',
            'Void', 'Never', 'Any', 'AnyObject', 'AnyClass',
            # Collections
            'Array', 'Dictionary', 'Set', 'Optional',
            # Foundation types
            'Date', 'Data', 'URL', 'UUID', 'Error',
            'NSObject', 'NSError', 'NSCoding',
            # UI types (commonly imported from frameworks)
            'View', 'Text', 'Image', 'Button', 'VStack', 'HStack', 'ZStack',
            'List', 'NavigationView', 'NavigationStack', 'NavigationLink',
            'Color', 'Font', 'CGFloat', 'CGPoint', 'CGSize', 'CGRect',
            'UIView', 'UIViewController', 'UIColor', 'UIImage',
            'UITableView', 'UICollectionView', 'UIButton', 'UILabel',
            # Common protocols
            'Codable', 'Decodable', 'Encodable', 'Hashable', 'Equatable',
            'Comparable', 'Identifiable', 'CustomStringConvertible',
            'ObservableObject', 'Published',
            # Keywords that look like types
            'Self', 'self', 'Type', 'some',
        }

        # Pattern 1: Type annotations - var/let name: Type
        type_annotation = r'(?:var|let)\s+\w+\s*:\s*(\[?\w+\]?(?:<[^>]+>)?(?:\?|\!)?)'
        for match in re.finditer(type_annotation, content):
            type_str = match.group(1)
            # Extract base type (remove Optional, Array brackets, generics)
            base_type = re.sub(r'[\[\]<>?!].*', '', type_str).strip()
            if base_type and base_type[0].isupper() and base_type not in stdlib_types:
                references.add(base_type)

        # Pattern 2: Function parameters - (param: Type)
        param_pattern = r'\(\s*(?:\w+\s+)?(\w+)\s*:\s*(\[?\w+\]?(?:<[^>]+>)?(?:\?|\!)?)'
        for match in re.finditer(param_pattern, content):
            type_str = match.group(2)
            base_type = re.sub(r'[\[\]<>?!].*', '', type_str).strip()
            if base_type and base_type[0].isupper() and base_type not in stdlib_types:
                references.add(base_type)

        # Pattern 3: Return types - -> Type
        return_pattern = r'->\s*(\[?\w+\]?(?:<[^>]+>)?(?:\?|\!)?)'
        for match in re.finditer(return_pattern, content):
            type_str = match.group(1)
            base_type = re.sub(r'[\[\]<>?!].*', '', type_str).strip()
            if base_type and base_type[0].isupper() and base_type not in stdlib_types:
                references.add(base_type)

        # Pattern 4: Type instantiation - TypeName(
        instantiation_pattern = r'\b([A-Z]\w+)\s*\('
        for match in re.finditer(instantiation_pattern, content):
            type_name = match.group(1)
            if type_name not in stdlib_types:
                references.add(type_name)

        # Pattern 5: Inheritance/conformance - : TypeName or , TypeName
        inheritance_pattern = r'(?:struct|class|enum|actor|extension)\s+\w+(?:<[^>]+>)?\s*:\s*([^{]+)\{'
        for match in re.finditer(inheritance_pattern, content):
            inheritance_list = match.group(1)
            # Split by comma and extract type names
            for part in inheritance_list.split(','):
                part = part.strip()
                # Handle generic constraints like SomeType<T>
                base_type = re.sub(r'<.*', '', part).strip()
                if base_type and base_type[0].isupper() and base_type not in stdlib_types:
                    references.add(base_type)

        # Pattern 6: Type casting - as TypeName, as? TypeName, as! TypeName
        cast_pattern = r'\bas[?!]?\s+([A-Z]\w+)'
        for match in re.finditer(cast_pattern, content):
            type_name = match.group(1)
            if type_name not in stdlib_types:
                references.add(type_name)

        # Pattern 7: Generic type parameters in angle brackets
        # e.g., Array<MyType>, Result<Success, Failure>
        generic_pattern = r'<([^>]+)>'
        for match in re.finditer(generic_pattern, content):
            generic_content = match.group(1)
            for part in re.split(r'[,:]', generic_content):
                part = part.strip()
                if part and part[0].isupper() and part not in stdlib_types:
                    references.add(part)

        return references

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in Swift file.

        Entry points:
        - @main attribute on struct/class/enum
        - main.swift file (Swift Package Manager)
        - @UIApplicationMain / @NSApplicationMain (deprecated but still used)
        - AppDelegate class
        - App struct conforming to SwiftUI App protocol
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        # Pattern 1: @main attribute
        main_attr_pattern = r'@main\s+(?:public\s+|internal\s+|private\s+|fileprivate\s+)*(?:struct|class|enum)\s+(\w+)'
        for match in re.finditer(main_attr_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_type",
                    line=line_num,
                    name=match.group(1),
                )
            )

        # Pattern 2: @UIApplicationMain / @NSApplicationMain (deprecated)
        app_main_pattern = r'@(?:UIApplicationMain|NSApplicationMain)\s+(?:public\s+|internal\s+|private\s+)*class\s+(\w+)'
        for match in re.finditer(app_main_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="app_delegate",
                    line=line_num,
                    name=match.group(1),
                )
            )

        # Pattern 3: main.swift file (SPM entry point)
        if filename == 'main.swift':
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_file",
                    line=1,
                    name="main.swift",
                )
            )

        # Pattern 4: AppDelegate class
        app_delegate_pattern = r'class\s+(AppDelegate|ApplicationDelegate)\s*:\s*(?:\w+,\s*)*(?:UIResponder|NSObject)'
        for match in re.finditer(app_delegate_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="app_delegate",
                    line=line_num,
                    name=match.group(1),
                )
            )

        # Pattern 5: SwiftUI App protocol conformance
        # struct MyApp: App { ... }
        swiftui_app_pattern = r'(?:struct|class)\s+(\w+)\s*:\s*(?:\w+,\s*)*App\s*\{'
        for match in re.finditer(swiftui_app_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            # Check if already detected via @main
            if not any(ep.name == match.group(1) and ep.type == "main_type" for ep in entry_points):
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="swiftui_app",
                        line=line_num,
                        name=match.group(1),
                    )
                )

        # Pattern 6: SceneDelegate
        scene_delegate_pattern = r'class\s+(SceneDelegate)\s*:\s*(?:\w+,\s*)*(?:UIResponder|NSObject)'
        for match in re.finditer(scene_delegate_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="scene_delegate",
                    line=line_num,
                    name=match.group(1),
                )
            )

        # Pattern 7: XCTestCase subclasses
        test_case_pattern = r'class\s+(\w+)\s*:\s*XCTestCase'
        for match in re.finditer(test_case_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="test_case",
                    line=line_num,
                    name=match.group(1),
                )
            )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract type definitions from Swift file by reusing scan() output.

        Returns struct, class, enum, protocol, actor, extension, and typealias definitions.
        This enables building a type->file mapping for dependency resolution.
        """
        try:
            structures = self.scan(content.encode("utf-8"))
            if not structures:
                return []
            return self._structures_to_definitions_swift(file_path, structures)
        except Exception:
            # Fallback to regex-based extraction
            return self._extract_definitions_regex(file_path, content)

    def _structures_to_definitions_swift(
        self, file_path: str, structures: list[StructureNode], parent: str = None
    ) -> list[DefinitionInfo]:
        """Convert StructureNode list to DefinitionInfo list for Swift.

        Swift has more type kinds than the base class handles (struct, enum, protocol, etc.)
        """
        definitions = []

        # Swift type kinds that should be included
        swift_types = {"class", "struct", "enum", "protocol", "actor", "extension", "typealias", "function", "method"}

        for node in structures:
            if node.type in swift_types:
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
                # For Swift, use the type name as parent for nested types
                child_parent = node.name if node.type in {"class", "struct", "enum", "protocol", "actor", "extension"} else parent
                definitions.extend(
                    self._structures_to_definitions_swift(file_path, node.children, child_parent)
                )

        return definitions

    def _extract_definitions_regex(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        # Pattern for type declarations
        type_pattern = r'''
            (?:^|\n)\s*
            (?:@\w+\s+)*                                    # Optional attributes
            (?:open\s+|public\s+|internal\s+|private\s+|fileprivate\s+)*
            (?:final\s+)?
            (struct|class|enum|protocol|actor|extension)\s+
            (\w+)
            (?:<[^>]+>)?
            (?:\s*:\s*[^{]+)?
            \s*\{
        '''

        for match in re.finditer(type_pattern, content, re.VERBOSE | re.MULTILINE):
            type_kind = match.group(1)
            type_name = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type=type_kind,
                    name=type_name,
                    line=line_num,
                    signature=None,
                    parent=None,
                )
            )

        # Also extract typealiases
        typealias_pattern = r'(?:^|\n)\s*(?:public\s+|internal\s+|private\s+|fileprivate\s+)?typealias\s+(\w+)\s*='
        for match in re.finditer(typealias_pattern, content, re.MULTILINE):
            type_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="typealias",
                    name=type_name,
                    line=line_num,
                    signature=None,
                    parent=None,
                )
            )

        return definitions

    # ===========================================================================
    # Classification (enhanced for Swift)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify Swift file into architectural cluster.

        Uses base class heuristics plus Swift-specific patterns.
        """
        # Use base class classification (handles common patterns)
        base_cluster = super().classify_file(file_path, content)

        # Swift-specific patterns
        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points
            if name == "main.swift":
                return "entry_points"
            if name in ("appdelegate.swift", "scenedelegate.swift"):
                return "entry_points"

            # Check for @main attribute
            if re.search(r'@main\s+(?:struct|class|enum)', content):
                return "entry_points"

            # Check for SwiftUI App
            if re.search(r'(?:struct|class)\s+\w+\s*:\s*(?:\w+,\s*)*App\s*\{', content):
                return "entry_points"

            # Test files
            if name.endswith('tests.swift') or name.endswith('test.swift'):
                return "tests"
            if 'xctest' in content.lower():
                return "tests"

            # Config files
            if name == "package.swift":
                return "config"
            if name in ("config.swift", "settings.swift", "constants.swift"):
                return "config"

            # ViewControllers
            if "viewcontroller" in name or "/viewcontrollers/" in path_lower:
                return "core_logic"

            # Views (SwiftUI and UIKit)
            if name.endswith("view.swift") or "/views/" in path_lower:
                return "core_logic"

            # Models
            if "/models/" in path_lower or name.endswith("model.swift"):
                return "core_logic"

            # ViewModels
            if "/viewmodels/" in path_lower or name.endswith("viewmodel.swift"):
                return "core_logic"

            # Services
            if "/services/" in path_lower or name.endswith("service.swift"):
                return "core_logic"

            # Managers
            if name.endswith("manager.swift") or "/managers/" in path_lower:
                return "core_logic"

            # Extensions (utility code)
            if name.endswith("+extension.swift") or "/extensions/" in path_lower:
                return "other"

            # Protocols
            if name.endswith("protocol.swift") or "/protocols/" in path_lower:
                return "core_logic"

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
        """
        Resolve Swift import/type reference to file path.

        Swift uses intra-module type references (no explicit imports for
        same-module types). These are resolved via the definitions_map
        which maps type names to the files that define them.
        """
        # Type references are resolved via definitions_map
        if module in definitions_map:
            return definitions_map[module]
        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """
        Format Swift entry point for display.

        Formats:
        - main_type: "@main TypeName @line"
        - swiftui_app: "TypeName: App @line"
        - app_delegate: "AppDelegate TypeName @line"
        - scene_delegate: "SceneDelegate @line"
        - main_file: "file (main.swift)"
        - test_case: "XCTestCase TypeName @line"
        """
        if ep.type == "main_type":
            return f"  {ep.file}:@main {ep.name} @{ep.line}"
        elif ep.type == "swiftui_app":
            return f"  {ep.file}:{ep.name}: App @{ep.line}"
        elif ep.type == "app_delegate":
            return f"  {ep.file}:AppDelegate {ep.name} @{ep.line}"
        elif ep.type == "scene_delegate":
            return f"  {ep.file}:SceneDelegate @{ep.line}"
        elif ep.type == "main_file":
            return f"  {ep.file} (main.swift)"
        elif ep.type == "test_case":
            return f"  {ep.file}:XCTestCase {ep.name} @{ep.line}"
        else:
            return super().format_entry_point(ep)
