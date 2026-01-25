"""Generic fallback language handler for unsupported file types.

This module provides a fallback language handler for files without specific
language support. It returns empty results for all analysis methods.

IMPORTANT: This class is NOT auto-registered in the language registry because
get_extensions() returns an empty list. It should be instantiated directly
by code_map.py as a fallback when no other language handler is available.
"""

from typing import Optional

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class GenericLanguage(BaseLanguage):
    """Fallback language handler for file types without specific language support.

    Returns empty results for all analysis methods. Used when no language-specific
    handler is available for a file extension.

    This class is intentionally NOT registered in the language registry
    (get_extensions returns []) and should be used directly as a fallback.
    """

    def __init__(self, **kwargs):
        """Initialize generic language handler."""
        super().__init__(**kwargs)

    # ===========================================================================
    # Metadata
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        """Return empty list - this handler is used as fallback, not registered.

        The registry will NOT auto-register this class because it returns no
        extensions. It should be instantiated directly when needed as a fallback.
        """
        return []

    @classmethod
    def get_language_name(cls) -> str:
        """Return generic language name."""
        return "Generic"

    @classmethod
    def get_priority(cls) -> int:
        """Lowest priority - only used when no other handler available."""
        return -1

    # ===========================================================================
    # Structure Scanning
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """No structure scanning for generic files.

        Generic files don't have a known structure that can be parsed.

        Args:
            source_code: Raw file content as bytes (ignored)

        Returns:
            None - generic files have no structure scanning
        """
        return None

    # ===========================================================================
    # Semantic Analysis - Layer 1
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """No import extraction for generic files.

        Args:
            file_path: Relative path to the file (ignored)
            content: File content as string (ignored)

        Returns:
            Empty list
        """
        return []

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """No entry point detection for generic files.

        Args:
            file_path: Relative path to the file (ignored)
            content: File content as string (ignored)

        Returns:
            Empty list
        """
        return []

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """No definition extraction for generic files.

        Args:
            file_path: Relative path to the file (ignored)
            content: File content as string (ignored)

        Returns:
            Empty list
        """
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """No call extraction for generic files.

        Args:
            file_path: Relative path to the file (ignored)
            content: File content as string (ignored)
            definitions: List of definitions (ignored)

        Returns:
            Empty list
        """
        return []

    # ===========================================================================
    # Analysis helpers
    # ===========================================================================

    def should_analyze(self, file_path: str) -> bool:
        """Generic files can be analyzed (even though results are empty).

        This returns True to allow the file to go through the analysis pipeline.
        The analysis will simply return empty results.

        Args:
            file_path: Relative path to the file

        Returns:
            True (always)
        """
        return True

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
        """No import resolution for generic files.

        Args:
            module: Module name to resolve (ignored)
            source_file: Path of file doing the import (ignored)
            all_files: List of all files in project (ignored)
            definitions_map: Map of definitions to file paths (ignored)

        Returns:
            None
        """
        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Use default formatting for generic files.

        Args:
            ep: EntryPointInfo object to format

        Returns:
            Formatted string using base class implementation
        """
        return super().format_entry_point(ep)
