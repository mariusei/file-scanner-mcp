"""
Analyzer plugin system with auto-discovery.

To add a new language analyzer:
1. Create a new file in this directory (e.g., python_analyzer.py)
2. Define a class that inherits from BaseAnalyzer
3. Implement get_extensions(), get_language_name(), extract_imports(), and find_entry_points()
4. Optionally implement Layer 2 methods: extract_definitions(), extract_calls()
5. That's it! The analyzer is automatically discovered and registered
"""

import importlib
import inspect
from pathlib import Path
from typing import Optional

from .base import BaseAnalyzer
from .models import (
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
    CallGraphNode,
    FileNode,
    CodeMapResult,
)

__all__ = [
    "BaseAnalyzer",
    "AnalyzerRegistry",
    "ImportInfo",
    "EntryPointInfo",
    "DefinitionInfo",
    "CallInfo",
    "CallGraphNode",
    "FileNode",
    "CodeMapResult",
]


class AnalyzerRegistry:
    """Auto-discovering registry for all language analyzers."""

    def __init__(self):
        self._analyzers: dict[str, type[BaseAnalyzer]] = {}
        self._discover_analyzers()

    def _discover_analyzers(self):
        """Automatically discover all analyzer plugins in this directory."""
        # Get the directory where this __init__.py is located
        package_dir = Path(__file__).parent

        # Import all Python files in this directory (except __init__.py, base.py, models.py)
        for file_path in package_dir.glob("*.py"):
            if file_path.name in ("__init__.py", "base.py", "models.py"):
                continue

            # Import the module using the package name from __name__
            module_name = f"{__name__}.{file_path.stem}"
            try:
                module = importlib.import_module(module_name)

                # Find all BaseAnalyzer subclasses in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, BaseAnalyzer)
                        and obj is not BaseAnalyzer
                        and not inspect.isabstract(obj)
                    ):
                        self.register_analyzer(obj)

            except Exception as e:
                # Skip modules that fail to import
                print(f"Warning: Failed to import analyzer module {module_name}: {e}")
                continue

    def register_analyzer(self, analyzer_class: type[BaseAnalyzer]):
        """Register an analyzer class for its supported extensions."""
        for ext in analyzer_class.get_extensions():
            ext_lower = ext.lower()

            # If extension already registered, use higher priority analyzer
            if ext_lower in self._analyzers:
                existing = self._analyzers[ext_lower]
                if analyzer_class.get_priority() <= existing.get_priority():
                    continue

            self._analyzers[ext_lower] = analyzer_class

    def get_analyzer(self, file_extension: str) -> Optional[type[BaseAnalyzer]]:
        """Get the appropriate analyzer class for a file extension."""
        return self._analyzers.get(file_extension.lower())

    def get_supported_extensions(self) -> list[str]:
        """Get list of all supported file extensions."""
        return sorted(self._analyzers.keys())

    def get_analyzer_info(self) -> dict[str, str]:
        """Get mapping of extensions to language names."""
        return {
            ext: analyzer.get_language_name() for ext, analyzer in self._analyzers.items()
        }


# Global registry instance
_registry = None


def get_registry() -> AnalyzerRegistry:
    """Get the global analyzer registry (singleton)."""
    global _registry
    if _registry is None:
        _registry = AnalyzerRegistry()
    return _registry
