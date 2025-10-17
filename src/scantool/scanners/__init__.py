"""
Scanner plugin system with auto-discovery.

To add a new language scanner:
1. Create a new file in this directory (e.g., python_scanner.py)
2. Define a class that inherits from BaseScanner
3. Implement get_extensions(), get_language_name(), and scan()
4. That's it! The scanner is automatically discovered and registered
"""

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Optional

from .base import BaseScanner, StructureNode

__all__ = ["BaseScanner", "StructureNode", "ScannerRegistry"]


class ScannerRegistry:
    """Auto-discovering registry for all file type scanners."""

    def __init__(self):
        self._scanners: dict[str, type[BaseScanner]] = {}
        self._discover_scanners()

    def _discover_scanners(self):
        """Automatically discover all scanner plugins in this directory."""
        # Get the directory where this __init__.py is located
        package_dir = Path(__file__).parent

        # Import all Python files in this directory (except __init__.py and base.py)
        for file_path in package_dir.glob("*.py"):
            if file_path.name in ("__init__.py", "base.py"):
                continue

            # Import the module
            module_name = f"scantool.scanners.{file_path.stem}"
            try:
                module = importlib.import_module(module_name)

                # Find all BaseScanner subclasses in the module
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseScanner) and
                        obj is not BaseScanner and
                        not inspect.isabstract(obj)):
                        self.register_scanner(obj)

            except Exception as e:
                # Skip modules that fail to import
                print(f"Warning: Failed to import scanner module {module_name}: {e}")
                continue

    def register_scanner(self, scanner_class: type[BaseScanner]):
        """Register a scanner class for its supported extensions."""
        for ext in scanner_class.get_extensions():
            ext_lower = ext.lower()

            # If extension already registered, use higher priority scanner
            if ext_lower in self._scanners:
                existing = self._scanners[ext_lower]
                if scanner_class.get_priority() <= existing.get_priority():
                    continue

            self._scanners[ext_lower] = scanner_class

    def get_scanner(self, file_extension: str) -> Optional[type[BaseScanner]]:
        """Get the appropriate scanner class for a file extension."""
        return self._scanners.get(file_extension.lower())

    def get_supported_extensions(self) -> list[str]:
        """Get list of all supported file extensions."""
        return sorted(self._scanners.keys())

    def get_scanner_info(self) -> dict[str, str]:
        """Get mapping of extensions to language names."""
        return {
            ext: scanner.get_language_name()
            for ext, scanner in self._scanners.items()
        }


# Global registry instance
_registry = None


def get_registry() -> ScannerRegistry:
    """Get the global scanner registry (singleton)."""
    global _registry
    if _registry is None:
        _registry = ScannerRegistry()
    return _registry
