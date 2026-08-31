"""Integration tests for all scanners."""

import re
from datetime import datetime
from pathlib import Path

from scantool.directory_formatter import DirectoryFormatter
from scantool.formatter import TreeFormatter
from scantool.scanner import FileScanner


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


def test_unix_timestamp_in_output():
    """Test that formatters include unix timestamps for LLM processing."""
    # Test DirectoryFormatter._format_relative_time
    dir_formatter = DirectoryFormatter()

    # Test with current time
    current_time = datetime.now().isoformat()
    result = dir_formatter._format_relative_time(current_time)

    # Verify unix timestamp is present
    assert "[ts:" in result, "Unix timestamp should be present in relative time format"
    assert "]" in result, "Unix timestamp should be properly closed"

    # Verify we can extract the timestamp
    match = re.search(r'\[ts:(\d+)\]', result)
    assert match is not None, "Should be able to extract unix timestamp with regex"

    unix_ts = int(match.group(1))
    assert unix_ts > 0, "Unix timestamp should be positive"

    # Verify the timestamp is reasonably close to now (within 5 seconds)
    now_ts = int(datetime.now().timestamp())
    assert abs(now_ts - unix_ts) < 5, "Unix timestamp should be close to current time"

    # Test TreeFormatter with a real file
    scanner = FileScanner()
    tree_formatter = TreeFormatter()

    test_file = Path(__file__).parent / "python" / "samples" / "basic.py"
    structures = scanner.scan_file(str(test_file))
    output = tree_formatter.format(str(test_file), structures)

    # Check if file-info node has unix timestamp in modified field
    if "file-info:" in output and "modified:" in output:
        # Extract the line with modified timestamp
        for line in output.split('\n'):
            if "modified:" in line:
                assert "[ts:" in line, "File metadata should include unix timestamp"
                break


def test_scan_directory_propagates_mode(monkeypatch):
    """scan_directory must pass its saliency mode through to every scan_file."""
    scanner = FileScanner()
    seen_modes = []
    original = scanner.scan_file

    def spy(path, **kwargs):
        seen_modes.append(kwargs.get("mode"))
        return original(path, **kwargs)

    monkeypatch.setattr(scanner, "scan_file", spy)
    fixture_dir = Path(__file__).parent / "golden" / "fixture_dir"
    results = scanner.scan_directory(str(fixture_dir), mode="active")

    assert results
    assert seen_modes and all(m == "active" for m in seen_modes)


def test_scan_directory_max_files_stops_parsing(tmp_path, monkeypatch):
    """max_files must cap parsing work, not only truncate formatted output."""
    for name in ("a.py", "b.py", "c.py", "d.py"):
        (tmp_path / name).write_text(f"def {name[0]}():\n    return 1\n")

    scanner = FileScanner()
    scanned = []
    original = scanner.scan_file

    def spy(path, **kwargs):
        scanned.append(Path(path).name)
        return original(path, **kwargs)

    monkeypatch.setattr(scanner, "scan_file", spy)

    results = scanner.scan_directory(str(tmp_path), max_files=2)

    assert [Path(path).name for path in results] == ["a.py", "b.py"]
    assert scanned == ["a.py", "b.py"]


def test_scan_file_stubs_oversized_supported_file(tmp_path):
    """max_bytes stubs a file too large to parse regardless of type; None
    (an explicit single-file scan) always parses in full."""
    from scantool.languages import is_file_info_stub

    big = tmp_path / "big.py"
    big.write_text("def real_function():\n    return 1\n" * 500)
    scanner = FileScanner()

    stubbed = scanner.scan_file(str(big), max_bytes=100)
    assert stubbed is not None and is_file_info_stub(stubbed)
    assert stubbed[0].file_metadata["oversized"] is True
    assert stubbed[0].file_metadata["size_formatted"]

    parsed = scanner.scan_file(str(big), max_bytes=None)
    assert parsed is not None and not is_file_info_stub(parsed)
    assert any(n.name == "real_function" for n in parsed)


def test_scan_directory_stubs_oversized_by_size_not_type(tmp_path, monkeypatch):
    """A directory sweep stubs any file over the sweep cap — a large SUPPORTED
    file (not just an unsupported type) — while small files still parse."""
    import scantool.scanner as scanner_module
    from scantool.languages import is_file_info_stub

    (tmp_path / "small.py").write_text("def small():\n    return 1\n")
    (tmp_path / "huge.py").write_text("def huge():\n    return 1\n" * 500)
    monkeypatch.setattr(scanner_module, "SWEEP_MAX_BYTES", 100)

    results = FileScanner().scan_directory(str(tmp_path), "**/*")

    huge = results[str(tmp_path / "huge.py")]
    small = results[str(tmp_path / "small.py")]
    assert is_file_info_stub(huge)          # supported type, stubbed on size
    assert not is_file_info_stub(small)     # under the cap, parsed
    assert any(n.name == "small" for n in small)
