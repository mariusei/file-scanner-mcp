"""Go code analyzer for extracting imports and entry points."""

import re
from pathlib import Path
from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class GoAnalyzer(BaseAnalyzer):
    """
    Analyzer for Go source files.

    Supports: .go

    Layer 1 implementation (regex-based):
    - Import detection (single + grouped)
    - Entry point detection (main package + func main)
    - File classification

    Layer 2 (tree-sitter): Not yet implemented - uses base class defaults
    """

    @classmethod
    def get_extensions(cls) -> list[str]:
        """Go file extensions."""
        return [".go"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "Go"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip Go files that should not be analyzed.

        Go-specific skip patterns:
        - Skip test files (*_test.go) - analyzed separately
        - Skip generated files (*.pb.go, *.gen.go)
        - vendor/ and testdata/ are already filtered by COMMON_SKIP_DIRS
        """
        filename = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # Skip test files (separate cluster)
        if filename.endswith('_test.go'):
            return True  # Keep tests, but classify separately

        # Skip generated protobuf files
        if filename.endswith('.pb.go'):
            return False

        # Skip other generated files
        if filename.endswith('.gen.go') or 'generated' in filename:
            return False

        # Skip vendor (should be caught by COMMON_SKIP_DIRS, but double-check)
        if '/vendor/' in path_lower:
            return False

        return True

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract import statements from Go file.

        Patterns supported:
        - import "package"
        - import alias "package"
        - import ( ... ) (grouped imports)
        """
        imports = []

        # Pattern 1: Single import
        single_import_pattern = r'^\s*import\s+(?:(\w+)\s+)?"([^"]+)"'
        for match in re.finditer(single_import_pattern, content, re.MULTILINE):
            alias = match.group(1)  # Optional alias
            package = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=package,
                    line=line_num,
                    import_type="import",
                    imported_names=[alias] if alias else None,
                )
            )

        # Pattern 2: Grouped imports
        # import (
        #     "fmt"
        #     alias "package"
        # )
        grouped_pattern = r'import\s*\(\s*((?:[^)]+))\s*\)'
        for match in re.finditer(grouped_pattern, content, re.DOTALL):
            import_block = match.group(1)
            block_start_line = content[:match.start()].count('\n') + 1

            # Parse each line in the import block
            for line in import_block.split('\n'):
                line = line.strip()
                if not line or line.startswith('//'):
                    continue

                # Match: alias "package" OR "package"
                import_line_pattern = r'(?:(\w+)\s+)?"([^"]+)"'
                line_match = re.search(import_line_pattern, line)
                if line_match:
                    alias = line_match.group(1)
                    package = line_match.group(2)

                    imports.append(
                        ImportInfo(
                            source_file=file_path,
                            target_module=package,
                            line=block_start_line,
                            import_type="import",
                            imported_names=[alias] if alias else None,
                        )
                    )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in Go file.

        Entry points:
        - func main() in package main
        - init() functions (special Go initialization)
        """
        entry_points = []

        # Check if this is package main
        is_main_package = bool(re.search(r'^\s*package\s+main', content, re.MULTILINE))

        # Pattern 1: func main()
        main_func_pattern = r'^\s*func\s+main\s*\(\s*\)'
        for match in re.finditer(main_func_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            if is_main_package:
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="main_function",
                        line=line_num,
                        name="main",
                    )
                )

        # Pattern 2: init() functions (run before main)
        init_func_pattern = r'^\s*func\s+init\s*\(\s*\)'
        for match in re.finditer(init_func_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="init_function",
                    line=line_num,
                    name="init",
                )
            )

        # Pattern 3: HTTP handlers (common pattern)
        # func (s *Server) HandleXyz(w http.ResponseWriter, r *http.Request)
        handler_pattern = r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\([^)]*http\.ResponseWriter[^)]*\)'
        for match in re.finditer(handler_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            handler_name = match.group(1)
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="http_handler",
                    line=line_num,
                    name=handler_name,
                )
            )

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify Go file into architectural cluster.

        Uses base class heuristics plus Go-specific patterns.
        """
        # Use base class classification (handles common patterns like test_)
        base_cluster = super().classify_file(file_path, content)

        # Go-specific patterns
        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points (main package)
            if name == "main.go":
                return "entry_points"

            # Check package declaration
            is_main_package = bool(re.search(r'^\s*package\s+main', content, re.MULTILINE))
            if is_main_package:
                return "entry_points"

            # Config files
            if name in ["config.go", "settings.go", "env.go"]:
                return "config"

            # Handlers/Controllers
            if "/handlers/" in path_lower or "/controllers/" in path_lower:
                return "core_logic"

            # Models
            if "/models/" in path_lower or name.endswith("_model.go"):
                return "core_logic"

            # Internal packages (Go convention for private code)
            if "/internal/" in path_lower:
                return "core_logic"

        return base_cluster
