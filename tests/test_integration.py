"""Integration tests for all scanners."""

from pathlib import Path

import pytest

from scantool.scanner import FileScanner
from scantool.formatter import TreeFormatter


def test_scan_all_sample_files():
    """Test that all sample files can be scanned without crashing."""
    scanner = FileScanner()
    formatter = TreeFormatter()

    # Get all sample files from all language directories
    test_dir = Path(__file__).parent
    sample_dirs = [
        test_dir / "python" / "samples",
        test_dir / "typescript" / "samples",
        test_dir / "text" / "samples",
    ]

    tested_files = 0
    for sample_dir in sample_dirs:
        if not sample_dir.exists():
            continue

        for file_path in sample_dir.iterdir():
            if file_path.is_file():
                # Skip hidden files
                if file_path.name.startswith("."):
                    continue

                structures = scanner.scan_file(str(file_path))
                assert structures is not None, f"Should parse {file_path}"

                # Verify formatter doesn't crash
                output = formatter.format(str(file_path), structures)
                assert len(output) > 0, f"Should format output for {file_path}"

                tested_files += 1

    assert tested_files > 0, "Should have tested at least one file"


def test_scanner_registry():
    """Test that scanner registry is properly initialized."""
    scanner = FileScanner()

    supported_extensions = scanner.get_supported_extensions()
    assert len(supported_extensions) > 0, "Should have registered scanners"

    # Verify expected extensions are supported
    assert ".py" in supported_extensions, "Should support Python"
    assert ".ts" in supported_extensions or ".tsx" in supported_extensions, "Should support TypeScript"
    assert ".txt" in supported_extensions, "Should support text"

    scanner_info = scanner.get_scanner_info()
    assert len(scanner_info) > 0, "Should have scanner info"


def test_formatter_consistency():
    """Test that formatter produces consistent output."""
    scanner = FileScanner()
    formatter = TreeFormatter()

    test_file = Path(__file__).parent / "python" / "samples" / "basic.py"

    structures = scanner.scan_file(str(test_file))
    output1 = formatter.format(str(test_file), structures)
    output2 = formatter.format(str(test_file), structures)

    assert output1 == output2, "Formatter should produce identical output for same input"
