"""C/C++ language support - unified scanner and analyzer.

This module combines CCppScanner and CppAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_cpp
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class CCppLanguage(BaseLanguage):
    """Unified language handler for C/C++ files.

    Provides both structure scanning and semantic analysis:
    - scan(): Extract structs, classes, functions, methods with signatures and metadata
    - extract_imports(): Find #include statements
    - find_entry_points(): Find main functions, WinMain, DllMain, test macros
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Find function/method calls (not yet implemented)

    Supports: .c, .cc, .cpp, .cxx, .h, .hpp, .hh, .hxx
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_cpp.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"]

    @classmethod
    def get_language_name(cls) -> str:
        return "C/C++"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip generated C/C++ files."""
        filename_lower = filename.lower()

        # Skip protobuf generated files
        if filename_lower.endswith('.pb.h') or filename_lower.endswith('.pb.cc') or filename_lower.endswith('.pb.cpp'):
            return True

        # Skip Qt generated files
        if filename_lower.startswith('moc_') and (filename_lower.endswith('.cpp') or filename_lower.endswith('.h')):
            return True
        if filename_lower.startswith('ui_') and filename_lower.endswith('.h'):
            return True
        if filename_lower.startswith('qrc_') and filename_lower.endswith('.cpp'):
            return True

        # Skip other generated files
        if filename_lower.endswith('.gen.h') or filename_lower.endswith('.gen.cpp'):
            return True

        return False

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip C/C++ files that should not be analyzed.

        C/C++-specific skip patterns:
        - Skip protobuf generated files (*.pb.h, *.pb.cc)
        - Skip Qt generated files (moc_*.cpp, ui_*.h, qrc_*.cpp)
        - Skip other generated files (*.gen.h, *.gen.cpp)
        """
        filename = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # Skip protobuf generated files
        if filename.endswith('.pb.h') or filename.endswith('.pb.cc') or filename.endswith('.pb.cpp'):
            return False

        # Skip Qt meta-object compiler generated files
        if filename.startswith('moc_') and (filename.endswith('.cpp') or filename.endswith('.h')):
            return False

        # Skip Qt UI generated files
        if filename.startswith('ui_') and filename.endswith('.h'):
            return False

        # Skip Qt resource compiler generated files
        if filename.startswith('qrc_') and filename.endswith('.cpp'):
            return False

        # Skip other generated files
        if filename.endswith('.gen.h') or filename.endswith('.gen.cpp'):
            return False

        # Skip if "generated" is in filename
        if 'generated' in filename and 'generator' not in filename:
            return False

        # Skip build directories (should be caught by tier 1, but double-check)
        if '/build/' in path_lower or '/cmake-build-' in path_lower:
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value C/C++ files for inventory listing.

        Low-value files (unless central):
        - Very small header files (likely just declarations)
        - Files in test/mock directories that are very small
        """
        filename = Path(file_path).name.lower()

        # Small header-only forward declarations
        if filename.endswith(('.h', '.hpp', '.hh', '.hxx')) and size < 100:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from CCppScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan C/C++ source code and extract structure with metadata."""
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

            # Structs
            if node.type == "struct_specifier":
                struct_node = self._extract_struct(node, source_code)
                if struct_node:
                    parent_structures.append(struct_node)
                    # Traverse children for nested declarations
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            traverse(child, struct_node.children)

            # Classes (C++)
            elif node.type == "class_specifier":
                class_node = self._extract_class(node, source_code)
                if class_node:
                    parent_structures.append(class_node)
                    # Traverse children for methods and nested structures
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            traverse(child, class_node.children)

            # Enums
            elif node.type == "enum_specifier":
                enum_node = self._extract_enum(node, source_code)
                if enum_node:
                    parent_structures.append(enum_node)

            # Namespaces (C++)
            elif node.type == "namespace_definition":
                namespace_node = self._extract_namespace(node, source_code)
                if namespace_node:
                    parent_structures.append(namespace_node)
                    # Traverse children
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            traverse(child, namespace_node.children)

            # Functions (both declarations and definitions)
            elif node.type == "function_definition":
                func_node = self._extract_function(node, source_code, root)
                if func_node:
                    parent_structures.append(func_node)

            # Function declarations
            elif node.type == "declaration":
                # Check if this is a function declaration
                func_node = self._extract_function_declaration(node, source_code, root)
                if func_node:
                    parent_structures.append(func_node)

            # Method definitions (inside classes)
            elif node.type == "field_declaration":
                method_node = self._extract_method(node, source_code)
                if method_node:
                    parent_structures.append(method_node)

            # Preprocessor includes
            elif node.type == "preproc_include":
                self._handle_include(node, parent_structures, source_code)

            else:
                # Keep traversing for top-level structures
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_struct(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract struct declaration."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous struct
            return None

        name = self._get_node_text(name_node, source_code)

        # Get comment
        comment = self._extract_comment(node, source_code)

        return StructureNode(
            type="struct",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=comment,
            children=[]
        )

    def _extract_class(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract C++ class declaration."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous class
            return None

        name = self._get_node_text(name_node, source_code)

        # Get base classes
        bases = self._extract_base_classes(node, source_code)
        signature = bases if bases else None

        # Get comment
        comment = self._extract_comment(node, source_code)

        # Get modifiers (from declaration context)
        modifiers = self._extract_class_modifiers(node, source_code)

        return StructureNode(
            type="class",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=comment,
            modifiers=modifiers,
            children=[]
        )

    def _extract_enum(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract enum declaration."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous enum
            return None

        name = self._get_node_text(name_node, source_code)

        # Get comment
        comment = self._extract_comment(node, source_code)

        return StructureNode(
            type="enum",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=comment,
            children=[]
        )

    def _extract_namespace(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract C++ namespace declaration."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Anonymous namespace
            name = "<anonymous>"
        else:
            name = self._get_node_text(name_node, source_code)

        # Get comment
        comment = self._extract_comment(node, source_code)

        return StructureNode(
            type="namespace",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=comment,
            children=[]
        )

    def _extract_function(self, node: Node, source_code: bytes, root: Node) -> Optional[StructureNode]:
        """Extract function definition."""
        declarator = node.child_by_field_name("declarator")
        if not declarator:
            return None

        # Get function name from declarator
        name = self._extract_function_name(declarator, source_code)
        if not name:
            return None

        # Determine if it's a method or function
        is_method = any(p.type in ("class_specifier", "struct_specifier") for p in self._get_ancestors(root, node))
        type_name = "method" if is_method else "function"

        # Get signature
        signature = self._extract_function_signature(declarator, source_code)

        # Get return type
        return_type = self._extract_return_type(node, source_code)
        if return_type and signature:
            signature = f"{return_type} {signature}"

        # Get comment
        comment = self._extract_comment(node, source_code)

        # Get modifiers
        modifiers = self._extract_function_modifiers(node, source_code)

        # Get attributes
        attributes = self._extract_attributes(node, source_code)
        if attributes:
            modifiers.extend(attributes)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type=type_name,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._normalize_signature(signature) if signature else None,
            docstring=comment,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_function_declaration(self, node: Node, source_code: bytes, root: Node) -> Optional[StructureNode]:
        """Extract function declaration (not definition)."""
        # Find declarator in the declaration
        declarator = None
        for child in node.children:
            if child.type == "function_declarator":
                declarator = child
                break
            # Look deeper if needed
            if child.type == "init_declarator":
                for subchild in child.children:
                    if subchild.type == "function_declarator":
                        declarator = subchild
                        break

        if not declarator:
            return None

        # Get function name
        name = self._extract_function_name(declarator, source_code)
        if not name:
            return None

        # Determine if it's a method or function
        is_method = any(p.type in ("class_specifier", "struct_specifier") for p in self._get_ancestors(root, node))
        type_name = "method" if is_method else "function"

        # Get signature
        signature = self._extract_function_signature(declarator, source_code)

        # Get return type
        return_type = self._extract_return_type(node, source_code)
        if return_type and signature:
            signature = f"{return_type} {signature}"

        # Get comment
        comment = self._extract_comment(node, source_code)

        # Get modifiers
        modifiers = self._extract_function_modifiers(node, source_code)

        return StructureNode(
            type=type_name,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._normalize_signature(signature) if signature else None,
            docstring=comment,
            modifiers=modifiers,
            children=[]
        )

    def _extract_method(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract method from field declaration."""
        # Check if this field declaration is actually a method
        declarator = None
        for child in node.children:
            if child.type == "function_declarator":
                declarator = child
                break

        if not declarator:
            return None

        # Get method name
        name = self._extract_function_name(declarator, source_code)
        if not name:
            return None

        # Get signature
        signature = self._extract_function_signature(declarator, source_code)

        # Get return type
        return_type = self._extract_return_type(node, source_code)
        if return_type and signature:
            signature = f"{return_type} {signature}"

        # Get comment
        comment = self._extract_comment(node, source_code)

        # Get modifiers (public, private, protected, virtual, static, const)
        modifiers = self._extract_method_modifiers(node, source_code)

        return StructureNode(
            type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=self._normalize_signature(signature) if signature else None,
            docstring=comment,
            modifiers=modifiers,
            children=[]
        )

    def _extract_function_name(self, declarator: Node, source_code: bytes) -> Optional[str]:
        """Extract function name from declarator."""
        # The declarator can have different structures
        # Look for identifier or field_identifier
        for child in declarator.children:
            if child.type in ("identifier", "field_identifier", "destructor_name"):
                return self._get_node_text(child, source_code)
            elif child.type == "qualified_identifier":
                # Get last part of qualified name
                for subchild in reversed(child.children):
                    if subchild.type == "identifier":
                        return self._get_node_text(subchild, source_code)
            elif child.type in ("pointer_declarator", "reference_declarator"):
                # Recurse into pointer/reference declarators
                name = self._extract_function_name(child, source_code)
                if name:
                    return name

        return None

    def _extract_function_signature(self, declarator: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature (parameters)."""
        params_node = declarator.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            return params_text
        return None

    def _extract_return_type(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract return type from function node."""
        type_node = node.child_by_field_name("type")
        if type_node:
            return_type = self._get_node_text(type_node, source_code).strip()
            return return_type
        return None

    def _extract_base_classes(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract base classes from class declaration."""
        parts = []

        for child in node.children:
            if child.type == "base_class_clause":
                # Get full base class clause text
                base_text = self._get_node_text(child, source_code).strip()
                # Remove leading colon if present
                if base_text.startswith(":"):
                    base_text = base_text[1:].strip()
                parts.append(base_text)

        return ": " + ", ".join(parts) if parts else None

    def _extract_comment(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract comment before node."""
        prev = node.prev_sibling

        # Look for comment nodes before this node
        while prev:
            if prev.type == "comment":
                comment_text = self._get_node_text(prev, source_code).strip()
                # Parse comment (// or /* */)
                if comment_text.startswith("//"):
                    return comment_text[2:].strip()
                elif comment_text.startswith("/*"):
                    # Extract first line of block comment
                    lines = comment_text[2:-2].strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        # Remove leading asterisks
                        if line.startswith("*"):
                            line = line[1:].strip()
                        if line:
                            return line
                return None
            prev = prev.prev_sibling

        return None

    def _extract_class_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for classes."""
        modifiers = []

        # Look at parent to see if it's a template
        parent = node.parent
        if parent and parent.type == "template_declaration":
            modifiers.append("template")

        return modifiers

    def _extract_function_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for functions (static, inline, virtual, const, etc.)."""
        modifiers = []

        # Check for storage class specifiers
        for child in node.children:
            if child.type == "storage_class_specifier":
                modifier_text = self._get_node_text(child, source_code)
                modifiers.append(modifier_text)
            elif child.type == "type_qualifier":
                qualifier_text = self._get_node_text(child, source_code)
                modifiers.append(qualifier_text)
            elif child.type == "virtual":
                modifiers.append("virtual")

        # Check declarator for const
        declarator = node.child_by_field_name("declarator")
        if declarator:
            for child in declarator.children:
                if child.type == "type_qualifier" and "const" in self._get_node_text(child, source_code):
                    if "const" not in modifiers:
                        modifiers.append("const")

        return modifiers

    def _extract_method_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract modifiers for methods (public, private, protected, virtual, static, const)."""
        modifiers = []

        # Check for access specifiers (handled at class level typically)
        # Check for storage class specifiers and qualifiers
        for child in node.children:
            if child.type == "storage_class_specifier":
                modifier_text = self._get_node_text(child, source_code)
                modifiers.append(modifier_text)
            elif child.type == "type_qualifier":
                qualifier_text = self._get_node_text(child, source_code)
                modifiers.append(qualifier_text)
            elif child.type == "virtual_specifier":
                modifiers.append("virtual")
            elif child.type == "virtual":
                modifiers.append("virtual")

        return modifiers

    def _extract_attributes(self, node: Node, source_code: bytes) -> list[str]:
        """Extract C++ attributes like [[nodiscard]], __attribute__, etc."""
        attributes = []

        for child in node.children:
            if child.type == "attribute_declaration":
                attr_text = self._get_node_text(child, source_code).strip()
                attributes.append(attr_text)
            elif child.type == "attribute_specifier":
                attr_text = self._get_node_text(child, source_code).strip()
                attributes.append(attr_text)

        return attributes

    def _handle_include(self, node: Node, parent_structures: list, source_code: bytes):
        """Group include statements together."""
        if not parent_structures or parent_structures[-1].type != "includes":
            include_node = StructureNode(
                type="includes",
                name="#include directives",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(include_node)
        else:
            # Extend the end line of the existing include group
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
        for match in re.finditer(r'\bstruct\s+(\w+)\s*\{', text):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="struct",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find class definitions
        for match in re.finditer(r'\bclass\s+(\w+)', text):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find enum definitions
        for match in re.finditer(r'\benum\s+(?:class\s+)?(\w+)', text):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="enum",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find namespace definitions
        for match in re.finditer(r'\bnamespace\s+(\w+)', text):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="namespace",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function definitions (basic pattern)
        for match in re.finditer(r'\b(\w+)\s+(\w+)\s*\([^)]*\)\s*\{', text):
            line_num = text[:match.start()].count('\n') + 1
            func_name = match.group(2)
            structures.append(StructureNode(
                type="function",
                name=func_name + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from CppAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract #include statements from C/C++ file.

        Patterns supported:
        - #include "local.h" (local includes)
        - #include <system.h> (system includes)
        - # include (with space)
        - Handles multi-line includes with backslash continuation
        """
        imports = []

        # Pattern 1: Local includes - #include "file.h"
        local_include_pattern = r'^\s*#\s*include\s+"([^"]+)"'
        for match in re.finditer(local_include_pattern, content, re.MULTILINE):
            header = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=header,
                    line=line_num,
                    import_type="local",
                )
            )

        # Pattern 2: System includes - #include <file.h>
        system_include_pattern = r'^\s*#\s*include\s+<([^>]+)>'
        for match in re.finditer(system_include_pattern, content, re.MULTILINE):
            header = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=header,
                    line=line_num,
                    import_type="system",
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in C/C++ file.

        Entry points:
        - int main()
        - int main(int argc, char** argv)
        - int main(int argc, char* argv[])
        - void main() (non-standard but sometimes used)
        - WinMain for Windows applications
        - DllMain for DLLs
        - Test macros (Google Test, Catch2)
        """
        entry_points = []

        # Pattern 1: Standard main function
        # Matches: int main(), int main(void), int main(int argc, char** argv), etc.
        main_pattern = r'^\s*(?:extern\s+)?(?:int|void)\s+main\s*\('
        for match in re.finditer(main_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_function",
                    line=line_num,
                    name="main",
                )
            )

        # Pattern 2: WinMain (Windows entry point)
        # int WINAPI WinMain(HINSTANCE hInstance, ...)
        winmain_pattern = r'^\s*(?:int|DWORD)\s+(?:WINAPI|APIENTRY)\s+WinMain\s*\('
        for match in re.finditer(winmain_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="winmain_function",
                    line=line_num,
                    name="WinMain",
                )
            )

        # Pattern 3: wWinMain (Unicode Windows entry point)
        wwmain_pattern = r'^\s*(?:int|DWORD)\s+(?:WINAPI|APIENTRY)\s+wWinMain\s*\('
        for match in re.finditer(wwmain_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="winmain_function",
                    line=line_num,
                    name="wWinMain",
                )
            )

        # Pattern 4: DllMain (Windows DLL entry point)
        dllmain_pattern = r'^\s*BOOL\s+(?:WINAPI|APIENTRY)\s+DllMain\s*\('
        for match in re.finditer(dllmain_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="dllmain_function",
                    line=line_num,
                    name="DllMain",
                )
            )

        # Pattern 5: TEST macros (Google Test, Catch2, etc.)
        # TEST(TestSuite, TestName) or TEST_F(Fixture, TestName)
        test_macro_pattern = r'^\s*TEST(?:_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)'
        for match in re.finditer(test_macro_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            suite_name = match.group(1)
            test_name = match.group(2)
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="test",
                    line=line_num,
                    name=f"{suite_name}.{test_name}",
                )
            )

        # Pattern 6: Catch2 TEST_CASE macro
        # TEST_CASE("description", "[tag]")
        catch_test_pattern = r'^\s*TEST_CASE\s*\(\s*"([^"]+)"'
        for match in re.finditer(catch_test_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            test_desc = match.group(1)
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="test",
                    line=line_num,
                    name=test_desc,
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

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        # Classes
        for match in re.finditer(r'\bclass\s+(\w+)', content):
            line = content[:match.start()].count("\n") + 1
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

        # Structs
        for match in re.finditer(r'\bstruct\s+(\w+)\s*\{', content):
            line = content[:match.start()].count("\n") + 1
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

        # Functions (basic pattern)
        for match in re.finditer(r'\b(\w+)\s+(\w+)\s*\([^)]*\)\s*\{', content):
            line = content[:match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="function",
                    name=match.group(2),
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
            # Track function context
            if node.type == "function_definition":
                # Find the function name from the declarator
                declarator = node.child_by_field_name("declarator")
                func_name = self._extract_function_name(declarator, source_bytes) if declarator else None
                if func_name:
                    # Traverse children with this function as context
                    for child in node.children:
                        traverse(child, func_name)
                    return

            # Extract call expressions
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                callee_name = None

                if func_node:
                    # Simple function call: foo()
                    if func_node.type == "identifier":
                        callee_name = self._get_node_text(func_node, source_bytes)

                    # Method call: obj.method() or obj->method()
                    elif func_node.type == "field_expression":
                        field_node = func_node.child_by_field_name("field")
                        if field_node:
                            callee_name = self._get_node_text(field_node, source_bytes)

                    # Scoped call: Namespace::function() or Class::method()
                    elif func_node.type == "qualified_identifier":
                        # Get the last part (the function name)
                        for child in reversed(func_node.children):
                            if child.type == "identifier":
                                callee_name = self._get_node_text(child, source_bytes)
                                break

                    # Template call: func<T>()
                    elif func_node.type == "template_function":
                        name_node = func_node.child_by_field_name("name")
                        if name_node:
                            callee_name = self._get_node_text(name_node, source_bytes)

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
                "if", "else", "for", "while", "do", "switch", "case",
                "return", "break", "continue", "goto", "sizeof", "alignof",
                "typeof", "decltype", "static_cast", "dynamic_cast",
                "const_cast", "reinterpret_cast", "new", "delete",
                "throw", "catch", "try", "class", "struct", "union",
                "enum", "namespace", "template", "typename", "typedef",
                "using", "virtual", "override", "final", "inline",
                "constexpr", "noexcept", "explicit", "static", "extern",
                "register", "volatile", "mutable", "thread_local",
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
    # Classification (enhanced for C/C++)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify C/C++ file into architectural cluster.

        Uses base class heuristics plus C/C++-specific patterns.
        """
        name = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # C/C++-specific patterns that override base classification

        # Third-party/vendor code (check first, before base class)
        if '/third_party/' in path_lower or '/vendor/' in path_lower or '/external/' in path_lower:
            return "infrastructure"

        # Entry points (main files)
        if name in ["main.cpp", "main.c", "main.cc", "main.cxx"]:
            return "entry_points"

        # Check for main function in content
        if re.search(r'^\s*(?:int|void)\s+main\s*\(', content, re.MULTILINE):
            return "entry_points"

        # Headers in public API directories
        if name.endswith(('.h', '.hpp', '.hh', '.hxx')):
            # Public API headers
            if '/include/' in path_lower:
                return "infrastructure"
            # Check if it's a config header
            if 'config' in name or 'version' in name:
                return "config"

        # Config files
        if name in ["config.h", "config.cpp", "settings.h", "settings.cpp"]:
            return "config"

        # Test files
        if any(x in name for x in ['test_', '_test.', 'unittest', 'test.cpp', 'test.c']):
            return "tests"

        # Check for test macros in content
        if re.search(r'^\s*TEST(?:_F|_P|_CASE)?\s*\(', content, re.MULTILINE):
            return "tests"

        # API directories contain core logic
        if '/api/' in path_lower:
            return "core_logic"

        # Source directories often contain core logic
        if '/src/' in path_lower:
            return "core_logic"

        # Use base class classification for remaining cases
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
        """
        Resolve C/C++ #include to file path.

        Handles:
        - "local.h" -> local header (project file)
        - <system.h> -> system header (skipped)

        System headers and standard library are skipped.
        """
        # System includes are skipped (angle brackets were removed before module)
        # but we still check for common system patterns
        system_headers = (
            "iostream", "string", "vector", "map", "set", "algorithm",
            "cstdio", "cstdlib", "cstring", "cmath", "memory", "utility",
            "stdio.h", "stdlib.h", "string.h", "math.h",
        )
        if module in system_headers or module.startswith("sys/"):
            return None

        # Try direct match
        if module in all_files:
            return module

        # Try with common prefixes
        for prefix in ["include/", "src/", ""]:
            candidate = f"{prefix}{module}"
            if candidate in all_files:
                return candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """
        Format C/C++ entry point for display.

        Formats:
        - main_function: "int main() @line"
        - wmain: "int wmain() @line"
        - winmain_function: "WinMain @line"
        - dllmain_function: "DllMain @line"
        - test: "TestSuite.TestName @line"
        """
        if ep.type == "main_function":
            return f"  {ep.file}:int main() @{ep.line}"
        elif ep.type == "wmain":
            return f"  {ep.file}:int wmain() @{ep.line}"
        elif ep.type == "winmain_function":
            return f"  {ep.file}:{ep.name}() @{ep.line}"
        elif ep.type == "dllmain_function":
            return f"  {ep.file}:DllMain() @{ep.line}"
        elif ep.type == "test":
            return f"  {ep.file}:TEST({ep.name}) @{ep.line}"
        else:
            return super().format_entry_point(ep)
