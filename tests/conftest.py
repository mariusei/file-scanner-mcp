"""Shared fixtures for all tests."""

from pathlib import Path

import pytest

from scantool.scanner import FileScanner
from scantool.formatter import TreeFormatter


@pytest.fixture
def file_scanner():
    """Return a FileScanner instance."""
    return FileScanner()


@pytest.fixture
def tree_formatter():
    """Return a TreeFormatter instance with default settings."""
    return TreeFormatter(
        show_signatures=True,
        show_decorators=True,
        show_docstrings=True,
        show_complexity=False
    )


@pytest.fixture
def sample_dir():
    """Return the path to the samples directory for the current test language."""
    def _get_sample_dir(language: str) -> Path:
        return Path(__file__).parent / language / "samples"
    return _get_sample_dir


@pytest.fixture
def basic_sample(sample_dir, request):
    """Return the path to the basic sample file for the current test language.

    Uses the parent directory name to determine the language.
    """
    test_file_path = Path(request.fspath)
    language = test_file_path.parent.name

    # Determine extension based on language
    extension_map = {
        "python": ".py",
        "typescript": ".ts",
        "text": ".txt",
    }

    ext = extension_map.get(language, "")
    return sample_dir(language) / f"basic{ext}"


def validate_line_range_invariants(structures, parent=None, parent_name="root"):
    """Validate universal line range invariants for any scanner.

    This function tests properties that should hold for ALL scanners:
    1. Line numbers are positive and valid
    2. end_line >= start_line
    3. Children are within parent's range
    4. Siblings don't overlap
    5. Structures that can have content span multiple lines

    Args:
        structures: List of StructureNode to validate
        parent: Parent StructureNode (for recursion)
        parent_name: Name of parent (for error messages)

    Raises:
        AssertionError: If any invariant is violated
    """
    for i, node in enumerate(structures):
        # Invariant 1: Valid line numbers (1-indexed)
        assert node.start_line > 0, \
            f"{node.name}: start_line must be positive, got {node.start_line}"

        # Invariant 2: End >= Start
        assert node.end_line >= node.start_line, \
            f"{node.name}: end_line ({node.end_line}) must be >= start_line ({node.start_line})"

        # Invariant 3: Multi-line structures
        # Classes, functions, methods, and headings with children should span multiple lines
        if node.children and node.type in ("class", "function", "method") or node.type.startswith("heading"):
            assert node.end_line > node.start_line, \
                f"{node.name}: {node.type} with children should span multiple lines, got ({node.start_line}-{node.end_line})"

        # Invariant 4: Children within parent range
        if parent is not None:
            assert node.start_line >= parent.start_line, \
                f"{node.name} (child of {parent_name}): child starts at {node.start_line}, before parent starts at {parent.start_line}"
            assert node.end_line <= parent.end_line, \
                f"{node.name} (child of {parent_name}): child ends at {node.end_line}, after parent ends at {parent.end_line}"

        # Invariant 5: Siblings don't overlap
        # Skip this check for metadata nodes (file-info, imports) which can overlap with content
        metadata_types = ("file-info", "imports")
        if i + 1 < len(structures):
            next_node = structures[i + 1]
            if node.type not in metadata_types and next_node.type not in metadata_types:
                assert node.end_line < next_node.start_line, \
                    f"Sibling overlap: {node.name} ends at line {node.end_line}, but {next_node.name} starts at line {next_node.start_line}"

        # Recurse into children
        if node.children:
            validate_line_range_invariants(node.children, parent=node, parent_name=node.name)
