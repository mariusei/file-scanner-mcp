"""Rust code analyzer for extracting imports, entry points, and structure."""

import re
from typing import Optional
from pathlib import Path

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo, DefinitionInfo, CallInfo


class RustAnalyzer(BaseAnalyzer):
    """Analyzer for Rust source files (.rs)."""

    def __init__(self):
        """Initialize Rust analyzer."""
        super().__init__()

    # ===================================================================
    # REQUIRED: Metadata
    # ===================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        """File extensions for Rust."""
        return [".rs"]

    @classmethod
    def get_language_name(cls) -> str:
        """Language name."""
        return "Rust"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority (0 = default, higher = preferred)."""
        return 10

    # ===================================================================
    # OPTIONAL: Skip patterns
    # ===================================================================

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip files that should not be analyzed.

        Skips:
        - Generated protobuf files (*.pb.rs)
        - Files in target/ directory (build artifacts)
        - build.rs in target/ (build script output)
        """
        path = Path(file_path)
        filename = path.name.lower()

        # Skip generated protobuf files
        if filename.endswith('.pb.rs'):
            return False

        # Skip files in target/ directory
        if 'target' in path.parts:
            return False

        return True

    # ===================================================================
    # REQUIRED: Layer 1 - File-level analysis
    # ===================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract imports from Rust file.

        Rust import patterns:
        - use std::collections::HashMap;
        - use crate::module::Type;
        - use super::parent;
        - use self::current;
        - use foo::{bar, baz};  (multiple imports)
        - use foo::bar as baz;  (aliased imports)
        """
        imports = []

        # Pattern for use statements
        # Matches: use path::to::module;
        #          use path::{item1, item2};
        #          use path::item as alias;
        use_pattern = r'^\s*(?:pub\s+)?use\s+((?:std|crate|super|self|::)?[\w:]+(?:::\{[^}]+\})?(?:\s+as\s+\w+)?)\s*;'

        for match in re.finditer(use_pattern, content, re.MULTILINE):
            use_path = match.group(1).strip()
            line = content[:match.start()].count('\n') + 1

            # Handle grouped imports: use foo::{bar, baz}
            if '::{}' in use_path or '::{' in use_path:
                # Extract base path and items
                brace_match = re.match(r'([\w:]+)::\{([^}]+)\}', use_path)
                if brace_match:
                    base_path = brace_match.group(1)
                    items_str = brace_match.group(2)

                    # Parse individual items
                    imported_names = []
                    for item in items_str.split(','):
                        item = item.strip()
                        if ' as ' in item:
                            name, _ = item.split(' as ')
                            imported_names.append(name.strip())
                        else:
                            imported_names.append(item)

                    imports.append(ImportInfo(
                        source_file=file_path,
                        target_module=base_path,
                        import_type="use",
                        line=line,
                        imported_names=imported_names
                    ))
                    continue

            # Handle aliased imports: use foo::bar as baz
            if ' as ' in use_path:
                module_part, alias = use_path.split(' as ')
                module_part = module_part.strip()

                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=module_part,
                    import_type="use_as",
                    line=line,
                    imported_names=[alias.strip()]
                ))
                continue

            # Simple use statement
            import_type = "use"
            if use_path.startswith('super::'):
                import_type = "relative"
            elif use_path.startswith('self::'):
                import_type = "relative"
            elif use_path.startswith('crate::'):
                import_type = "crate"
            elif use_path.startswith('::'):
                import_type = "absolute"
            elif use_path.startswith('std::'):
                import_type = "std"

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=use_path,
                import_type=import_type,
                line=line,
                imported_names=[]
            ))

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in Rust file.

        Entry points:
        - fn main() - standard entry point
        - #[tokio::main] - async Tokio entry point
        - #[async_std::main] - async async-std entry point
        - #[actix_web::main] - Actix Web entry point
        - #[test] functions (test entry points)
        - #[bench] functions (benchmark entry points)
        """
        entry_points = []

        # Pattern 1: Standard fn main()
        main_pattern = r'^\s*(?:pub\s+)?fn\s+main\s*\('
        for match in re.finditer(main_pattern, content, re.MULTILINE):
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="main_function",
                name="main",
                line=line
            ))

        # Pattern 2: Async framework entry points
        # Look for #[framework::main] followed by fn main() or async fn main()
        async_main_pattern = r'#\[(tokio|async_std|actix_web)::(main|test)\]\s*(?:async\s+)?fn\s+(\w+)'
        for match in re.finditer(async_main_pattern, content, re.MULTILINE):
            framework = match.group(1)
            decorator_type = match.group(2)
            func_name = match.group(3)
            line = content[:match.start()].count('\n') + 1

            entry_points.append(EntryPointInfo(
                file=file_path,
                type="async_main" if decorator_type == "main" else "async_test",
                name=func_name,
                line=line,
                framework=framework
            ))

        # Pattern 3: Test functions
        # #[test] or #[cfg(test)]
        test_pattern = r'#\[(?:cfg\(test\)|test)\]\s*(?:async\s+)?fn\s+(\w+)'
        for match in re.finditer(test_pattern, content, re.MULTILINE):
            func_name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            entry_points.append(EntryPointInfo(
                file=file_path,
                type="test",
                name=func_name,
                line=line
            ))

        # Pattern 4: Benchmark functions
        bench_pattern = r'#\[bench\]\s*fn\s+(\w+)'
        for match in re.finditer(bench_pattern, content):
            func_name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            entry_points.append(EntryPointInfo(
                file=file_path,
                type="benchmark",
                name=func_name,
                line=line
            ))

        # Pattern 5: lib.rs public API exports (if file is lib.rs)
        if file_path.endswith('lib.rs'):
            # Look for pub mod statements
            pub_mod_pattern = r'^\s*pub\s+mod\s+(\w+)\s*;'
            for match in re.finditer(pub_mod_pattern, content, re.MULTILINE):
                mod_name = match.group(1)
                line = content[:match.start()].count('\n') + 1

                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="export",
                    name=f"mod {mod_name}",
                    line=line
                ))

            # Look for pub use re-exports
            pub_use_pattern = r'^\s*pub\s+use\s+([\w:]+)'
            for match in re.finditer(pub_use_pattern, content, re.MULTILINE):
                use_path = match.group(1)
                line = content[:match.start()].count('\n') + 1

                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="export",
                    name=f"pub use {use_path}",
                    line=line
                ))

        return entry_points

    # ===================================================================
    # OPTIONAL: Layer 2 - Structure-level analysis (for call graphs)
    # ===================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """
        Extract function/struct/enum definitions.

        For Layer 1, we return empty list. Full implementation would require
        tree-sitter for robust parsing of Rust's complex syntax.
        """
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """
        Extract function calls.

        For Layer 1, we return empty list. Full implementation would require
        tree-sitter for robust parsing of Rust's complex syntax.
        """
        return []

    # ===================================================================
    # OPTIONAL: Custom classification
    # ===================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify Rust file into architectural cluster.

        Rust-specific patterns:
        - main.rs -> entry_points
        - lib.rs -> entry_points
        - tests/ directory -> tests
        - benches/ directory -> tests (benchmarks)
        - mod.rs -> infrastructure (module organization)
        """
        path = Path(file_path)
        filename = path.name

        # Check for standard Rust entry points
        if filename in ('main.rs', 'lib.rs'):
            return "entry_points"

        # Check directory structure
        if 'tests' in path.parts or filename.startswith('test_'):
            return "tests"

        if 'benches' in path.parts or filename.startswith('bench_'):
            return "tests"

        if filename == 'mod.rs':
            return "infrastructure"

        # Check content patterns
        if '#[test]' in content or '#[cfg(test)]' in content:
            return "tests"

        if '#[bench]' in content:
            return "tests"

        if 'fn main(' in content:
            return "entry_points"

        # Fall back to base implementation
        return super().classify_file(file_path, content)
