"""Python code analyzer for extracting imports, entry points, and structure."""

import re
from typing import Optional
from pathlib import Path

try:
    import tree_sitter_python
    from tree_sitter import Language, Parser
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo, DefinitionInfo, CallInfo


class PythonAnalyzer(BaseAnalyzer):
    """Analyzer for Python source files (.py, .pyw)."""

    def __init__(self):
        """Initialize with tree-sitter parser if available."""
        super().__init__()
        self.parser = None
        if HAS_TREE_SITTER:
            self.parser = Parser()
            self.parser.language = Language(tree_sitter_python.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        """Python file extensions."""
        return [".py", ".pyw"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "Python"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip Python files that should not be analyzed.

        Matches PythonScanner.should_skip() logic:
        - Skip compiled Python files (.pyc, .pyo, .pyd)
        - __pycache__ directories are already filtered by COMMON_SKIP_DIRS
        """
        filename = Path(file_path).name

        # Skip compiled Python files
        if filename.endswith(('.pyc', '.pyo', '.pyd')):
            return False

        return True

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract import statements from Python file.

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

            # Parse imported items (handle multi-line imports, aliases)
            imported_names = []
            # Remove parentheses if present
            imported_items_str = imported_items_str.strip('()')
            for item in imported_items_str.split(','):
                item = item.strip()
                if ' as ' in item:
                    name, alias = item.split(' as ')
                    imported_names.append(name.strip())
                else:
                    imported_names.append(item)

            # Determine if relative import
            is_relative = module.startswith('.')
            import_type = "relative" if is_relative else "from_import"

            # Resolve relative imports to absolute paths
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
        """
        Find entry points in Python file.

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
                # Parse list of exported names
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
                        line=1,  # General indicator
                    )
                )

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify Python file into architectural cluster.

        Enhanced classification with Python-specific patterns.
        """
        # Use base implementation first
        cluster = super().classify_file(file_path, content)

        # If not already classified, check for Python-specific patterns
        if cluster == "other":
            # Check for common Python patterns in content
            if "if __name__ ==" in content or "def main(" in content:
                return "entry_points"

            # Check for test files by content (pytest, unittest)
            if any(
                pattern in content
                for pattern in ["import pytest", "import unittest", "from unittest"]
            ):
                return "tests"

            # Check for common utility patterns
            if any(
                pattern in content
                for pattern in ["def helper_", "def util_", "class Helper", "class Util"]
            ):
                return "utilities"

        return cluster

    # ===================================================================
    # LAYER 2: Structure-level analysis
    # ===================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """
        Extract function/class definitions using tree-sitter.

        Falls back to regex if tree-sitter unavailable.
        """
        if not self.parser:
            # Fallback to regex-based extraction
            return self._extract_definitions_regex(file_path, content)

        try:
            source_bytes = content.encode("utf-8")
            tree = self.parser.parse(source_bytes)
            return self._extract_definitions_tree_sitter(
                file_path, tree.root_node, source_bytes
            )
        except Exception:
            # Fallback to regex on parse error
            return self._extract_definitions_regex(file_path, content)

    def _extract_definitions_tree_sitter(
        self, file_path: str, root, source_bytes: bytes
    ) -> list[DefinitionInfo]:
        """Extract definitions using tree-sitter AST."""
        definitions = []

        def traverse(node, parent_class=None):
            # Class definitions
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = source_bytes[name_node.start_byte : name_node.end_byte].decode(
                        "utf-8"
                    )
                    line = node.start_point[0] + 1

                    # Get signature (base classes)
                    superclasses = []
                    for child in node.children:
                        if child.type == "argument_list":
                            for arg in child.children:
                                if arg.type == "identifier":
                                    superclasses.append(
                                        source_bytes[arg.start_byte : arg.end_byte].decode(
                                            "utf-8"
                                        )
                                    )
                    signature = (
                        f"({', '.join(superclasses)})" if superclasses else None
                    )

                    definitions.append(
                        DefinitionInfo(
                            file=file_path,
                            type="class",
                            name=name,
                            line=line,
                            signature=signature,
                            parent=None,
                        )
                    )

                    # Traverse children for methods
                    for child in node.children:
                        traverse(child, parent_class=name)

            # Function/method definitions
            elif node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = source_bytes[name_node.start_byte : name_node.end_byte].decode(
                        "utf-8"
                    )
                    line = node.start_point[0] + 1

                    # Get signature (parameters)
                    params_node = node.child_by_field_name("parameters")
                    signature = None
                    if params_node:
                        signature = source_bytes[
                            params_node.start_byte : params_node.end_byte
                        ].decode("utf-8")

                    func_type = "method" if parent_class else "function"

                    definitions.append(
                        DefinitionInfo(
                            file=file_path,
                            type=func_type,
                            name=name,
                            line=line,
                            signature=signature,
                            parent=parent_class,
                        )
                    )

            # Continue traversing
            else:
                for child in node.children:
                    traverse(child, parent_class)

        traverse(root)
        return definitions

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        # Classes
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

        # Functions
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
        """
        Extract function/method calls using tree-sitter.

        Falls back to regex if tree-sitter unavailable.
        """
        if not self.parser:
            # Fallback to regex-based extraction
            return self._extract_calls_regex(file_path, content, definitions)

        try:
            source_bytes = content.encode("utf-8")
            tree = self.parser.parse(source_bytes)
            return self._extract_calls_tree_sitter(
                file_path, tree.root_node, source_bytes, definitions
            )
        except Exception:
            # Fallback to regex on parse error
            return self._extract_calls_regex(file_path, content, definitions)

    def _extract_calls_tree_sitter(
        self, file_path: str, root, source_bytes: bytes, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Extract calls using tree-sitter AST."""
        calls = []
        current_function = None

        def traverse(node, context_func=None):
            nonlocal current_function

            # Track which function we're inside
            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    current_function = source_bytes[
                        name_node.start_byte : name_node.end_byte
                    ].decode("utf-8")

                # Traverse children
                for child in node.children:
                    traverse(child, current_function)

                current_function = context_func  # Restore context

            # Call expressions
            elif node.type == "call":
                # Get function being called
                func_node = node.child_by_field_name("function")
                if func_node:
                    # Handle simple calls: foo()
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
                                is_cross_file=False,  # Will determine later
                            )
                        )

                    # Handle attribute calls: obj.method()
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

                # Continue traversing
                for child in node.children:
                    traverse(child, context_func)

            # Continue traversing
            else:
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

        # Find all function calls: name(
        for match in re.finditer(r"\b(\w+)\s*\(", content):
            callee_name = match.group(1)
            line = content[: match.start()].count("\n") + 1

            # Skip Python keywords
            if callee_name in [
                "if",
                "for",
                "while",
                "def",
                "class",
                "return",
                "print",
            ]:
                continue

            calls.append(
                CallInfo(
                    caller_file=file_path,
                    caller_name=None,  # Cannot determine with regex
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
