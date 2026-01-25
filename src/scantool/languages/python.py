"""Python language support - unified scanner and analyzer.

This module combines PythonScanner and PythonAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class PythonLanguage(BaseLanguage):
    """Unified language handler for Python files (.py, .pyw).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract classes, functions, methods with signatures and metadata
    - extract_imports(): Find import statements
    - find_entry_points(): Find main functions, __main__ blocks, app instances
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Find function/method calls
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_python.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".py", ".pyw"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Python"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip compiled Python files."""
        if filename.endswith(('.pyc', '.pyo', '.pyd')):
            return True
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Skip compiled Python files."""
        filename = Path(file_path).name
        if filename.endswith(('.pyc', '.pyo', '.pyd')):
            return False
        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value Python files for inventory listing.

        Low-value files (unless central):
        - Empty or near-empty __init__.py files
        - conftest.py (pytest fixtures, usually boilerplate)
        - setup.py/setup.cfg (unless large)
        """
        filename = Path(file_path).name

        if filename == "__init__.py" and size < 100:
            return True

        if filename == "conftest.py" and size < 200:
            return True

        if filename in ("setup.py", "setup.cfg") and size < 100:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from PythonScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Python source code and extract structure with metadata."""
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
            if node.type == "class_definition":
                class_node = self._extract_class(node, source_code, root)
                parent_structures.append(class_node)

                # Traverse children for methods
                for child in node.children:
                    traverse(child, class_node.children)

            # Functions/Methods
            elif node.type == "function_definition":
                func_node = self._extract_function(node, source_code, root)
                parent_structures.append(func_node)

            # Imports
            elif node.type in ("import_statement", "import_from_statement"):
                self._handle_import(node, parent_structures)

            else:
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_class(self, node: Node, source_code: bytes, root: Node) -> StructureNode:
        """Extract class with full metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        decorators = self._extract_decorators(node, source_code)
        superclasses = self._extract_superclasses(node, source_code)
        signature = f"({', '.join(superclasses)})" if superclasses else None
        docstring = self._extract_docstring(node, source_code)
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
            children=[]
        )

    def _extract_function(self, node: Node, source_code: bytes, root: Node) -> StructureNode:
        """Extract function/method with signature and metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        is_method = any(p.type == "class_definition" for p in self._get_ancestors(root, node))
        type_name = "method" if is_method else "function"

        signature = self._extract_signature(node, source_code)
        decorators = self._extract_decorators(node, source_code)
        docstring = self._extract_docstring(node, source_code)
        modifiers = self._extract_modifiers(node, decorators)
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type=type_name,
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

    def _extract_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract function signature with parameters and return type."""
        parts = []

        params_node = node.child_by_field_name("parameters")
        if params_node:
            parts.append(self._get_node_text(params_node, source_code))

        return_type_node = node.child_by_field_name("return_type")
        if return_type_node:
            return_text = self._get_node_text(return_type_node, source_code).strip()
            if not return_text.startswith("->"):
                return_text = f"-> {return_text}"
            elif not return_text.startswith("-> "):
                return_text = return_text.replace("->", "-> ", 1)
            parts.append(f" {return_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_decorators(self, node: Node, source_code: bytes) -> list[str]:
        """Extract decorators from a function/class definition."""
        decorators = []
        prev = node.prev_sibling

        while prev and prev.type == "decorator":
            dec_text = self._get_node_text(prev, source_code).strip()
            decorators.insert(0, dec_text)
            prev = prev.prev_sibling

        return decorators

    def _extract_docstring(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract first line of docstring."""
        body = node.child_by_field_name("body")
        if not body or len(body.children) == 0:
            return None

        first_stmt = body.children[0]
        if first_stmt.type == "expression_statement":
            for child in first_stmt.children:
                if child.type == "string":
                    docstring = self._get_node_text(child, source_code)
                    docstring = docstring.strip('"""').strip("'''").strip('"').strip("'")
                    lines = [line.strip() for line in docstring.split('\n')]
                    for line in lines:
                        if line:
                            return line
                    return None

        return None

    def _extract_superclasses(self, node: Node, source_code: bytes) -> list[str]:
        """Extract base class names."""
        superclasses = []
        argument_list = node.child_by_field_name("superclasses")

        if argument_list:
            for child in argument_list.children:
                if child.type in ("identifier", "attribute"):
                    superclasses.append(self._get_node_text(child, source_code))

        return superclasses

    def _extract_modifiers(self, node: Node, decorators: list[str]) -> list[str]:
        """Extract modifiers like async, static, classmethod."""
        modifiers = []

        for child in node.children:
            if child.type == "async":
                modifiers.append("async")
                break

        for dec in decorators:
            if "@staticmethod" in dec:
                modifiers.append("static")
            elif "@classmethod" in dec:
                modifiers.append("classmethod")
            elif "@property" in dec:
                modifiers.append("property")
            elif "@abstractmethod" in dec:
                modifiers.append("abstract")

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

        for match in re.finditer(r'^class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        for match in re.finditer(r'^(async\s+)?def\s+(\w+)\s*\((.*?)\)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            is_async = match.group(1) is not None
            name = match.group(2)
            params = match.group(3)
            modifiers = ["async"] if is_async else []

            structures.append(StructureNode(
                type="function",
                name=name + " (fallback)",
                start_line=line_num,
                end_line=line_num,
                signature=f"({params})",
                modifiers=modifiers
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from PythonAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract import statements from Python file.

        Patterns supported:
        - from x.y import z
        - from x.y import z as w
        - from x.y import (a, b, c)
        - import x.y.z
        - import x.y as z
        - from . import x (relative import)
        - from ..utils import y (relative import)
        """
        imports = []

        # Pattern 1: from X import Y
        from_import_pattern = r'^\s*from\s+([\w.]+)\s+import\s+(.+?)(?:\s+#.*)?$'
        for match in re.finditer(from_import_pattern, content, re.MULTILINE):
            module = match.group(1)
            imported_items_str = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            imported_names = []
            imported_items_str = imported_items_str.strip('()')
            for item in imported_items_str.split(','):
                item = item.strip()
                if ' as ' in item:
                    name, alias = item.split(' as ')
                    imported_names.append(name.strip())
                else:
                    imported_names.append(item)

            is_relative = module.startswith('.')
            import_type = "relative" if is_relative else "from_import"

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
                    imported_names=imported_names,
                )
            )

        # Pattern 2: import X
        import_pattern = r'^\s*import\s+([\w.]+)(?:\s+as\s+\w+)?(?:\s+#.*)?$'
        for match in re.finditer(import_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type="import",
                    imported_names=[],
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in Python file.

        Entry points:
        - def main() functions
        - if __name__ == "__main__" blocks
        - Flask/FastAPI/FastMCP app instances
        - Exports in __init__.py files
        """
        entry_points = []

        # Pattern 1: def main()
        main_func_pattern = r'^def\s+main\s*\('
        for match in re.finditer(main_func_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_function",
                    name="main",
                    line=line_num,
                )
            )

        # Pattern 2: if __name__ == "__main__"
        if_main_pattern = r'if\s+__name__\s*==\s*["\']__main__["\']'
        for match in re.finditer(if_main_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path, type="if_main", name="__main__", line=line_num
                )
            )

        # Pattern 3: Flask/FastAPI/FastMCP app instances
        app_pattern = r'(app|server|mcp)\s*=\s*(Flask|FastAPI|FastMCP|Starlette)\('
        for match in re.finditer(app_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            var_name = match.group(1)
            framework = match.group(2)
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="app_instance",
                    name=var_name,
                    line=line_num,
                    framework=framework,
                )
            )

        # Pattern 4: __init__.py exports
        if file_path.endswith("__init__.py"):
            # Look for __all__ = [...]
            all_pattern = r'__all__\s*=\s*\[(.*?)\]'
            for match in re.finditer(all_pattern, content, re.MULTILINE | re.DOTALL):
                line_num = content[:match.start()].count('\n') + 1
                exports_str = match.group(1)
                exports = [
                    name.strip().strip('"').strip("'")
                    for name in exports_str.split(',')
                    if name.strip()
                ]
                if exports:
                    entry_points.append(
                        EntryPointInfo(
                            file=file_path,
                            type="export",
                            name=f"__all__ ({len(exports)} items)",
                            line=line_num,
                        )
                    )

            # Look for from .X import Y (re-exports)
            reexport_pattern = r'^from\s+\.\S+\s+import\s+(\w+)'
            reexports = re.findall(reexport_pattern, content, re.MULTILINE)
            if reexports:
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="export",
                        name=f"re-exports ({len(reexports)} items)",
                        line=1,
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

        for match in re.finditer(r"^class\s+(\w+)", content, re.MULTILINE):
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

        for match in re.finditer(r"^def\s+(\w+)\s*\(", content, re.MULTILINE):
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

            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    current_function = source_bytes[
                        name_node.start_byte : name_node.end_byte
                    ].decode("utf-8")

                for child in node.children:
                    traverse(child, current_function)

                current_function = context_func
                return

            if node.type == "call":
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

                    elif func_node.type == "attribute":
                        attr_node = func_node.child_by_field_name("attribute")
                        if attr_node:
                            callee_name = source_bytes[
                                attr_node.start_byte : attr_node.end_byte
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

            if callee_name in [
                "if", "for", "while", "def", "class", "return", "print",
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
    # Classification (enhanced for Python)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify Python file into architectural cluster."""
        cluster = super().classify_file(file_path, content)

        if cluster == "other":
            if "if __name__ ==" in content or "def main(" in content:
                return "entry_points"

            if any(
                pattern in content
                for pattern in ["import pytest", "import unittest", "from unittest"]
            ):
                return "tests"

            if any(
                pattern in content
                for pattern in ["def helper_", "def util_", "class Helper", "class Util"]
            ):
                return "utilities"

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
        """Resolve Python import module to file path.

        Handles:
        - Absolute imports: myapp.utils -> myapp/utils.py
        - Relative imports (already resolved): foo/bar -> foo/bar.py
        - Package imports: myapp.utils -> myapp/utils/__init__.py
        """
        if "/" in module:
            candidate = f"{module}.py"
            if candidate in all_files:
                return candidate
            candidate_init = f"{module}/__init__.py"
            if candidate_init in all_files:
                return candidate_init
            return None

        parts = module.split(".")

        candidates = [
            "/".join(parts) + ".py",
            "/".join(parts[1:]) + ".py",
            "/".join(parts) + "/__init__.py",
        ]

        if len(parts) > 0:
            candidates.append("src/" + "/".join(parts) + ".py")
            candidates.append("src/" + "/".join(parts) + "/__init__.py")

        for candidate in candidates:
            if candidate in all_files:
                return candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format Python entry point for display."""
        if ep.type == "main_function":
            return f"  {ep.file}:main() @{ep.line}"
        elif ep.type == "if_main":
            return f"  {ep.file}:if __name__ @{ep.line}"
        elif ep.type == "app_instance":
            return f"  {ep.file}:{ep.framework} {ep.name} @{ep.line}"
        elif ep.type == "export":
            return f"  {ep.file}:{ep.name}"
        else:
            return super().format_entry_point(ep)
