"""Main file scanner orchestrator using the plugin system."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .scanners import BaseScanner, StructureNode, get_registry
from .gitignore import load_gitignore, GitignoreParser
from .glob_expander import expand_braces


class FileScanner:
    """Main scanner that delegates to language-specific scanner plugins."""

    def __init__(self, show_errors: bool = True, fallback_on_errors: bool = True):
        """
        Initialize file scanner.

        Args:
            show_errors: Show parse error nodes in output
            fallback_on_errors: Use regex fallback for severely broken files
        """
        self.registry = get_registry()
        self.show_errors = show_errors
        self.fallback_on_errors = fallback_on_errors

    def scan_file(self, file_path: str, include_file_metadata: bool = True) -> Optional[list[StructureNode]]:
        """
        Scan a single file and return its structure.

        Args:
            file_path: Path to the file to scan
            include_file_metadata: Include file metadata (size, timestamps) as first node

        Returns:
            List of StructureNode objects, or None if file type not supported
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get appropriate scanner for this file type
        suffix = path.suffix.lower()
        scanner_class = self.registry.get_scanner(suffix)

        if not scanner_class:
            return None  # Unsupported file type

        # Get file metadata
        file_stats = os.stat(file_path)

        # Create scanner instance with options
        scanner = scanner_class(
            show_errors=self.show_errors,
            fallback_on_errors=self.fallback_on_errors
        )

        # Read file
        with open(file_path, "rb") as f:
            source_code = f.read()

        # Scan using the appropriate plugin
        structures = scanner.scan(source_code)

        # Prepend file metadata if requested and structures exist
        if include_file_metadata and structures is not None:
            # Format file size
            size_bytes = file_stats.st_size
            if size_bytes < 1024:
                size_str = f"{size_bytes}B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f}KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f}MB"

            # Create file info node
            file_info = StructureNode(
                type="file-info",
                name=path.name,
                start_line=1,
                end_line=1,
                file_metadata={
                    "size": size_bytes,
                    "size_formatted": size_str,
                    "created": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                    "permissions": oct(file_stats.st_mode)[-3:],
                }
            )
            structures = [file_info] + structures

        return structures

    def scan_directory(
        self,
        directory: str,
        pattern: str = "**/*",
        respect_gitignore: bool = True,
        exclude_patterns: Optional[list[str]] = None
    ) -> dict[str, Optional[list[StructureNode]]]:
        """
        Scan all supported files in a directory.

        Args:
            directory: Directory path to scan
            pattern: Glob pattern for files (use "**/*" for recursive, "*" for current dir only)
            respect_gitignore: Respect .gitignore exclusions (default: True)
            exclude_patterns: Additional patterns to exclude (gitignore syntax)

        Returns:
            Dictionary mapping file paths to their structures
        """
        results = {}
        dir_path = Path(directory).resolve()

        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        # Load gitignore if requested
        gitignore = load_gitignore(dir_path) if respect_gitignore else None

        # Default exclusions - always applied
        default_exclusions = [
            '.DS_Store',      # macOS
            'Thumbs.db',      # Windows
            'desktop.ini',    # Windows
            '.localized',     # macOS
        ]

        # Combine defaults with user-provided exclusions
        all_exclude_patterns = default_exclusions.copy()
        if exclude_patterns:
            all_exclude_patterns.extend(exclude_patterns)

        # Parse exclusion patterns
        exclude_parser = GitignoreParser(all_exclude_patterns) if all_exclude_patterns else None

        # Expand brace patterns (e.g., "**/*.{py,js}" → ["**/*.py", "**/*.js"])
        expanded_patterns = expand_braces(pattern)

        # Process each expanded pattern
        seen_files = set()  # Avoid duplicates if patterns overlap
        for expanded_pattern in expanded_patterns:
            for file_path in dir_path.glob(expanded_pattern):
                if not file_path.is_file():
                    continue

                # Skip if already processed
                file_str = str(file_path)
                if file_str in seen_files:
                    continue
                seen_files.add(file_str)

                # Check exclusions
                try:
                    rel_path = str(file_path.relative_to(dir_path))
                except ValueError:
                    # File outside base directory
                    continue

                # Skip files inside hidden directories (directories starting with .)
                # But allow hidden files themselves (e.g., .gitignore, .python-version)
                path_parts = Path(rel_path).parts
                if any(part.startswith('.') and part not in [file_path.name] for part in path_parts):
                    # File is inside a hidden directory, skip it
                    continue

                # Check gitignore
                if gitignore and gitignore.matches(rel_path, file_path.is_dir()):
                    continue

                # Check additional exclusions
                if exclude_parser and exclude_parser.matches(rel_path, file_path.is_dir()):
                    continue

                # Check if we have a scanner for this file type
                scanner_class = self.registry.get_scanner(file_path.suffix.lower())
                if scanner_class:
                    # Check if scanner wants to skip this file
                    if scanner_class.should_skip(file_path.name):
                        continue

                    try:
                        results[file_str] = self.scan_file(file_str)
                    except Exception as e:
                        # Continue scanning even if one file fails
                        results[file_str] = [StructureNode(
                            type="error",
                            name=f"Failed to scan: {str(e)}",
                            start_line=1,
                            end_line=1
                        )]
                else:
                    # Unsupported file type - include with basic metadata only
                    try:
                        file_stats = os.stat(file_str)
                        size_bytes = file_stats.st_size
                        if size_bytes < 1024:
                            size_str = f"{size_bytes}B"
                        elif size_bytes < 1024 * 1024:
                            size_str = f"{size_bytes / 1024:.1f}KB"
                        else:
                            size_str = f"{size_bytes / (1024 * 1024):.1f}MB"

                        results[file_str] = [StructureNode(
                            type="file-info",
                            name=file_path.name,
                            start_line=1,
                            end_line=1,
                            file_metadata={
                                "size": size_bytes,
                                "size_formatted": size_str,
                                "extension": file_path.suffix or "(no extension)",
                                "modified": datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                                "unsupported": True
                            }
                        )]
                    except Exception:
                        # If we can't even get metadata, skip the file
                        continue

        return results

    def get_supported_extensions(self) -> list[str]:
        """Get list of all supported file extensions."""
        return self.registry.get_supported_extensions()

    def get_scanner_info(self) -> dict[str, str]:
        """Get mapping of extensions to language names."""
        return self.registry.get_scanner_info()


# For backward compatibility, export StructureNode
__all__ = ["FileScanner", "StructureNode"]
