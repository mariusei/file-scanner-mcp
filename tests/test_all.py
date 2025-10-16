"""Comprehensive test suite for all supported file formats."""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scantool.scanner import FileScanner
from scantool.formatter import TreeFormatter


def test_file(file_path: str) -> tuple[bool, str]:
    """Test scanning a single file."""
    scanner = FileScanner()
    formatter = TreeFormatter()

    try:
        structures = scanner.scan_file(file_path)

        if structures is None:
            return False, f"Unsupported file type: {file_path}"

        output = formatter.format(file_path, structures)
        return True, output

    except Exception as e:
        return False, f"Error: {e}"


def main():
    """Run all tests."""
    test_files = [
        "tests/samples/example.py",
        "tests/samples/example.js",
        "tests/samples/example.ts",
        "tests/samples/example.rs",
        "tests/samples/example.go",
        "tests/samples/example.md",
    ]

    print("=" * 80)
    print("File Scanner MCP - Comprehensive Test Suite")
    print("=" * 80)
    print()

    all_passed = True

    for file_path in test_files:
        lang = Path(file_path).suffix
        print(f"\n{'=' * 80}")
        print(f"Testing {lang.upper()} file: {file_path}")
        print("=" * 80)

        success, result = test_file(file_path)

        if success:
            print("✓ PASSED\n")
            print(result)
        else:
            print("✗ FAILED\n")
            print(result)
            all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("✓ ALL TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
