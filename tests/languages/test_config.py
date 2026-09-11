"""Tests for config language (.ini).

.json and .toml semantics moved to test_json_semantic.py / test_toml_semantic.py
alongside their own dedicated language handlers.
"""

import pytest

from scantool.languages.config import ConfigLanguage


@pytest.fixture
def language():
    """Create language instance."""
    return ConfigLanguage()


class TestConfigAnalyzer:
    """Test suite for config language."""

    def test_extensions(self, language):
        """Test that analyzer supports correct extensions."""
        extensions = language.get_extensions()
        assert ".ini" in extensions
        assert ".json" not in extensions
        assert ".toml" not in extensions

    def test_language_name(self, language):
        """Test language name."""
        assert language.get_language_name() == "Config"

    def test_should_analyze_skip_lock_files(self, language):
        """Test that lock files are skipped."""
        assert language.should_analyze("package-lock.json") is False
        assert language.should_analyze("yarn.lock") is False
        assert language.should_analyze("pnpm-lock.yaml") is False
        assert language.should_analyze("poetry.lock") is False
        assert language.should_analyze("Cargo.lock") is False
        assert language.should_analyze("custom.lock") is False

    def test_should_analyze_skip_minified(self, language):
        """Test that minified files are skipped."""
        assert language.should_analyze("config.min.json") is False
        assert language.should_analyze("config.json") is True

    def test_should_analyze_normal_files(self, language):
        """Test that normal config files are analyzed."""
        assert language.should_analyze("docker-compose.yml") is True
        assert language.should_analyze("app.ini") is True

    def test_extract_imports_ini_file_paths(self, language):
        """Test extraction of file paths from INI files."""
        content = """[settings]
config_path = ./config/app.conf
log_file = "/var/log/app.log"
data_dir = ../data
"""
        imports = language.extract_imports("config.ini", content)
        ini_imports = [imp for imp in imports if imp.import_type == "config_value"]
        assert len(ini_imports) >= 1
        assert any("./config/app.conf" in imp.target_module for imp in ini_imports)

    # ===================================================================
    # Generic path patterns
    # ===================================================================

    def test_extract_imports_generic_quoted_paths(self, language):
        """Test extraction of generic quoted relative paths."""
        content = """template: "./templates/base.html"
stylesheet: "../assets/style.css"
"""
        imports = language.extract_imports("custom.yaml", content)
        assert len(imports) >= 2
        assert any(imp.target_module == "./templates/base.html" for imp in imports)
        assert any(imp.target_module == "../assets/style.css" for imp in imports)

    def test_extract_imports_generic_no_urls(self, language):
        """Test that URLs are not extracted as paths."""
        content = """api: "https://api.example.com/data.json"
local: "./local/file.json"
"""
        imports = language.extract_imports("config.yaml", content)
        # Should extract local path but not URL
        assert any(imp.target_module == "./local/file.json" for imp in imports)
        assert not any("https://" in imp.target_module for imp in imports)

    # ===================================================================
    # Entry points
    # ===================================================================

    def test_classify_file_all_config(self, language):
        """Test that all config files are classified as config cluster."""
        assert language.classify_file("docker-compose.yml", "") == "config"
        assert language.classify_file("config.ini", "") == "config"

    # ===================================================================
    # Edge cases
    # ===================================================================

    def test_extract_imports_empty_file(self, language):
        """Test that empty files return empty imports."""
        imports = language.extract_imports("empty.yaml", "")
        assert imports == []

    def test_find_entry_points_empty_file(self, language):
        """Test that empty files return empty entry points."""
        entry_points = language.find_entry_points("empty.yaml", "")
        assert entry_points == []
