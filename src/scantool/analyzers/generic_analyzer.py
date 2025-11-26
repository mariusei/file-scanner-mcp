"""Generic fallback analyzer for unsupported file types."""

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class GenericAnalyzer(BaseAnalyzer):
    """
    Fallback analyzer for file types without specific language support.

    Returns empty results for all analysis methods. Used when no language-specific
    analyzer is available for a file extension.
    """

    @classmethod
    def get_extensions(cls) -> list[str]:
        """
        Return empty list - this analyzer is used as fallback, not registered.

        The registry will create instances of this class when no other analyzer
        matches a file extension.
        """
        return []

    @classmethod
    def get_language_name(cls) -> str:
        """Return generic language name."""
        return "Generic"

    @classmethod
    def get_priority(cls) -> int:
        """Lowest priority - only used when no other analyzer available."""
        return -1

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """No import extraction for generic files."""
        return []

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """No entry point detection for generic files."""
        return []

    def should_analyze(self, file_path: str) -> bool:
        """Generic files can be analyzed (even though results are empty)."""
        return True
