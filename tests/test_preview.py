"""Tests for directory preview functionality."""

import tempfile
from pathlib import Path
import pytest
from scantool.preview import preview_directory, DirectoryPreview, DirectoryStats


class TestDirectoryStats:
    """Test DirectoryStats class."""

    def test_init(self):
        """Test DirectoryStats initialization."""
        stats = DirectoryStats("test/path")
        assert stats.path == "test/path"
        assert stats.file_count == 0
        assert stats.total_size == 0
        assert len(stats.extensions) == 0

    def test_add_file(self):
        """Test adding files to stats."""
        stats = DirectoryStats("test")
        stats.add_file(100, "py")
        stats.add_file(200, "py")
        stats.add_file(150, "md")

        assert stats.file_count == 3
        assert stats.total_size == 450
        assert stats.extensions["py"] == 2
        assert stats.extensions["md"] == 1

    def test_format_size(self):
        """Test size formatting."""
        stats = DirectoryStats("test")
        stats.total_size = 500
        assert "500" in stats.format_size() and "B" in stats.format_size()

        stats.total_size = 1024
        result = stats.format_size()
        assert "KB" in result

        stats.total_size = 1024 * 1024
        result = stats.format_size()
        assert "MB" in result

        stats.total_size = 1024 * 1024 * 1024
        result = stats.format_size()
        assert "GB" in result

    def test_format_extensions(self):
        """Test extension formatting."""
        stats = DirectoryStats("test")
        stats.add_file(100, "py")
        stats.add_file(100, "py")
        stats.add_file(100, "md")
        stats.add_file(100, "txt")

        result = stats.format_extensions()
        assert "py:2" in result
        assert "md:1" in result or "txt:1" in result


class TestDirectoryPreview:
    """Test DirectoryPreview class."""

    def test_scan_empty_directory(self, tmp_path):
        """Test scanning empty directory."""
        scanner = DirectoryPreview(str(tmp_path))
        scanner.scan()

        assert scanner.total_files == 0
        assert scanner.total_size == 0

    def test_scan_simple_directory(self, tmp_path):
        """Test scanning directory with files."""
        # Create test files
        (tmp_path / "file1.py").write_text("print('hello')")
        (tmp_path / "file2.py").write_text("print('world')")
        (tmp_path / "readme.md").write_text("# Test")

        scanner = DirectoryPreview(str(tmp_path))
        scanner.scan()

        assert scanner.total_files == 3
        assert scanner.total_size > 0

    def test_scan_nested_directories(self, tmp_path):
        """Test scanning nested directory structure."""
        # Create nested structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('main')")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("def test_main(): pass")

        scanner = DirectoryPreview(str(tmp_path))
        scanner.scan()

        assert scanner.total_files == 2
        # Check that we have src and tests in stats
        assert any("src" in path for path in scanner.dir_stats.keys())
        assert any("tests" in path for path in scanner.dir_stats.keys())

    def test_max_depth_limit(self, tmp_path):
        """Test max_depth parameter."""
        # Create deep nested structure
        deep_dir = tmp_path / "level1" / "level2" / "level3"
        deep_dir.mkdir(parents=True)
        (deep_dir / "deep.txt").write_text("deep file")

        # Scan with max_depth=1 (only top level)
        scanner = DirectoryPreview(str(tmp_path), max_depth=1)
        scanner.scan()

        # Should not reach the deep file
        assert scanner.total_files == 0

        # Scan with max_depth=None (unlimited)
        scanner_unlimited = DirectoryPreview(str(tmp_path), max_depth=None)
        scanner_unlimited.scan()

        # Should find the deep file
        assert scanner_unlimited.total_files == 1

    def test_gitignore_respected(self, tmp_path):
        """Test that .gitignore patterns are respected."""
        # Create .gitignore
        (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/\n")

        # Create files
        (tmp_path / "good.py").write_text("code")
        (tmp_path / "bad.pyc").write_text("bytecode")

        pycache_dir = tmp_path / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "cache.pyc").write_text("cache")

        # Scan with gitignore respected
        scanner = DirectoryPreview(str(tmp_path), respect_gitignore=True)
        scanner.scan()

        # Should only find good.py and .gitignore
        assert scanner.total_files == 2  # good.py + .gitignore

        # Scan without gitignore
        scanner_no_ignore = DirectoryPreview(str(tmp_path), respect_gitignore=False)
        scanner_no_ignore.scan()

        # Should find all files
        assert scanner_no_ignore.total_files == 4  # good.py, bad.pyc, cache.pyc, .gitignore


class TestPreviewDirectoryFunction:
    """Test preview_directory function."""

    def test_preview_simple_project(self, tmp_path):
        """Test preview of simple project structure."""
        # Create simple project
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("def main(): pass")
        (src_dir / "utils.py").write_text("def helper(): pass")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("def test_main(): pass")

        (tmp_path / "README.md").write_text("# Project")

        # Get preview
        result = preview_directory(str(tmp_path))

        # Check output contains key information
        assert "src/" in result
        assert "tests/" in result
        assert "py:" in result
        assert "Quick start:" in result or "💡" in result

    def test_preview_empty_directory(self, tmp_path):
        """Test preview of empty directory."""
        result = preview_directory(str(tmp_path))

        assert str(tmp_path.name) in result
        assert "0 files" in result or "scanned" in result

    def test_preview_with_recommendations(self, tmp_path):
        """Test that recommendations are generated."""
        # Create significant project structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        for i in range(10):
            (src_dir / f"file{i}.py").write_text(f"# File {i}")

        result = preview_directory(str(tmp_path))

        # Should have recommendations
        assert "scan_directory" in result or "Quick start" in result or "💡" in result

    def test_preview_respects_show_top_n(self, tmp_path):
        """Test show_top_n parameter."""
        # Create many directories
        for i in range(20):
            dir_path = tmp_path / f"dir{i}"
            dir_path.mkdir()
            (dir_path / "file.txt").write_text("content")

        # Preview with limited dirs
        result = preview_directory(str(tmp_path), show_top_n=5)

        # Count directory mentions (approximately)
        dir_count = sum(1 for i in range(20) if f"dir{i}/" in result)

        # Should show roughly 5 (might vary slightly due to formatting)
        assert dir_count <= 7  # Some tolerance for subdirectory display


def test_integration_preview_then_scan(tmp_path):
    """Integration test: preview → scan workflow."""
    # Create realistic project
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("def main(): pass")

    # 1. Preview first
    preview = preview_directory(str(tmp_path))
    assert "src/" in preview

    # 2. Based on preview, we'd typically run scan_directory
    # (We just verify the preview output suggests this)
    assert "scan_directory" in preview.lower() or "quick start" in preview.lower()
