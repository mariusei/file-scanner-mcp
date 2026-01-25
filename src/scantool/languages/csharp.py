"""C# language support - unified scanner and analyzer.

This module combines CSharpScanner and CSharpAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_c_sharp
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class CSharpLanguage(BaseLanguage):
    """Unified language handler for C# files (.cs, .csx).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract classes, interfaces, structs, enums, methods, properties
    - extract_imports(): Find using directives
    - find_entry_points(): Find Main methods, ASP.NET controllers, minimal APIs
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Find method calls (basic implementation)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_c_sharp.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".cs", ".csx"]

    @classmethod
    def get_language_name(cls) -> str:
        return "C#"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip designer and generated files."""
        lower = filename.lower()
        if '.designer.cs' in lower:
            return True
        if lower.endswith('.g.cs') or lower.endswith('.generated.cs'):
            return True
        if lower == 'assemblyinfo.cs':
            return True
        return False

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip C# files that should not be analyzed.

        C#-specific skip patterns:
        - Skip designer files (*.Designer.cs, *.designer.cs)
        - Skip generated files (*.g.cs, *.generated.cs)
        - Skip auto-generated AssemblyInfo files
        - bin/ and obj/ directories
        """
        filename = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # Skip designer files
        if '.designer.cs' in filename:
            return False

        # Skip generated files
        if filename.endswith('.g.cs') or filename.endswith('.generated.cs'):
            return False

        # Skip auto-generated AssemblyInfo files
        if filename == 'assemblyinfo.cs':
            return False

        # Skip bin/obj (should be caught by COMMON_SKIP_DIRS, but double-check)
        if '/bin/' in path_lower or '/obj/' in path_lower:
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value C# files for inventory listing.

        Low-value files (unless central):
        - Empty or near-empty files
        - Global usings files (typically boilerplate)
        """
        filename = Path(file_path).name.lower()

        # GlobalUsings.cs is usually auto-generated boilerplate
        if filename == 'globalusings.cs' and size < 500:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from CSharpScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan C# source code and extract structure with metadata."""
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

            # Using directives
            if node.type == "using_directive":
                self._handle_using(node, parent_structures)

            # Namespace declaration
            elif node.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
                self._handle_namespace(node, parent_structures, source_code, root, traverse)

            # Classes
            elif node.type == "class_declaration":
                class_node = self._extract_class(node, source_code)
                parent_structures.append(class_node)

                # Traverse children for methods, properties, nested classes, etc.
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, class_node.children)

            # Interfaces
            elif node.type == "interface_declaration":
                interface_node = self._extract_interface(node, source_code)
                parent_structures.append(interface_node)

                # Traverse children for method signatures, properties
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, interface_node.children)

            # Structs
            elif node.type == "struct_declaration":
                struct_node = self._extract_struct(node, source_code)
                parent_structures.append(struct_node)

                # Traverse children for methods, properties, etc.
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, struct_node.children)

            # Enums
            elif node.type == "enum_declaration":
                enum_node = self._extract_enum(node, source_code)
                parent_structures.append(enum_node)

            # Records (C# 9+)
            elif node.type == "record_declaration":
                record_node = self._extract_record(node, source_code)
                parent_structures.append(record_node)

                # Traverse children for methods, properties
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, record_node.children)

            # Methods
            elif node.type == "method_declaration":
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Properties
            elif node.type == "property_declaration":
                property_node = self._extract_property(node, source_code)
                parent_structures.append(property_node)

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

    def _extract_class(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract class with full metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)

        # Get base class and interfaces
        signature_parts = []
        if type_params:
            signature_parts.append(type_params)

        # Get base list (base class and interfaces)
        base_list = node.child_by_field_name("bases")
        if base_list:
            base_text = self._get_node_text(base_list, source_code).strip()
            # Remove the colon if present
            base_text = base_text.lstrip(':').strip()
            signature_parts.append(f": {base_text}")

        signature = " ".join(signature_parts) if signature_parts else None

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)

        # Get base interfaces
        signature_parts = []
        if type_params:
            signature_parts.append(type_params)

        base_list = node.child_by_field_name("bases")
        if base_list:
            base_text = self._get_node_text(base_list, source_code).strip()
            base_text = base_text.lstrip(':').strip()
            signature_parts.append(f": {base_text}")

        signature = " ".join(signature_parts) if signature_parts else None

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

    def _extract_struct(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract struct declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)

        # Get interfaces
        signature_parts = []
        if type_params:
            signature_parts.append(type_params)

        base_list = node.child_by_field_name("bases")
        if base_list:
            base_text = self._get_node_text(base_list, source_code).strip()
            base_text = base_text.lstrip(':').strip()
            signature_parts.append(f": {base_text}")

        signature = " ".join(signature_parts) if signature_parts else None

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

        return StructureNode(
            type="struct",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_record(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract record declaration (C# 9+)."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get type parameters (generics)
        type_params = self._extract_type_parameters(node, source_code)

        # Get parameters (for positional records)
        signature_parts = []
        if type_params:
            signature_parts.append(type_params)

        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            signature_parts.append(params_text)

        # Get base list
        base_list = node.child_by_field_name("bases")
        if base_list:
            base_text = self._get_node_text(base_list, source_code).strip()
            base_text = base_text.lstrip(':').strip()
            signature_parts.append(f": {base_text}")

        signature = " ".join(signature_parts) if signature_parts else None

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

        return StructureNode(
            type="record",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._normalize_signature(signature) if signature else None,
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

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get base type (enums can have a base type like : byte)
        # Look for base_list child node
        signature = None
        for child in node.children:
            if child.type == "base_list":
                base_text = self._get_node_text(child, source_code).strip()
                base_text = base_text.lstrip(':').strip()
                signature = f": {base_text}"
                break

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

    def _extract_property(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract property declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get property type
        type_node = node.child_by_field_name("type")
        signature = None
        if type_node:
            type_text = self._get_node_text(type_node, source_code).strip()
            signature = f": {type_text}"

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

        return StructureNode(
            type="property",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            decorators=decorators,
            docstring=docstring,
            modifiers=modifiers,
            children=[]
        )

    def _extract_constructor(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract constructor declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get modifiers
        modifiers = self._extract_modifiers(node, source_code)

        # Get attributes
        decorators = self._extract_attributes(node, source_code)

        # Get signature (parameters)
        params_node = node.child_by_field_name("parameters")
        signature = None
        if params_node:
            signature = self._get_node_text(params_node, source_code)

        # Get XML documentation comment
        docstring = self._extract_xml_doc(node, source_code)

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

        # Get return type (it's a child before the method name)
        # Could be generic_name, predefined_type, identifier, etc.
        return_type = None
        name_node = node.child_by_field_name("name")
        for child in node.children:
            # Stop when we reach the name
            if child == name_node:
                break
            # Skip modifiers
            if child.type == "modifier":
                continue
            # This must be the return type
            if child.type in ("generic_name", "predefined_type", "identifier", "nullable_type",
                            "array_type", "qualified_name", "tuple_type"):
                return_type = self._get_node_text(child, source_code).strip()
                break

        # Get type parameters (generics on method)
        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            type_params_text = self._get_node_text(type_params, source_code)
            parts.append(type_params_text)

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Add return type at the end
        if return_type:
            parts.append(f": {return_type}")

        signature = " ".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers like public, private, static, readonly, async, virtual, override, abstract."""
        modifiers = []

        for child in node.children:
            if child.type == "modifier":
                # Modifier is wrapped - get the actual keyword
                modifier_text = self._get_node_text(child, source_code).strip()
                if modifier_text:
                    modifiers.append(modifier_text)

        return modifiers

    def _extract_attributes(self, node: Node, source_code: bytes) -> list[str]:
        """Extract attributes (C# decorators) from a class/method/property."""
        attributes = []

        # In C#, attributes are children of the node, appearing before modifiers
        for child in node.children:
            if child.type == "attribute_list":
                attr_text = self._get_node_text(child, source_code).strip()
                attributes.append(attr_text)

        return attributes

    def _extract_xml_doc(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract first line of XML documentation comment (///)."""
        # Try to find comments before the node
        start_byte = node.start_byte

        # Look backwards in source to find XML doc comments
        text = source_code.decode('utf-8', errors='replace')
        lines_before = text[:start_byte].split('\n')

        # Collect XML doc comment lines (///)
        doc_lines = []
        for line in reversed(lines_before):
            stripped = line.strip()
            if stripped.startswith('///'):
                # Remove /// and extract content
                content = stripped[3:].strip()
                # Extract from <summary> tags if present
                if '<summary>' in content:
                    content = content.replace('<summary>', '').strip()
                if '</summary>' in content:
                    content = content.replace('</summary>', '').strip()
                if content and not content.startswith('<') and not content.startswith('/'):
                    doc_lines.insert(0, content)
            elif stripped and not stripped.startswith('//'):
                # Stop at first non-comment line
                break

        # Return first meaningful line
        for line in doc_lines:
            if line and not line.startswith('<') and not line.startswith('/'):
                return line

        return None

    def _extract_type_parameters(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract type parameters (generics) like <T> or <TKey, TValue>."""
        # Try field-based access first
        type_params = node.child_by_field_name("type_parameters")
        if type_params:
            return self._get_node_text(type_params, source_code)

        # Fallback: look for type_parameter_list child
        for child in node.children:
            if child.type == "type_parameter_list":
                return self._get_node_text(child, source_code)

        return None

    def _handle_namespace(self, node: Node, parent_structures: list, source_code: bytes, root: Node, traverse_func):
        """Handle namespace declaration."""
        name_node = node.child_by_field_name("name")

        if name_node:
            namespace_name = self._get_node_text(name_node, source_code)
            namespace_node = StructureNode(
                type="namespace",
                name=namespace_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                children=[]
            )
            parent_structures.append(namespace_node)

            # Traverse children within namespace
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    traverse_func(child, namespace_node.children)
            else:
                # File-scoped namespace - traverse remaining children
                for child in node.children:
                    if child.start_point[0] > node.start_point[0]:
                        traverse_func(child, namespace_node.children)

    def _handle_using(self, node: Node, parent_structures: list):
        """Group using directives together."""
        if not parent_structures or parent_structures[-1].type != "imports":
            import_node = StructureNode(
                type="imports",
                name="using directives",
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

        # Find namespace declaration
        namespace_match = re.search(r'^\s*namespace\s+([\w.]+)', text, re.MULTILINE)
        if namespace_match:
            line_num = text[:namespace_match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="namespace",
                name=namespace_match.group(1),
                start_line=line_num,
                end_line=line_num
            ))

        # Find class definitions
        for match in re.finditer(r'^\s*(?:public\s+)?(?:abstract\s+)?(?:sealed\s+)?class\s+(\w+)', text, re.MULTILINE):
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

        # Find struct definitions
        for match in re.finditer(r'^\s*(?:public\s+)?struct\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="struct",
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
        for match in re.finditer(r'^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:async\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find property definitions
        for match in re.finditer(r'^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\{', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="property",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from CSharpAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract using directives from C# file.

        Patterns supported:
        - using System.Collections;
        - using System.Collections.Generic;
        - using static System.Math;
        - using Alias = System.Collections.Generic.List<int>;
        """
        imports = []

        # Pattern 1: Standard using directives
        # using System.Collections.Generic;
        using_pattern = r'^\s*using\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;'
        for match in re.finditer(using_pattern, content, re.MULTILINE):
            namespace = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=namespace,
                    line=line_num,
                    import_type="using",
                )
            )

        # Pattern 2: Static using directives
        # using static System.Math;
        static_using_pattern = r'^\s*using\s+static\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;'
        for match in re.finditer(static_using_pattern, content, re.MULTILINE):
            namespace = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=namespace,
                    line=line_num,
                    import_type="static_using",
                )
            )

        # Pattern 3: Alias using directives
        # using MyList = System.Collections.Generic.List<int>;
        # Note: Allow full type syntax including generics with commas and spaces
        alias_using_pattern = r'^\s*using\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_.<>,\s]+?)\s*;'
        for match in re.finditer(alias_using_pattern, content, re.MULTILINE):
            alias = match.group(1)
            namespace = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=namespace,
                    line=line_num,
                    import_type="alias_using",
                    imported_names=[alias],
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in C# file.

        Entry points:
        - static void Main(string[] args)
        - static async Task Main(string[] args)
        - static int Main()
        - [ApiController] or [Controller] attributes (ASP.NET)
        - [HttpGet], [HttpPost], etc. (ASP.NET action methods)
        - Top-level statements (C# 9+)
        """
        entry_points = []

        # Pattern 1: Main methods (various signatures)
        # static void Main(), static int Main(string[] args), static async Task Main()
        main_patterns = [
            r'^\s*(?:public\s+|private\s+|internal\s+)?static\s+(?:async\s+)?(?:void|int|Task(?:<int>)?)\s+Main\s*\(',
        ]
        for pattern in main_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[:match.start()].count('\n') + 1
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="main_function",
                        line=line_num,
                        name="Main",
                    )
                )

        # Pattern 2: ASP.NET Controllers (class-level attributes)
        # [ApiController], [Controller]
        controller_pattern = r'^\s*\[(?:Api)?Controller\]'
        for match in re.finditer(controller_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1

            # Try to find the class name following the attribute
            remaining_content = content[match.end():]
            class_match = re.search(r'\s*(?:public\s+|internal\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)', remaining_content)
            class_name = class_match.group(1) if class_match else "Controller"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="controller",
                    line=line_num,
                    name=class_name,
                    framework="ASP.NET",
                )
            )

        # Pattern 3: ASP.NET Action methods (HTTP verb attributes)
        # [HttpGet], [HttpPost], [HttpPut], [HttpDelete], etc.
        http_verb_pattern = r'^\s*\[Http(?:Get|Post|Put|Delete|Patch|Head|Options)\]'
        for match in re.finditer(http_verb_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1

            # Try to find the method name following the attribute
            remaining_content = content[match.end():]
            method_match = re.search(
                r'\s*(?:public\s+|private\s+|protected\s+|internal\s+)?(?:async\s+)?(?:Task<?[^>]*>?|ActionResult<?[^>]*>?|IActionResult|[A-Za-z_][A-Za-z0-9_.<>]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(',
                remaining_content
            )
            method_name = method_match.group(1) if method_match else "ActionMethod"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="http_handler",
                    line=line_num,
                    name=method_name,
                    framework="ASP.NET",
                )
            )

        # Pattern 4: Startup class (ASP.NET Core convention)
        # public class Startup
        startup_pattern = r'^\s*(?:public\s+)?class\s+Startup\s*(?::|{)'
        for match in re.finditer(startup_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="startup_class",
                    line=line_num,
                    name="Startup",
                    framework="ASP.NET Core",
                )
            )

        # Pattern 5: Program class (ASP.NET Core 6+ minimal API)
        # Look for WebApplication.CreateBuilder or WebApplicationBuilder
        minimal_api_pattern = r'(?:WebApplication\.CreateBuilder|WebApplicationBuilder)'
        for match in re.finditer(minimal_api_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="minimal_api",
                    line=line_num,
                    name="Program",
                    framework="ASP.NET Core",
                )
            )
            break  # Only report once per file

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

        Extended for C# to handle more types (interfaces, structs, etc.)
        """
        definitions = []

        for node in structures:
            # Include C#-specific types
            if node.type in ("class", "function", "method", "interface", "struct", "enum", "record", "constructor"):
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
                child_parent = node.name if node.type in ("class", "interface", "struct", "record", "namespace") else parent
                definitions.extend(
                    self._structures_to_definitions(file_path, node.children, child_parent)
                )

        return definitions

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        for match in re.finditer(r"^\s*(?:public\s+)?class\s+(\w+)", content, re.MULTILINE):
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

        for match in re.finditer(
            r"^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:\w+)\s+(\w+)\s*\(",
            content,
            re.MULTILINE
        ):
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
        """Extract method calls using tree-sitter.

        Note: This needs tree-sitter parsing because call sites are
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

            # Track current method/function context
            if node.type in ("method_declaration", "constructor_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    current_function = source_bytes[
                        name_node.start_byte : name_node.end_byte
                    ].decode("utf-8")

                for child in node.children:
                    traverse(child, current_function)

                current_function = context_func
                return

            # Invocation expressions (method calls)
            if node.type == "invocation_expression":
                func_node = node.child_by_field_name("function")
                if func_node:
                    # Simple identifier call: MethodName()
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

                    # Member access call: obj.Method() or Class.StaticMethod()
                    elif func_node.type == "member_access_expression":
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

        # Simple pattern to find method calls
        for match in re.finditer(r"\b(\w+)\s*\(", content):
            callee_name = match.group(1)
            line = content[: match.start()].count("\n") + 1

            # Skip keywords and common constructs
            if callee_name in [
                "if", "for", "while", "foreach", "switch", "catch",
                "using", "lock", "return", "new", "typeof", "nameof",
                "class", "struct", "interface", "enum", "void", "int",
                "string", "bool", "double", "float", "decimal", "byte",
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
    # Classification (enhanced for C#)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify C# file into architectural cluster.

        Uses base class heuristics plus C#-specific patterns.
        """
        # Use base class classification (handles common patterns like test_)
        base_cluster = super().classify_file(file_path, content)

        # C#-specific patterns
        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points (Program.cs, Startup.cs)
            if name in ["program.cs", "startup.cs"]:
                return "entry_points"

            # Check for Main method
            if re.search(r'^\s*static\s+(?:async\s+)?(?:void|int|Task)\s+Main\s*\(', content, re.MULTILINE):
                return "entry_points"

            # Controllers
            if "/controllers/" in path_lower or name.endswith("controller.cs"):
                return "core_logic"

            # ASP.NET Controller attribute
            if re.search(r'^\s*\[(?:Api)?Controller\]', content, re.MULTILINE):
                return "core_logic"

            # Models
            if "/models/" in path_lower or name.endswith("model.cs"):
                return "core_logic"

            # Services
            if "/services/" in path_lower or name.endswith("service.cs"):
                return "core_logic"

            # Repositories
            if "/repositories/" in path_lower or name.endswith("repository.cs"):
                return "core_logic"

            # Config files
            if name in ["appsettings.cs", "config.cs", "configuration.cs"]:
                return "config"

            # Extensions (helper methods)
            if name.endswith("extensions.cs"):
                return "utilities"

            # Tests (NUnit, xUnit, MSTest patterns)
            if "test" in name or "/tests/" in path_lower:
                return "tests"

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
        Resolve C# using directive to file path.

        C# uses namespace imports, not file imports. We try to match
        namespace parts to file paths.

        System.* namespaces are skipped.
        """
        # Skip system namespaces
        if module.startswith(("System", "Microsoft", "Windows")):
            return None

        # Try matching namespace to file path
        # Namespace.ClassName -> Namespace/ClassName.cs
        parts = module.split(".")
        candidate = "/".join(parts) + ".cs"
        if candidate in all_files:
            return candidate

        # Just the last part (class name)
        if len(parts) > 0:
            for f in all_files:
                if f.endswith(f"/{parts[-1]}.cs") or f == f"{parts[-1]}.cs":
                    return f

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """
        Format C# entry point for display.

        Formats:
        - main_method: "static void Main @line"
        - controller: "[ApiController] ControllerName @line"
        - aspnet_app: "WebApplication @line"
        """
        if ep.type == "main_function":
            return f"  {ep.file}:static void Main @{ep.line}"
        elif ep.type == "controller":
            return f"  {ep.file}:[ApiController] {ep.name} @{ep.line}"
        elif ep.type == "aspnet_app":
            return f"  {ep.file}:WebApplication @{ep.line}"
        elif ep.type == "top_level":
            return f"  {ep.file}:top-level statements @{ep.line}"
        elif ep.type == "minimal_api":
            return f"  {ep.file}:minimal API @{ep.line}"
        elif ep.type == "startup_class":
            return f"  {ep.file}:Startup class @{ep.line}"
        elif ep.type == "http_handler":
            return f"  {ep.file}:[Http*] {ep.name} @{ep.line}"
        else:
            return super().format_entry_point(ep)
