"""Tests for config analyzer."""

import pytest
from scantool.analyzers.config_analyzer import ConfigAnalyzer


@pytest.fixture
def analyzer():
    """Create config analyzer instance."""
    return ConfigAnalyzer()


class TestConfigAnalyzer:
    """Test suite for config analyzer."""

    def test_extensions(self, analyzer):
        """Test that analyzer supports correct extensions."""
        extensions = analyzer.get_extensions()
        assert ".json" in extensions
        assert ".yaml" in extensions
        assert ".yml" in extensions
        assert ".toml" in extensions
        assert ".ini" in extensions

    def test_language_name(self, analyzer):
        """Test language name."""
        assert analyzer.get_language_name() == "Config"

    def test_should_analyze_skip_lock_files(self, analyzer):
        """Test that lock files are skipped."""
        assert analyzer.should_analyze("package-lock.json") is False
        assert analyzer.should_analyze("yarn.lock") is False
        assert analyzer.should_analyze("pnpm-lock.yaml") is False
        assert analyzer.should_analyze("poetry.lock") is False
        assert analyzer.should_analyze("Cargo.lock") is False
        assert analyzer.should_analyze("custom.lock") is False

    def test_should_analyze_skip_minified(self, analyzer):
        """Test that minified files are skipped."""
        assert analyzer.should_analyze("config.min.json") is False
        assert analyzer.should_analyze("config.json") is True

    def test_should_analyze_normal_files(self, analyzer):
        """Test that normal config files are analyzed."""
        assert analyzer.should_analyze("package.json") is True
        assert analyzer.should_analyze("tsconfig.json") is True
        assert analyzer.should_analyze("pyproject.toml") is True
        assert analyzer.should_analyze("docker-compose.yml") is True

    # ===================================================================
    # JSON imports
    # ===================================================================

    def test_extract_imports_tsconfig_extends(self, analyzer):
        """Test extraction of tsconfig extends."""
        content = """{
  "extends": "./base.json",
  "compilerOptions": {}
}"""
        imports = analyzer.extract_imports("tsconfig.json", content)
        extends_imports = [imp for imp in imports if imp.import_type == "extends"]
        assert len(extends_imports) == 1
        assert extends_imports[0].target_module == "./base.json"

    def test_extract_imports_tsconfig_files(self, analyzer):
        """Test extraction of tsconfig files array."""
        content = """{
  "files": [
    "src/index.ts",
    "src/types.ts"
  ]
}"""
        imports = analyzer.extract_imports("tsconfig.json", content)
        file_imports = [imp for imp in imports if imp.import_type == "file_reference"]
        assert len(file_imports) == 2
        assert any(imp.target_module == "src/index.ts" for imp in file_imports)
        assert any(imp.target_module == "src/types.ts" for imp in file_imports)

    def test_extract_imports_tsconfig_paths(self, analyzer):
        """Test extraction of tsconfig path mappings."""
        content = """{
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"],
      "@components/*": ["./src/components/*"]
    }
  }
}"""
        imports = analyzer.extract_imports("tsconfig.json", content)
        path_imports = [imp for imp in imports if imp.import_type == "path_mapping"]
        assert len(path_imports) == 2
        assert any(imp.target_module == "./src/*" for imp in path_imports)
        assert any(imp.target_module == "./src/components/*" for imp in path_imports)

    def test_extract_imports_package_json_scripts(self, analyzer):
        """Test extraction of file references from package.json scripts."""
        content = """{
  "scripts": {
    "build": "node build.js",
    "test": "node ./scripts/test.mjs"
  }
}"""
        imports = analyzer.extract_imports("package.json", content)
        script_imports = [imp for imp in imports if imp.import_type == "script_file"]
        assert len(script_imports) >= 1
        assert any("build.js" in imp.target_module for imp in script_imports)

    def test_extract_imports_package_json_no_dependencies(self, analyzer):
        """Test that package.json dependencies are NOT extracted (they're package names)."""
        content = """{
  "dependencies": {
    "react": "^18.0.0",
    "lodash": "^4.17.21"
  }
}"""
        imports = analyzer.extract_imports("package.json", content)
        # Should not extract package names from dependencies
        assert not any("react" in imp.target_module for imp in imports)
        assert not any("lodash" in imp.target_module for imp in imports)

    # ===================================================================
    # YAML imports
    # ===================================================================

    def test_extract_imports_docker_compose_env_file(self, analyzer):
        """Test extraction of env_file from docker-compose.yml."""
        content = """version: '3'
services:
  web:
    env_file: .env.production
    image: nginx
"""
        imports = analyzer.extract_imports("docker-compose.yml", content)
        env_imports = [imp for imp in imports if imp.import_type == "env_file"]
        assert len(env_imports) == 1
        assert env_imports[0].target_module == ".env.production"

    def test_extract_imports_docker_compose_dockerfile(self, analyzer):
        """Test extraction of Dockerfile paths from docker-compose.yml."""
        content = """version: '3'
services:
  app:
    build:
      dockerfile: ./docker/Dockerfile.prod
"""
        imports = analyzer.extract_imports("docker-compose.yml", content)
        dockerfile_imports = [imp for imp in imports if imp.import_type == "dockerfile"]
        assert len(dockerfile_imports) == 1
        assert dockerfile_imports[0].target_module == "./docker/Dockerfile.prod"

    def test_extract_imports_docker_compose_volumes(self, analyzer):
        """Test extraction of volume mounts from docker-compose.yml."""
        content = """version: '3'
services:
  db:
    volumes:
      - ./data:/var/lib/postgresql/data
      - ./config:/etc/config
"""
        imports = analyzer.extract_imports("docker-compose.yml", content)
        volume_imports = [imp for imp in imports if imp.import_type == "volume_mount"]
        assert len(volume_imports) >= 2
        assert any(imp.target_module == "./data" for imp in volume_imports)
        assert any(imp.target_module == "./config" for imp in volume_imports)

    # ===================================================================
    # TOML imports
    # ===================================================================

    def test_extract_imports_cargo_toml_path_dependencies(self, analyzer):
        """Test extraction of path dependencies from Cargo.toml."""
        content = """[dependencies]
serde = "1.0"
my_crate = { path = "../my_crate" }
utils = { path = "./utils" }
"""
        imports = analyzer.extract_imports("Cargo.toml", content)
        path_imports = [imp for imp in imports if imp.import_type == "path_dependency"]
        assert len(path_imports) == 2
        assert any(imp.target_module == "../my_crate" for imp in path_imports)
        assert any(imp.target_module == "./utils" for imp in path_imports)

    def test_extract_imports_cargo_toml_no_registry_deps(self, analyzer):
        """Test that Cargo.toml registry dependencies are NOT extracted."""
        content = """[dependencies]
serde = "1.0"
tokio = { version = "1.0", features = ["full"] }
"""
        imports = analyzer.extract_imports("Cargo.toml", content)
        # Should not extract registry package names
        assert not any("serde" == imp.target_module for imp in imports)
        assert not any("tokio" == imp.target_module for imp in imports)

    def test_extract_imports_pyproject_toml_config_file(self, analyzer):
        """Test extraction of config file paths from pyproject.toml."""
        content = """[tool.mypy]
config_file = "mypy.ini"
python_version = "3.11"
"""
        imports = analyzer.extract_imports("pyproject.toml", content)
        config_imports = [imp for imp in imports if imp.import_type == "config_file"]
        assert len(config_imports) == 1
        assert config_imports[0].target_module == "mypy.ini"

    # ===================================================================
    # INI imports
    # ===================================================================

    def test_extract_imports_ini_file_paths(self, analyzer):
        """Test extraction of file paths from INI files."""
        content = """[settings]
config_path = ./config/app.conf
log_file = "/var/log/app.log"
data_dir = ../data
"""
        imports = analyzer.extract_imports("config.ini", content)
        ini_imports = [imp for imp in imports if imp.import_type == "config_value"]
        assert len(ini_imports) >= 1
        assert any("./config/app.conf" in imp.target_module for imp in ini_imports)

    # ===================================================================
    # Generic path patterns
    # ===================================================================

    def test_extract_imports_generic_quoted_paths(self, analyzer):
        """Test extraction of generic quoted relative paths."""
        content = """{
  "template": "./templates/base.html",
  "stylesheet": "../assets/style.css"
}"""
        imports = analyzer.extract_imports("custom.json", content)
        assert len(imports) >= 2
        assert any(imp.target_module == "./templates/base.html" for imp in imports)
        assert any(imp.target_module == "../assets/style.css" for imp in imports)

    def test_extract_imports_generic_no_urls(self, analyzer):
        """Test that URLs are not extracted as paths."""
        content = """{
  "api": "https://api.example.com/data.json",
  "local": "./local/file.json"
}"""
        imports = analyzer.extract_imports("config.json", content)
        # Should extract local path but not URL
        assert any(imp.target_module == "./local/file.json" for imp in imports)
        assert not any("https://" in imp.target_module for imp in imports)

    # ===================================================================
    # Entry points
    # ===================================================================

    def test_find_entry_points_package_json(self, analyzer):
        """Test detection of package.json as npm project entry point."""
        content = """{
  "name": "my-app",
  "main": "index.js"
}"""
        entry_points = analyzer.find_entry_points("package.json", content)
        project_entries = [ep for ep in entry_points if ep.type == "project_config"]
        assert len(project_entries) == 1
        assert project_entries[0].framework == "npm"

    def test_find_entry_points_package_json_main(self, analyzer):
        """Test detection of main entry in package.json."""
        content = """{
  "main": "dist/index.js"
}"""
        entry_points = analyzer.find_entry_points("package.json", content)
        main_entries = [ep for ep in entry_points if ep.type == "main_entry"]
        assert len(main_entries) == 1
        assert main_entries[0].name == "dist/index.js"

    def test_find_entry_points_package_json_bin(self, analyzer):
        """Test detection of bin scripts in package.json."""
        content = """{
  "bin": {
    "my-cli": "./bin/cli.js",
    "my-tool": "./bin/tool.js"
  }
}"""
        entry_points = analyzer.find_entry_points("package.json", content)
        bin_entries = [ep for ep in entry_points if ep.type == "bin_script"]
        assert len(bin_entries) == 2
        assert any(ep.name == "my-cli" for ep in bin_entries)
        assert any(ep.name == "my-tool" for ep in bin_entries)

    def test_find_entry_points_tsconfig_json(self, analyzer):
        """Test detection of tsconfig.json as TypeScript project."""
        content = """{
  "compilerOptions": {}
}"""
        entry_points = analyzer.find_entry_points("tsconfig.json", content)
        project_entries = [ep for ep in entry_points if ep.type == "project_config"]
        assert len(project_entries) == 1
        assert project_entries[0].framework == "TypeScript"

    def test_find_entry_points_pyproject_toml(self, analyzer):
        """Test detection of pyproject.toml as Python project."""
        content = """[project]
name = "my-package"
version = "0.1.0"
"""
        entry_points = analyzer.find_entry_points("pyproject.toml", content)
        project_entries = [ep for ep in entry_points if ep.type == "project_config"]
        assert len(project_entries) == 1
        assert project_entries[0].framework == "Python"

    def test_find_entry_points_pyproject_toml_scripts(self, analyzer):
        """Test detection of project.scripts section in pyproject.toml."""
        content = """[project.scripts]
my-cli = "my_package:main"
"""
        entry_points = analyzer.find_entry_points("pyproject.toml", content)
        script_entries = [ep for ep in entry_points if ep.type == "scripts_section"]
        assert len(script_entries) == 1

    def test_find_entry_points_cargo_toml(self, analyzer):
        """Test detection of Cargo.toml as Rust project."""
        content = """[package]
name = "my-crate"
version = "0.1.0"
"""
        entry_points = analyzer.find_entry_points("Cargo.toml", content)
        project_entries = [ep for ep in entry_points if ep.type == "project_config"]
        assert len(project_entries) == 1
        assert project_entries[0].framework == "Rust"

    def test_find_entry_points_cargo_toml_bin(self, analyzer):
        """Test detection of [[bin]] targets in Cargo.toml."""
        content = """[[bin]]
name = "my-cli"
path = "src/bin/cli.rs"

[[bin]]
name = "my-tool"
"""
        entry_points = analyzer.find_entry_points("Cargo.toml", content)
        bin_entries = [ep for ep in entry_points if ep.type == "bin_target"]
        assert len(bin_entries) == 2

    def test_find_entry_points_docker_compose(self, analyzer):
        """Test detection of docker-compose.yml as Docker project."""
        content = """version: '3'
services:
  web:
    image: nginx
"""
        entry_points = analyzer.find_entry_points("docker-compose.yml", content)
        project_entries = [ep for ep in entry_points if ep.type == "project_config"]
        assert len(project_entries) == 1
        assert project_entries[0].framework == "Docker"

    def test_find_entry_points_docker_compose_services(self, analyzer):
        """Test detection of services section in docker-compose.yml."""
        content = """version: '3'
services:
  web:
    image: nginx
  db:
    image: postgres
"""
        entry_points = analyzer.find_entry_points("docker-compose.yml", content)
        service_entries = [ep for ep in entry_points if ep.type == "services_section"]
        assert len(service_entries) == 1

    # ===================================================================
    # Classification
    # ===================================================================

    def test_classify_file_all_config(self, analyzer):
        """Test that all config files are classified as config cluster."""
        assert analyzer.classify_file("package.json", "{}") == "config"
        assert analyzer.classify_file("tsconfig.json", "{}") == "config"
        assert analyzer.classify_file("pyproject.toml", "") == "config"
        assert analyzer.classify_file("docker-compose.yml", "") == "config"
        assert analyzer.classify_file("config.ini", "") == "config"

    # ===================================================================
    # Edge cases
    # ===================================================================

    def test_extract_imports_malformed_json(self, analyzer):
        """Test that malformed JSON doesn't crash the analyzer."""
        content = """{
  "invalid": "json
  missing closing brace
"""
        imports = analyzer.extract_imports("broken.json", content)
        # Should return generic path patterns if any, but not crash
        assert isinstance(imports, list)

    def test_extract_imports_empty_file(self, analyzer):
        """Test that empty files return empty imports."""
        imports = analyzer.extract_imports("empty.json", "")
        assert imports == []

    def test_find_entry_points_empty_file(self, analyzer):
        """Test that empty files return empty entry points."""
        entry_points = analyzer.find_entry_points("empty.json", "")
        assert entry_points == []

    def test_extract_imports_multiline_yaml(self, analyzer):
        """Test extraction from multiline YAML structures."""
        content = """version: '3'
services:
  web:
    volumes:
      - ./app:/app
      - ./config:/config
    env_file:
      - .env
      - .env.local
"""
        imports = analyzer.extract_imports("docker-compose.yml", content)
        # Should find multiple volume mounts
        volume_imports = [imp for imp in imports if imp.import_type == "volume_mount"]
        assert len(volume_imports) >= 2
