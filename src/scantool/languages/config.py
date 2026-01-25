"""Config language support - analyzer for configuration files.

This module provides ConfigLanguage for analyzing configuration files
(.json, .yaml, .yml, .toml, .ini). Since config files don't have
traditional code structure, scan() returns an empty list.

Key functionality:
- extract_imports(): Extract file path references from config files
- find_entry_points(): Find project configs, scripts sections, etc.
- classify_file(): All config files go to "config" cluster
"""

import re
import json
from typing import Optional
from pathlib import Path

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class ConfigLanguage(BaseLanguage):
    """Language handler for configuration files (.json, .yaml, .yml, .toml, .ini).

    Config files don't have traditional code structure (classes, functions),
    so scan() returns an empty list. The primary value is in:
    - extract_imports(): Find file path references
    - find_entry_points(): Find project configs and scripts
    """

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        """Configuration file extensions."""
        return [".json", ".yaml", ".yml", ".toml", ".ini"]

    @classmethod
    def get_language_name(cls) -> str:
        """Language name."""
        return "Config"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    # ===========================================================================
    # Skip Logic
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip config files that should not be scanned."""
        filename_lower = filename.lower()

        # Skip lock files
        if filename_lower in ('package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'cargo.lock'):
            return True

        # Skip if ends with .lock
        if filename_lower.endswith('.lock'):
            return True

        # Skip minified
        if '.min.' in filename_lower:
            return True

        return False

    def should_analyze(self, file_path: str) -> bool:
        """Skip config files that should not be analyzed."""
        filename = Path(file_path).name.lower()

        # Skip lock files
        if filename in ('package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'cargo.lock'):
            return False

        # Skip if ends with .lock
        if filename.endswith('.lock'):
            return False

        # Skip minified
        if '.min.' in filename:
            return False

        return True

    # ===========================================================================
    # Structure Scanning
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan config file - returns empty list as configs don't have code structure."""
        # Config files don't have traditional code structure (classes, functions)
        # Return empty list rather than None to indicate successful parse
        return []

    # ===========================================================================
    # Semantic Analysis - Layer 1
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract file path references from config files.

        Handles:
        - JSON: tsconfig paths, package.json scripts with file refs
        - YAML: docker-compose volumes, env_file, Dockerfile paths
        - TOML: pyproject.toml paths, Cargo.toml paths
        - File path patterns in string values

        Does NOT extract:
        - Package names (npm, cargo, pip - these are registry names, not file imports)
        """
        imports = []
        filename = Path(file_path).name.lower()

        # Detect file type
        if filename.endswith('.json'):
            imports.extend(self._extract_json_imports(file_path, content))
        elif filename.endswith(('.yaml', '.yml')):
            imports.extend(self._extract_yaml_imports(file_path, content))
        elif filename.endswith('.toml'):
            imports.extend(self._extract_toml_imports(file_path, content))
        elif filename.endswith('.ini'):
            imports.extend(self._extract_ini_imports(file_path, content))

        # Generic file path pattern extraction (all config types)
        imports.extend(self._extract_path_patterns(file_path, content))

        return imports

    def _extract_json_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from JSON config files."""
        imports = []
        filename = Path(file_path).name.lower()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return imports

        # tsconfig.json specific
        if filename == 'tsconfig.json':
            # "extends": "./base.json"
            if 'extends' in data and isinstance(data['extends'], str):
                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=data['extends'],
                    line=self._find_line(content, data['extends']),
                    import_type="extends"
                ))

            # "files": ["src/index.ts", ...]
            if 'files' in data and isinstance(data['files'], list):
                for file_ref in data['files']:
                    if isinstance(file_ref, str):
                        imports.append(ImportInfo(
                            source_file=file_path,
                            target_module=file_ref,
                            line=self._find_line(content, file_ref),
                            import_type="file_reference"
                        ))

            # "include": ["src/**/*"]
            if 'include' in data and isinstance(data['include'], list):
                for pattern in data['include']:
                    if isinstance(pattern, str) and not pattern.startswith('*'):
                        imports.append(ImportInfo(
                            source_file=file_path,
                            target_module=pattern,
                            line=self._find_line(content, pattern),
                            import_type="include_pattern"
                        ))

            # "paths": {"@/*": ["./src/*"]}
            if 'compilerOptions' in data and 'paths' in data['compilerOptions']:
                paths = data['compilerOptions']['paths']
                if isinstance(paths, dict):
                    for alias, path_list in paths.items():
                        if isinstance(path_list, list):
                            for path in path_list:
                                if isinstance(path, str):
                                    imports.append(ImportInfo(
                                        source_file=file_path,
                                        target_module=path,
                                        line=self._find_line(content, path),
                                        import_type="path_mapping"
                                    ))

        # package.json - only extract file paths from scripts, not dependencies
        elif filename == 'package.json':
            # Scripts might reference local files
            if 'scripts' in data and isinstance(data['scripts'], dict):
                for script_name, script_cmd in data['scripts'].items():
                    if isinstance(script_cmd, str):
                        # Extract file paths from scripts (e.g., "node build.js", "node ./scripts/test.mjs")
                        # Match files with or without ./ prefix
                        file_refs = re.findall(r'\b(?:\./)?[\w/.-]+\.(?:js|ts|mjs|cjs|json|jsx|tsx)\b', script_cmd)
                        for ref in file_refs:
                            imports.append(ImportInfo(
                                source_file=file_path,
                                target_module=ref,
                                line=self._find_line(content, ref),
                                import_type="script_file"
                            ))

        return imports

    def _extract_yaml_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from YAML config files."""
        imports = []
        filename = Path(file_path).name.lower()

        # docker-compose.yml patterns
        if 'docker-compose' in filename:
            # env_file: .env.production or env_file: .env
            env_file_pattern = r'env_file:\s*["\']?(\.env[^\s"\']*)["\']?'
            for match in re.finditer(env_file_pattern, content):
                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[:match.start()].count('\n') + 1,
                    import_type="env_file"
                ))

            # dockerfile: ./Dockerfile.prod
            dockerfile_pattern = r'dockerfile:\s*["\']?([^\s"\']+Dockerfile[^\s"\']*)["\']?'
            for match in re.finditer(dockerfile_pattern, content, re.IGNORECASE):
                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[:match.start()].count('\n') + 1,
                    import_type="dockerfile"
                ))

            # volumes: - ./data:/app/data
            volume_pattern = r'[-\s]+["\']?(\.{1,2}/[^:\s"\']+):[^\s"\']+["\']?'
            for match in re.finditer(volume_pattern, content):
                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[:match.start()].count('\n') + 1,
                    import_type="volume_mount"
                ))

        return imports

    def _extract_toml_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from TOML config files."""
        imports = []
        filename = Path(file_path).name.lower()

        # pyproject.toml - extract script paths, not package dependencies
        if filename == 'pyproject.toml':
            # [tool.mypy] config files
            config_pattern = r'config_file\s*=\s*["\']([^"\']+)["\']'
            for match in re.finditer(config_pattern, content):
                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[:match.start()].count('\n') + 1,
                    import_type="config_file"
                ))

        # Cargo.toml - path dependencies (local crates)
        elif filename == 'cargo.toml':
            # my_crate = { path = "../my_crate" }
            path_dep_pattern = r'path\s*=\s*["\']([^"\']+)["\']'
            for match in re.finditer(path_dep_pattern, content):
                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=match.group(1),
                    line=content[:match.start()].count('\n') + 1,
                    import_type="path_dependency"
                ))

        return imports

    def _extract_ini_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from INI config files."""
        imports = []

        # INI files may have file path values
        # key = /path/to/file or key = ./relative/path
        ini_path_pattern = r'^\s*[\w_-]+\s*=\s*(["\']?)([./][^\s"\']+\.[a-zA-Z0-9]+)\1'
        for match in re.finditer(ini_path_pattern, content, re.MULTILINE):
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=match.group(2),
                line=content[:match.start()].count('\n') + 1,
                import_type="config_value"
            ))

        return imports

    def _extract_path_patterns(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract generic file path patterns from config files.

        Conservative patterns:
        - Relative paths: ./file.ext, ../file.ext
        - Quoted paths with extensions
        - Avoid matching URLs, version numbers, or package names
        """
        imports = []

        # Pattern 1: Relative paths with common extensions (in quotes)
        # Matches: "./config.json", "../utils/helper.ts", "./templates/base.html", etc.
        quoted_path_pattern = r'["\'](\./(?:[^/"\s]+/)*[^/"\s]+\.[a-zA-Z0-9]+|\.\./(?:[^/"\s]+/)*[^/"\s]+\.[a-zA-Z0-9]+)["\']'
        for match in re.finditer(quoted_path_pattern, content):
            path = match.group(1)
            # Skip if looks like URL
            if '://' not in path:
                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=path,
                    line=content[:match.start()].count('\n') + 1,
                    import_type="path_reference"
                ))

        # Pattern 2: Unquoted relative paths on their own line (YAML-style)
        # Matches: "  - ./file.ext" or "key: ./file.ext"
        unquoted_path_pattern = r'(?:^|\s)(\./[^\s:]+\.[a-zA-Z0-9]+|\.\./(?:[^/\s]+/)*[^/\s]+\.[a-zA-Z0-9]+)(?:\s|$)'
        for match in re.finditer(unquoted_path_pattern, content, re.MULTILINE):
            path = match.group(1)
            if '://' not in path:
                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=path,
                    line=content[:match.start()].count('\n') + 1,
                    import_type="path_reference"
                ))

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in config files.

        Entry points:
        - package.json: main, bin scripts
        - Cargo.toml: [[bin]] targets
        - pyproject.toml: [project.scripts]
        - docker-compose.yml: services
        - tsconfig.json: project config
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        try:
            # JSON configs
            if filename.endswith('.json'):
                entry_points.extend(self._find_json_entry_points(file_path, content))

            # TOML configs
            elif filename.endswith('.toml'):
                entry_points.extend(self._find_toml_entry_points(file_path, content))

            # YAML configs
            elif filename.endswith(('.yaml', '.yml')):
                entry_points.extend(self._find_yaml_entry_points(file_path, content))

        except Exception:
            # Don't fail on parse errors
            pass

        return entry_points

    def _find_json_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in JSON config files."""
        entry_points = []
        filename = Path(file_path).name.lower()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return entry_points

        # package.json
        if filename == 'package.json':
            # Mark as npm/node project
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="project_config",
                name="npm_project",
                line=1,
                framework="npm"
            ))

            # main entry point
            if 'main' in data:
                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="main_entry",
                    name=data['main'],
                    line=self._find_line(content, data['main']),
                    framework="npm"
                ))

            # bin scripts
            if 'bin' in data:
                if isinstance(data['bin'], dict):
                    for bin_name, bin_path in data['bin'].items():
                        entry_points.append(EntryPointInfo(
                            file=file_path,
                            type="bin_script",
                            name=bin_name,
                            line=self._find_line(content, bin_name),
                            framework="npm"
                        ))

        # tsconfig.json
        elif filename == 'tsconfig.json':
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="project_config",
                name="typescript_project",
                line=1,
                framework="TypeScript"
            ))

        return entry_points

    def _find_toml_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in TOML config files."""
        entry_points = []
        filename = Path(file_path).name.lower()

        # pyproject.toml
        if filename == 'pyproject.toml':
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="project_config",
                name="python_project",
                line=1,
                framework="Python"
            ))

            # [project.scripts]
            script_pattern = r'\[project\.scripts\]'
            match = re.search(script_pattern, content)
            if match:
                line = content[:match.start()].count('\n') + 1
                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="scripts_section",
                    name="project_scripts",
                    line=line,
                    framework="Python"
                ))

        # Cargo.toml
        elif filename == 'cargo.toml':
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="project_config",
                name="rust_project",
                line=1,
                framework="Rust"
            ))

            # [[bin]]
            bin_pattern = r'\[\[bin\]\]'
            for match in re.finditer(bin_pattern, content):
                line = content[:match.start()].count('\n') + 1
                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="bin_target",
                    name="bin",
                    line=line,
                    framework="Rust"
                ))

        return entry_points

    def _find_yaml_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in YAML config files."""
        entry_points = []
        filename = Path(file_path).name.lower()

        # docker-compose.yml
        if 'docker-compose' in filename:
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="project_config",
                name="docker_compose_project",
                line=1,
                framework="Docker"
            ))

            # services:
            services_pattern = r'^services:\s*$'
            for match in re.finditer(services_pattern, content, re.MULTILINE):
                line = content[:match.start()].count('\n') + 1
                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="services_section",
                    name="services",
                    line=line,
                    framework="Docker"
                ))

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Config files don't have traditional definitions."""
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Config files don't have function calls."""
        return []

    # ===========================================================================
    # Classification
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """All config files go to config cluster."""
        return "config"

    # ===========================================================================
    # CodeMap Integration
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> Optional[str]:
        """Resolve config file reference to file path.

        Config files reference other files directly by path, so resolution
        is straightforward path matching.
        """
        # Direct path match
        if module in all_files:
            return module

        # Try relative to source file directory
        source_dir = str(Path(source_file).parent)
        if source_dir != ".":
            candidate = f"{source_dir}/{module}"
            if candidate in all_files:
                return candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format config entry point for display.

        Formats:
        - python_project: "pyproject.toml project"
        - npm_project: "package.json project"
        - docker_service: "docker-compose.yml service"
        """
        if ep.type == "python_project":
            return f"  {ep.file}:python_project @{ep.line}"
        elif ep.type == "npm_project":
            return f"  {ep.file}:npm_project @{ep.line}"
        elif ep.type == "docker_service":
            return f"  {ep.file}:docker {ep.name} @{ep.line}"
        elif ep.type == "project_scripts":
            return f"  {ep.file}:project_scripts @{ep.line}"
        else:
            return super().format_entry_point(ep)

    # ===========================================================================
    # Helper methods
    # ===========================================================================

    def _find_line(self, content: str, search_str: str) -> int:
        """Find line number of a string in content."""
        try:
            index = content.index(search_str)
            return content[:index].count('\n') + 1
        except ValueError:
            return 0
