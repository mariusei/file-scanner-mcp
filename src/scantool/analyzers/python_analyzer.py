"""Python code analyzer for extracting imports, entry points, and structure."""

import re
from typing import Optional
from pathlib import Path

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class PythonAnalyzer(BaseAnalyzer):
    """Analyzer for Python source files (.py, .pyw)."""

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
        """Skip empty __init__.py files and __pycache__."""
        if "__pycache__" in file_path:
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
