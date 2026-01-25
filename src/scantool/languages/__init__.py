"""Unified language system for scantool.

This package provides a single interface for language support, combining
scanner functionality (structure extraction) and analyzer functionality
(semantic analysis) into one class per language.

Usage:
    from scantool.languages import get_language, LanguageRegistry

    # Get language handler by extension
    lang = get_language('.py')
    structures = lang.scan(source_code)
    imports = lang.extract_imports(file_path, content)

    # Get all registered languages
    registry = LanguageRegistry()
    for ext, lang_cls in registry.items():
        print(f"{ext}: {lang_cls.get_language_name()}")

Models are available from the models submodule:
    from scantool.languages.models import (
        StructureNode,
        ImportInfo,
        EntryPointInfo,
        DefinitionInfo,
        CallInfo,
    )
"""

import importlib
import pkgutil
from typing import Dict, Type, Optional

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
    CallGraphNode,
    FileNode,
    CodeMapResult,
)

__all__ = [
    # Core classes
    "BaseLanguage",
    "LanguageRegistry",
    "get_language",
    "get_registry",
    # Models
    "StructureNode",
    "ImportInfo",
    "EntryPointInfo",
    "DefinitionInfo",
    "CallInfo",
    "CallGraphNode",
    "FileNode",
    "CodeMapResult",
]


class LanguageRegistry:
    """Registry of all language handlers.

    Provides lookup by file extension and auto-discovers language
    implementations in this package.
    """

    _instance: Optional["LanguageRegistry"] = None
    _languages: Dict[str, Type[BaseLanguage]]
    _instances: Dict[str, BaseLanguage]

    def __new__(cls):
        """Singleton pattern for registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._languages = {}
            cls._instance._instances = {}
            cls._instance._discover_languages()
        return cls._instance

    def _discover_languages(self):
        """Auto-discover language implementations in this package."""
        # Import all modules in this package
        package_path = __path__
        for importer, modname, ispkg in pkgutil.iter_modules(package_path):
            if modname in ("base", "models", "__init__"):
                continue
            try:
                module = importlib.import_module(f".{modname}", __package__)
                # Find BaseLanguage subclasses
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseLanguage)
                        and attr is not BaseLanguage
                    ):
                        self.register(attr)
            except ImportError:
                pass  # Skip modules that fail to import

    def register(self, language_cls: Type[BaseLanguage]):
        """Register a language handler.

        Args:
            language_cls: BaseLanguage subclass to register
        """
        for ext in language_cls.get_extensions():
            ext_lower = ext.lower()
            # Check priority if extension already registered
            if ext_lower in self._languages:
                existing = self._languages[ext_lower]
                if language_cls.get_priority() <= existing.get_priority():
                    continue
            self._languages[ext_lower] = language_cls

    def get(self, extension: str) -> Optional[BaseLanguage]:
        """Get language handler instance for extension.

        Args:
            extension: File extension (e.g., '.py', '.ts')

        Returns:
            Language handler instance, or None if not found
        """
        ext_lower = extension.lower()
        if ext_lower not in self._languages:
            return None

        # Cache instances
        if ext_lower not in self._instances:
            self._instances[ext_lower] = self._languages[ext_lower]()

        return self._instances[ext_lower]

    def get_class(self, extension: str) -> Optional[Type[BaseLanguage]]:
        """Get language handler class for extension.

        Args:
            extension: File extension

        Returns:
            Language handler class, or None if not found
        """
        return self._languages.get(extension.lower())

    def items(self):
        """Iterate over (extension, class) pairs."""
        return self._languages.items()

    def extensions(self):
        """Get all registered extensions."""
        return self._languages.keys()

    def languages(self):
        """Get all registered language classes."""
        return set(self._languages.values())

    # Backward compatibility methods (match old ScannerRegistry/AnalyzerRegistry interface)

    def get_scanner(self, extension: str) -> Optional[Type[BaseLanguage]]:
        """Get language class for extension (backward compatible with ScannerRegistry)."""
        return self.get_class(extension)

    def get_analyzer(self, extension: str) -> Optional[Type[BaseLanguage]]:
        """Get language class for extension (backward compatible with AnalyzerRegistry)."""
        return self.get_class(extension)

    def get_supported_extensions(self) -> list[str]:
        """Get sorted list of all supported extensions."""
        return sorted(self._languages.keys())

    def get_scanner_info(self) -> dict[str, str]:
        """Get mapping of extensions to language names."""
        return {ext: cls.get_language_name() for ext, cls in self._languages.items()}

    def get_analyzer_info(self) -> dict[str, str]:
        """Get mapping of extensions to language names."""
        return self.get_scanner_info()


# Module-level convenience functions

_registry: Optional[LanguageRegistry] = None


def get_registry() -> LanguageRegistry:
    """Get the global language registry."""
    global _registry
    if _registry is None:
        _registry = LanguageRegistry()
    return _registry


def get_language(extension: str) -> Optional[BaseLanguage]:
    """Get language handler instance for extension.

    Args:
        extension: File extension (e.g., '.py', '.ts')

    Returns:
        Language handler instance, or None if not found
    """
    return get_registry().get(extension)
