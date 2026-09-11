"""Semantic tests for TOML language (imports, entry points, classification).

Structure-scanning tests live in tests/toml/test_toml.py. These test bodies
were moved from test_config.py when .toml got its own dedicated handler.
"""

import pytest

from scantool.languages.toml import TOMLLanguage


@pytest.fixture
def language():
    """Create language instance."""
    return TOMLLanguage()


class TestTOMLAnalyzer:
    """Test suite for TOML semantic analysis."""

    def test_extensions(self, language):
        """Test that analyzer supports correct extensions."""
        assert language.get_extensions() == [".toml"]

    def test_language_name(self, language):
        """Test language name."""
        assert language.get_language_name() == "TOML"

    def test_should_analyze_skip_lock_files(self, language):
        """Test that lock files are skipped."""
        assert language.should_analyze("Cargo.lock") is False
        assert language.should_analyze("poetry.lock") is False
        assert language.should_analyze("custom.lock") is False

    def test_should_analyze_normal_files(self, language):
        """Test that normal TOML files are analyzed."""
        assert language.should_analyze("pyproject.toml") is True
        assert language.should_analyze("Cargo.toml") is True

    # ===================================================================
    # TOML imports
    # ===================================================================

    def test_extract_imports_cargo_toml_path_dependencies(self, language):
        """Test extraction of path dependencies from Cargo.toml."""
        content = """[dependencies]
serde = "1.0"
my_crate = { path = "../my_crate" }
utils = { path = "./utils" }
"""
        imports = language.extract_imports("Cargo.toml", content)
        path_imports = [imp for imp in imports if imp.import_type == "path_dependency"]
        assert len(path_imports) == 2
        assert any(imp.target_module == "../my_crate" for imp in path_imports)
        assert any(imp.target_module == "./utils" for imp in path_imports)

    def test_extract_imports_cargo_toml_no_registry_deps(self, language):
        """Test that Cargo.toml registry dependencies are NOT extracted."""
        content = """[dependencies]
serde = "1.0"
tokio = { version = "1.0", features = ["full"] }
"""
        imports = language.extract_imports("Cargo.toml", content)
        # Should not extract registry package names
        assert not any(imp.target_module == "serde" for imp in imports)
        assert not any(imp.target_module == "tokio" for imp in imports)

    def test_extract_imports_pyproject_toml_config_file(self, language):
        """Test extraction of config file paths from pyproject.toml."""
        content = """[tool.mypy]
config_file = "mypy.ini"
python_version = "3.11"
"""
        imports = language.extract_imports("pyproject.toml", content)
        config_imports = [imp for imp in imports if imp.import_type == "config_file"]
        assert len(config_imports) == 1
        assert config_imports[0].target_module == "mypy.ini"

    # ===================================================================
    # Generic path patterns
    # ===================================================================

    def test_extract_imports_generic_quoted_paths(self, language):
        """Test extraction of generic quoted relative paths."""
        content = """template = "./templates/base.html"
stylesheet = "../assets/style.css"
"""
        imports = language.extract_imports("custom.toml", content)
        assert len(imports) >= 2
        assert any(imp.target_module == "./templates/base.html" for imp in imports)
        assert any(imp.target_module == "../assets/style.css" for imp in imports)

    def test_extract_imports_generic_no_urls(self, language):
        """Test that URLs are not extracted as paths."""
        content = """api = "https://api.example.com/data.json"
local = "./local/file.json"
"""
        imports = language.extract_imports("config.toml", content)
        assert any(imp.target_module == "./local/file.json" for imp in imports)
        assert not any("https://" in imp.target_module for imp in imports)

    # ===================================================================
    # Entry points
    # ===================================================================

    def test_find_entry_points_pyproject_toml(self, language):
        """Test detection of pyproject.toml as Python project."""
        content = """[project]
name = "my-package"
version = "0.1.0"
"""
        entry_points = language.find_entry_points("pyproject.toml", content)
        project_entries = [ep for ep in entry_points if ep.type == "project_config"]
        assert len(project_entries) == 1
        assert project_entries[0].framework == "Python"

    def test_find_entry_points_pyproject_toml_scripts(self, language):
        """Test detection of project.scripts section in pyproject.toml."""
        content = """[project.scripts]
my-cli = "my_package:main"
"""
        entry_points = language.find_entry_points("pyproject.toml", content)
        script_entries = [ep for ep in entry_points if ep.type == "scripts_section"]
        assert len(script_entries) == 1

    def test_find_entry_points_cargo_toml(self, language):
        """Test detection of Cargo.toml as Rust project."""
        content = """[package]
name = "my-crate"
version = "0.1.0"
"""
        entry_points = language.find_entry_points("Cargo.toml", content)
        project_entries = [ep for ep in entry_points if ep.type == "project_config"]
        assert len(project_entries) == 1
        assert project_entries[0].framework == "Rust"

    def test_find_entry_points_cargo_toml_bin(self, language):
        """Test detection of [[bin]] targets in Cargo.toml."""
        content = """[[bin]]
name = "my-cli"
path = "src/bin/cli.rs"

[[bin]]
name = "my-tool"
"""
        entry_points = language.find_entry_points("Cargo.toml", content)
        bin_entries = [ep for ep in entry_points if ep.type == "bin_target"]
        assert len(bin_entries) == 2

    # ===================================================================
    # Classification
    # ===================================================================

    def test_classify_file_all_config(self, language):
        """Test that all TOML files are classified as config cluster."""
        assert language.classify_file("pyproject.toml", "") == "config"
        assert language.classify_file("Cargo.toml", "") == "config"

    # ===================================================================
    # Edge cases
    # ===================================================================

    def test_extract_imports_empty_file(self, language):
        """Test that empty files return empty imports."""
        imports = language.extract_imports("empty.toml", "")
        assert imports == []

    def test_find_entry_points_empty_file(self, language):
        """Test that empty files return empty entry points."""
        entry_points = language.find_entry_points("empty.toml", "")
        assert entry_points == []

    def test_resolve_import_to_file_direct_match(self, language):
        """Direct path match resolves as-is."""
        all_files = ["src/main.rs", "Cargo.toml"]
        assert language.resolve_import_to_file("src/main.rs", "Cargo.toml", all_files, {}) == (
            "src/main.rs"
        )

    def test_resolve_import_to_file_relative_to_source(self, language):
        """A reference relative to the source file's directory resolves."""
        all_files = ["config/base.toml", "config/app.toml"]
        result = language.resolve_import_to_file("base.toml", "config/app.toml", all_files, {})
        assert result == "config/base.toml"

    def test_resolve_import_to_file_no_match(self, language):
        """An unresolvable reference returns None."""
        assert language.resolve_import_to_file("missing.toml", "app.toml", [], {}) is None
