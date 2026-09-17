"""Config language support - analyzer for configuration files.

This module provides ConfigLanguage for analyzing configuration files
(.ini). Since config files don't have traditional code
structure, scan() returns an empty list.

.json and .toml have their own dedicated handlers (languages/json.py,
languages/toml.py) with real structure extraction; this module no longer
claims those extensions.

Key functionality:
- extract_imports(): Extract file path references from config files
- find_entry_points(): Find project configs, scripts sections, etc.
- classify_file(): All config files go to "config" cluster
"""

import re
from pathlib import Path

from .base import BaseLanguage, parent_dir
from .models import (
    CallInfo,
    DefinitionInfo,
    EntryPointInfo,
    ImportInfo,
    StructureNode,
)


class ConfigLanguage(BaseLanguage):
    """Language handler for configuration files (.ini).

    Config files don't have traditional code structure (classes, functions),
    so scan() returns an empty list. The primary value is in:
    - extract_imports(): Find file path references
    - find_entry_points(): Find project configs and scripts
    """

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        """Configuration file extensions."""
        return [".ini"]

    @classmethod
    def get_language_name(cls) -> str:
        """Language name."""
        return "Config"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    # ===========================================================================
    # Skip Logic
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip config files that should not be scanned."""
        filename_lower = filename.lower()

        # Skip lock files
        if filename_lower in (
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "cargo.lock",
        ):
            return True

        # Skip if ends with .lock
        if filename_lower.endswith(".lock"):
            return True

        # Skip minified
        return ".min." in filename_lower

    def should_analyze(self, file_path: str) -> bool:
        """Skip config files that should not be analyzed."""
        filename = Path(file_path).name.lower()

        # Skip lock files
        if filename in (
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "cargo.lock",
        ):
            return False

        # Skip if ends with .lock
        if filename.endswith(".lock"):
            return False

        # Skip minified
        return ".min." not in filename

    # ===========================================================================
    # Structure Scanning
    # ===========================================================================

    def scan(self, source_code: bytes) -> list[StructureNode] | None:
        """Scan config file - returns empty list as configs don't have code structure."""
        # Config files don't have traditional code structure (classes, functions)
        # Return empty list rather than None to indicate successful parse
        return []

    # ===========================================================================
    # Semantic Analysis - Layer 1
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract file path references from config files.

        Handles:
        - INI: file path values
        - File path patterns in string values

        Does NOT extract:
        - Package names (npm, cargo, pip - these are registry names, not file imports)
        """
        imports: list[ImportInfo] = []
        filename = Path(file_path).name.lower()

        if filename.endswith(".ini"):
            imports.extend(self._extract_ini_imports(file_path, content))

        # Generic file path pattern extraction (all config types)
        imports.extend(self._extract_path_patterns(file_path, content))

        return imports

    def _extract_ini_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from INI config files."""
        imports: list[ImportInfo] = []

        # INI files may have file path values
        # key = /path/to/file or key = ./relative/path
        ini_path_pattern = r'^\s*[\w_-]+\s*=\s*(["\']?)([./][^\s"\']+\.[a-zA-Z0-9]+)\1'
        for match in re.finditer(ini_path_pattern, content, re.MULTILINE):
            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=match.group(2),
                    line=content[: match.start()].count("\n") + 1,
                    import_type="config_value",
                )
            )

        return imports

    def _extract_path_patterns(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract generic file path patterns from config files.

        Conservative patterns:
        - Relative paths: ./file.ext, ../file.ext
        - Quoted paths with extensions
        - Avoid matching URLs, version numbers, or package names
        """
        imports: list[ImportInfo] = []

        # Pattern 1: Relative paths with common extensions (in quotes)
        # Matches: "./config.json", "../utils/helper.ts", "./templates/base.html", etc.
        quoted_path_pattern = r'["\'](\./(?:[^/"\s]+/)*[^/"\s]+\.[a-zA-Z0-9]+|\.\./(?:[^/"\s]+/)*[^/"\s]+\.[a-zA-Z0-9]+)["\']'
        for match in re.finditer(quoted_path_pattern, content):
            path = match.group(1)
            # Skip if looks like URL
            if "://" not in path:
                imports.append(
                    ImportInfo(
                        source_file=file_path,
                        target_module=path,
                        line=content[: match.start()].count("\n") + 1,
                        import_type="path_reference",
                    )
                )

        # Pattern 2: Unquoted relative paths on their own line (YAML-style)
        # Matches: "  - ./file.ext" or "key: ./file.ext"
        unquoted_path_pattern = (
            r"(?:^|\s)(\./[^\s:]+\.[a-zA-Z0-9]+|\.\./(?:[^/\s]+/)*[^/\s]+\.[a-zA-Z0-9]+)(?:\s|$)"
        )
        for match in re.finditer(unquoted_path_pattern, content, re.MULTILINE):
            path = match.group(1)
            if "://" not in path:
                imports.append(
                    ImportInfo(
                        source_file=file_path,
                        target_module=path,
                        line=content[: match.start()].count("\n") + 1,
                        import_type="path_reference",
                    )
                )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """An .ini file names no entry points; project configs (package.json,
        pyproject.toml, docker-compose.yml) live with their own handlers."""
        return []

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Config files don't have traditional definitions."""
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Config files don't have function calls."""
        return []

    # ===========================================================================
    # Classification
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """All config files go to config cluster."""
        return "config"

    # ===========================================================================
    # CodeMap Integration
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> str | None:
        """Resolve config file reference to file path.

        Config files reference other files directly by path, so resolution
        is straightforward path matching.
        """
        # Direct path match
        if module in all_files:
            return module

        # Try relative to source file directory
        source_dir = parent_dir(source_file)
        if source_dir != ".":
            candidate = f"{source_dir}/{module}"
            if candidate in all_files:
                return candidate

        return None
