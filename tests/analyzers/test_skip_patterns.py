"""Tests for skip patterns and noise filtering."""

import pytest
import tempfile
from pathlib import Path
from scantool.analyzers.skip_patterns import should_skip_directory, should_skip_file
from scantool.code_map import CodeMap
from scantool.analyzers.python_analyzer import PythonAnalyzer
from scantool.analyzers.typescript_analyzer import TypeScriptAnalyzer
from scantool.analyzers.go_analyzer import GoAnalyzer


class TestSkipPatterns:
    """Test skip_patterns.py functions."""

    def test_skip_git_directory(self):
        """Should skip .git directory."""
        assert should_skip_directory(".git") is True

    def test_skip_node_modules(self):
        """Should skip node_modules directory."""
        assert should_skip_directory("node_modules") is True

    def test_skip_pycache(self):
        """Should skip __pycache__ directory."""
        assert should_skip_directory("__pycache__") is True

    def test_skip_venv(self):
        """Should skip .venv directory."""
        assert should_skip_directory(".venv") is True
        assert should_skip_directory("venv") is True
        assert should_skip_directory(".virtualenv") is True

    def test_skip_dist_build(self):
        """Should skip dist and build directories."""
        assert should_skip_directory("dist") is True
        assert should_skip_directory("build") is True
        assert should_skip_directory("target") is True  # Rust/Java

    def test_skip_cache_dirs(self):
        """Should skip cache directories."""
        assert should_skip_directory(".pytest_cache") is True
        assert should_skip_directory(".mypy_cache") is True
        assert should_skip_directory(".ruff_cache") is True
        assert should_skip_directory(".cache") is True

    def test_skip_ide_dirs(self):
        """Should skip IDE directories."""
        assert should_skip_directory(".idea") is True
        assert should_skip_directory(".vscode") is True
        assert should_skip_directory(".vs") is True

    def test_not_skip_normal_dirs(self):
        """Should not skip normal directories."""
        assert should_skip_directory("src") is False
        assert should_skip_directory("tests") is False
        assert should_skip_directory("backend") is False
        assert should_skip_directory("frontend") is False

    def test_skip_ds_store(self):
        """Should skip .DS_Store."""
        assert should_skip_file(".DS_Store") is True

    def test_skip_gitignore_files(self):
        """Should skip .gitignore and similar."""
        assert should_skip_file(".gitignore") is True
        assert should_skip_file(".gitattributes") is True
        assert should_skip_file(".npmignore") is True
        assert should_skip_file(".dockerignore") is True

    def test_not_skip_normal_files(self):
        """Should not skip normal files."""
        assert should_skip_file("main.py") is False
        assert should_skip_file("README.md") is False
        assert should_skip_file("config.ts") is False


class TestPythonAnalyzerSkip:
    """Test PythonAnalyzer.should_analyze()."""

    def test_skip_pyc_files(self):
        """Should skip .pyc files."""
        analyzer = PythonAnalyzer()
        assert analyzer.should_analyze("module.pyc") is False
        assert analyzer.should_analyze("module.pyo") is False
        assert analyzer.should_analyze("module.pyd") is False

    def test_analyze_normal_py(self):
        """Should analyze normal .py files."""
        analyzer = PythonAnalyzer()
        assert analyzer.should_analyze("main.py") is True
        assert analyzer.should_analyze("src/utils.py") is True
        assert analyzer.should_analyze("__init__.py") is True  # Empty or not, we analyze


class TestTypeScriptAnalyzerSkip:
    """Test TypeScriptAnalyzer.should_analyze()."""

    def test_skip_minified_js(self):
        """Should skip minified JS files."""
        analyzer = TypeScriptAnalyzer()
        assert analyzer.should_analyze("bundle.min.js") is False
        assert analyzer.should_analyze("app.min.mjs") is False
        assert analyzer.should_analyze("vendor.min.cjs") is False

    def test_skip_d_ts_files(self):
        """Should skip TypeScript declaration files."""
        analyzer = TypeScriptAnalyzer()
        assert analyzer.should_analyze("types.d.ts") is False
        assert analyzer.should_analyze("globals.d.ts") is False

    def test_skip_bundles(self):
        """Should skip webpack/rollup bundles."""
        analyzer = TypeScriptAnalyzer()
        assert analyzer.should_analyze("main.bundle.js") is False
        assert analyzer.should_analyze("chunk-vendor.js") is False
        assert analyzer.should_analyze("chunk-123abc.js") is False

    def test_analyze_normal_ts(self):
        """Should analyze normal TypeScript files."""
        analyzer = TypeScriptAnalyzer()
        assert analyzer.should_analyze("main.ts") is True
        assert analyzer.should_analyze("component.tsx") is True
        assert analyzer.should_analyze("app.js") is True
        assert analyzer.should_analyze("utils.mjs") is True


class TestGoAnalyzerSkip:
    """Test GoAnalyzer.should_analyze()."""

    def test_skip_generated_pb_go(self):
        """Should skip protobuf generated files."""
        analyzer = GoAnalyzer()
        assert analyzer.should_analyze("api.pb.go") is False
        assert analyzer.should_analyze("messages.pb.go") is False

    def test_skip_generated_gen_go(self):
        """Should skip other generated files."""
        analyzer = GoAnalyzer()
        assert analyzer.should_analyze("models.gen.go") is False
        assert analyzer.should_analyze("generated_models.go") is False

    def test_analyze_test_files(self):
        """Should analyze test files (they're kept, classified separately)."""
        analyzer = GoAnalyzer()
        assert analyzer.should_analyze("main_test.go") is True

    def test_analyze_normal_go(self):
        """Should analyze normal Go files."""
        analyzer = GoAnalyzer()
        assert analyzer.should_analyze("main.go") is True
        assert analyzer.should_analyze("server.go") is True
        assert analyzer.should_analyze("internal/utils.go") is True


class TestCodeMapDiscovery:
    """Test that CodeMap._discover_files() filters noise correctly."""

    def test_skip_git_directory_in_discovery(self):
        """Should skip .git/ directory during discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create .git/ directory with files
            git_dir = project_dir / ".git"
            git_dir.mkdir()
            (git_dir / "config").write_text("dummy")
            (git_dir / "HEAD").write_text("ref: refs/heads/main")

            # Create normal file
            (project_dir / "main.py").write_text("def main(): pass")

            # Analyze
            cm = CodeMap(str(project_dir), respect_gitignore=False, enable_layer2=False)
            result = cm.analyze()

            # Should find main.py, NOT .git/config or .git/HEAD
            file_paths = [f.path for f in result.files]
            assert any("main.py" in fp for fp in file_paths)
            assert not any(".git" in fp for fp in file_paths)

    def test_skip_node_modules_in_discovery(self):
        """Should skip node_modules/ directory during discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create node_modules/ with files
            node_modules = project_dir / "node_modules"
            node_modules.mkdir()
            (node_modules / "package.js").write_text("module.exports = {}")

            # Create normal file
            (project_dir / "app.ts").write_text("export const app = 1")

            # Analyze
            cm = CodeMap(str(project_dir), respect_gitignore=False, enable_layer2=False)
            result = cm.analyze()

            # Should find app.ts, NOT node_modules/package.js
            file_paths = [f.path for f in result.files]
            assert any("app.ts" in fp for fp in file_paths)
            assert not any("node_modules" in fp for fp in file_paths)

    def test_skip_pycache_in_discovery(self):
        """Should skip __pycache__/ directory during discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create __pycache__/ with .pyc files
            pycache = project_dir / "__pycache__"
            pycache.mkdir()
            (pycache / "module.cpython-312.pyc").write_bytes(b"\x00\x00\x00\x00")

            # Create normal file
            (project_dir / "module.py").write_text("def foo(): pass")

            # Analyze
            cm = CodeMap(str(project_dir), respect_gitignore=False, enable_layer2=False)
            result = cm.analyze()

            # Should find module.py, NOT __pycache__/module.cpython-312.pyc
            file_paths = [f.path for f in result.files]
            assert any("module.py" in fp for fp in file_paths)
            assert not any("__pycache__" in fp for fp in file_paths)

    def test_skip_venv_in_discovery(self):
        """Should skip .venv/ directory during discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create .venv/ with Python files
            venv_dir = project_dir / ".venv"
            venv_dir.mkdir()
            (venv_dir / "lib").mkdir()
            (venv_dir / "lib" / "site-packages").write_text("")

            # Create normal file
            (project_dir / "main.py").write_text("import sys")

            # Analyze
            cm = CodeMap(str(project_dir), respect_gitignore=False, enable_layer2=False)
            result = cm.analyze()

            # Should find main.py, NOT .venv/lib/site-packages
            file_paths = [f.path for f in result.files]
            assert any("main.py" in fp for fp in file_paths)
            assert not any(".venv" in fp for fp in file_paths)

    def test_skip_ds_store_in_discovery(self):
        """Should skip .DS_Store files during discovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create .DS_Store
            (project_dir / ".DS_Store").write_bytes(b"\x00\x00\x00\x00")

            # Create normal file
            (project_dir / "main.py").write_text("def main(): pass")

            # Analyze
            cm = CodeMap(str(project_dir), respect_gitignore=False, enable_layer2=False)
            result = cm.analyze()

            # Should find main.py, NOT .DS_Store
            file_paths = [f.path for f in result.files]
            assert any("main.py" in fp for fp in file_paths)
            assert not any(".DS_Store" in fp for fp in file_paths)

    def test_multi_level_noise_filtering(self):
        """Should filter noise at multiple directory levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create nested structure with noise
            src = project_dir / "src"
            src.mkdir()
            (src / "main.py").write_text("def main(): pass")

            # Create __pycache__ in src/
            pycache = src / "__pycache__"
            pycache.mkdir()
            (pycache / "main.pyc").write_bytes(b"\x00")

            # Create .git/ at root
            git_dir = project_dir / ".git"
            git_dir.mkdir()
            (git_dir / "config").write_text("")

            # Create node_modules/ at root
            node_modules = project_dir / "node_modules"
            node_modules.mkdir()
            (node_modules / "lib.js").write_text("")

            # Analyze
            cm = CodeMap(str(project_dir), respect_gitignore=False, enable_layer2=False)
            result = cm.analyze()

            # Should find ONLY src/main.py
            assert result.total_files == 1
            file_paths = [f.path for f in result.files]
            assert any("src/main.py" in fp or "src\\main.py" in fp for fp in file_paths)
            assert not any(".git" in fp for fp in file_paths)
            assert not any("node_modules" in fp for fp in file_paths)
            assert not any("__pycache__" in fp for fp in file_paths)

    def test_skip_combined_with_analyzer_should_analyze(self):
        """Should combine directory skip AND analyzer.should_analyze()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create minified JS file
            (project_dir / "app.min.js").write_text("!function(){}")

            # Create normal JS file
            (project_dir / "app.js").write_text("export const app = 1")

            # Create .pyc file (wrong language, but tests skip)
            (project_dir / "module.pyc").write_bytes(b"\x00")

            # Create normal Python file
            (project_dir / "module.py").write_text("def foo(): pass")

            # Analyze
            cm = CodeMap(str(project_dir), respect_gitignore=False, enable_layer2=False)
            result = cm.analyze()

            # Should find app.js and module.py
            # Should NOT find app.min.js (TypeScriptAnalyzer.should_analyze() = False)
            # Should NOT find module.pyc (PythonAnalyzer.should_analyze() = False)
            file_paths = [f.path for f in result.files]

            # Should have analyzed app.js and module.py
            assert any("app.js" in fp for fp in file_paths)
            assert any("module.py" in fp for fp in file_paths)

            # Definitions should exist (if files were analyzed)
            # app.min.js and module.pyc should not contribute
            assert len(result.files) == 2  # Only 2 files analyzed
