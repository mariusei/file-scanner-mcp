"""
Template for creating new language analyzers.

INSTRUCTIONS:
1. Copy this file to {language}_analyzer.py (e.g., rust_analyzer.py)
2. Replace ALL_CAPS placeholders with your language specifics
3. Implement methods marked REQUIRED
4. Optionally implement Layer 2 methods for call graph support
5. Create test file: tests/analyzers/test_{language}_analyzer.py (see below)
6. Delete this docstring and rename class
7. Run tests: uv run pytest tests/analyzers/test_{language}_analyzer.py -v

PHILOSOPHY (Raskt-Enkelt-Pålitelig):
- Prefer regex for simple patterns (fast, readable)
- Use tree-sitter for complex syntax (robust, maintainable)
- No TODOs, no placeholders, no shortcuts
- DRY: Use BaseAnalyzer helpers (_resolve_relative_import, classify_file)
- Complete implementation: handle edge cases, not just happy path
- Multi-line patterns: Use re.MULTILINE and handle line continuations

TWO-TIER FILTERING:
- Tier 1 (skip_patterns.py): Filters directories (.git, node_modules) and
  extensions (.pyc, .dll) BEFORE analyzer sees files
- Tier 2 (should_analyze): Language-specific patterns (minified, generated)
  AFTER directory filtering. Keep this focused on naming patterns only.
"""

import re
from typing import Optional
from pathlib import Path

# CHOOSE ONE:
# Option A: Regex-based (fast, simple languages)
# Option B: tree-sitter-based (complex syntax, better reliability)

# Option B example:
try:
    import tree_sitter_LANGUAGE  # Replace LANGUAGE with actual package name
    from tree_sitter import Language, Parser
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo, DefinitionInfo, CallInfo


class LANGUAGEAnalyzer(BaseAnalyzer):
    """Analyzer for LANGUAGE source files (.EXT1, .EXT2)."""

    def __init__(self):
        """Initialize with tree-sitter parser if available."""
        super().__init__()
        self.parser = None
        if HAS_TREE_SITTER:
            self.parser = Parser()
            self.parser.language = Language(tree_sitter_LANGUAGE.language())

    # ===================================================================
    # REQUIRED: Metadata
    # ===================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        """File extensions for LANGUAGE."""
        return [".EXT1", ".EXT2"]  # e.g., [".rs"] for Rust, [".rb"] for Ruby

    @classmethod
    def get_language_name(cls) -> str:
        """Language name."""
        return "LANGUAGE"  # e.g., "Rust", "Ruby", "Swift"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority (0 = default, higher = preferred)."""
        return 10

    # ===================================================================
    # OPTIONAL: Skip patterns (Tier 2)
    # ===================================================================

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip files that should not be analyzed (Tier 2 filtering).

        IMPORTANT: This is called AFTER Tier 1 filtering (skip_patterns.py).
        - Tier 1 already filtered: .git/, node_modules/, .pyc, .dll, etc.
        - Tier 2 (this method): Language-specific naming patterns

        Examples:
        - Generated files (*.pb.LANGUAGE, *.generated.LANGUAGE)
        - Minified files (*.min.LANGUAGE)
        - Type declarations (*.d.ts for TypeScript)
        - Framework-specific generated files

        NOTE: Check filename/path patterns only, not directory structure
        (directories are handled by Tier 1).
        """
        filename = Path(file_path).name.lower()

        # Example: Skip generated files
        if filename.endswith(('.generated.EXT', '.pb.EXT')):
            return False

        # Example: Skip minified files
        if '.min.' in filename:
            return False

        # Example: Skip if in specific directory (use sparingly)
        # Prefer adding to COMMON_SKIP_DIRS in skip_patterns.py instead
        if 'target/' in file_path.lower():
            return False

        return True

    # ===================================================================
    # REQUIRED: Layer 1 - File-level analysis
    # ===================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract imports from LANGUAGE file.

        IMPLEMENTATION OPTIONS:
        1. Regex (for simple, consistent syntax):
           - Fast, readable, easy to maintain
           - Good for: Python imports, Rust use statements, Go imports

        2. Tree-sitter (for complex syntax):
           - Robust against edge cases (comments, strings, nested syntax)
           - Good for: JavaScript/TypeScript dynamic imports, C++ includes

        CHOOSE based on language complexity, not preference.
        """
        if self.parser and HAS_TREE_SITTER:
            return self._extract_imports_tree_sitter(file_path, content)
        else:
            return self._extract_imports_regex(file_path, content)

    def _extract_imports_regex(self, file_path: str, content: str) -> list[ImportInfo]:
        """Regex-based import extraction (fast, simple)."""
        imports = []

        # Example patterns (REPLACE with your language):
        # Python: import foo, from foo import bar
        # Rust: use foo::bar;
        # Go: import "foo/bar"
        # Ruby: require 'foo'

        # Pattern 1: Simple imports
        # Example: import foo
        pattern1 = r'^\s*IMPORT_KEYWORD\s+([^\s;,]+)'
        for match in re.finditer(pattern1, content, re.MULTILINE):
            module = match.group(1).strip()
            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=module,
                import_type="module",
                line=line
            ))

        # Pattern 2: From-style imports
        # Example: from foo import bar
        pattern2 = r'^\s*FROM_KEYWORD\s+([^\s]+)\s+IMPORT_KEYWORD'
        for match in re.finditer(pattern2, content, re.MULTILINE):
            module = match.group(1).strip()
            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=module,
                import_type="from",
                line=line
            ))

        # Pattern 3: Multi-line grouped imports (e.g., Rust, Go)
        # Example: use foo::{bar, baz};
        # Example: import ( "foo" "bar" )
        # Strategy: Match opening, extract base module, ignore grouped items
        pattern3 = r'^\s*IMPORT_KEYWORD\s+([^\s{;]+)\s*\{[^}]*\}'
        for match in re.finditer(pattern3, content, re.MULTILINE):
            module = match.group(1).strip()
            # Remove grouped items: foo::{bar, baz} -> foo
            module = re.sub(r'\{[^}]*\}', '', module).strip()
            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=module,
                import_type="grouped",
                line=line
            ))

        # Handle relative imports (if applicable)
        for imp in imports:
            if imp.target_module.startswith('.'):
                resolved = self._resolve_relative_import(file_path, imp.target_module)
                if resolved:
                    imp.target_module = resolved

        return imports

    def _extract_imports_tree_sitter(self, file_path: str, content: str) -> list[ImportInfo]:
        """Tree-sitter-based import extraction (robust)."""
        imports = []
        tree = self.parser.parse(bytes(content, 'utf8'))

        # Query for import statements (SYNTAX SPECIFIC)
        # Example tree-sitter node types:
        # - Python: import_statement, import_from_statement
        # - Rust: use_declaration
        # - TypeScript: import_statement
        query = """
        (IMPORT_NODE_TYPE) @import
        """

        # Example implementation:
        def visit(node):
            if node.type == "IMPORT_NODE_TYPE":
                # Extract module name from node
                module_node = node.child_by_field_name("MODULE_FIELD")
                if module_node:
                    module = content[module_node.start_byte:module_node.end_byte]
                    line = node.start_point[0] + 1
                    imports.append(ImportInfo(
                        source_file=file_path,
                        target_module=module,
                        import_type="module",
                        line=line
                    ))

            for child in node.children:
                visit(child)

        visit(tree.root_node)
        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in LANGUAGE file.

        Entry points vary by language:
        - Python: if __name__ == "__main__", main() function
        - Rust: fn main(), #[tokio::main]
        - JavaScript/TypeScript: export default, module.exports
        - Go: func main()
        - Ruby: if __FILE__ == $0
        - Java: public static void main(String[] args)
        """
        entry_points = []

        # Example 1: main() function
        main_pattern = r'^\s*(?:pub\s+)?fn\s+main\s*\('
        for match in re.finditer(main_pattern, content, re.MULTILINE):
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="main_function",
                name="main",
                line=line
            ))

        # Example 2: if __name__ / if __FILE__ patterns
        name_guard_pattern = r'if\s+__(?:name|FILE)__\s*==\s*["\']__main__["\']\s*:'
        for match in re.finditer(name_guard_pattern, content, re.MULTILINE):
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="if_main",
                name="__main__",
                line=line
            ))

        # Example 3: Framework-specific entry points (Flask, Express, etc.)
        # app = Flask(__name__)
        # const app = express()
        framework_pattern = r'(\w+)\s*=\s*(Flask|express|FastAPI)\('
        for match in re.finditer(framework_pattern, content):
            name = match.group(1)
            framework = match.group(2)
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="app_instance",
                name=name,
                framework=framework,
                line=line
            ))

        # Example 4: Exports (JavaScript/TypeScript)
        # export default function
        # module.exports =
        export_pattern = r'^\s*export\s+(?:default\s+)?(?:function|class|const)\s+(\w+)'
        for match in re.finditer(export_pattern, content, re.MULTILINE):
            name = match.group(1)
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="export",
                name=name,
                line=line
            ))

        return entry_points

    # ===================================================================
    # OPTIONAL: Layer 2 - Structure-level analysis (for call graphs)
    # ===================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """
        Extract function/class definitions.

        Only implement if you want call graph support (hot functions).
        Otherwise, return [] (Layer 1 only).

        DEFINITION TYPES:
        - "function": Top-level functions
        - "method": Class/struct methods
        - "class": Classes, structs, interfaces
        """
        if not self.parser or not HAS_TREE_SITTER:
            return []

        definitions = []
        tree = self.parser.parse(bytes(content, 'utf8'))

        def visit(node, parent_name=None):
            # Functions
            if node.type == "FUNCTION_NODE_TYPE":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = content[name_node.start_byte:name_node.end_byte]
                    line = node.start_point[0] + 1

                    # Build FQN (fully qualified name)
                    fqn = f"{file_path}:{parent_name}.{name}" if parent_name else f"{file_path}:{name}"

                    definitions.append(DefinitionInfo(
                        name=fqn,
                        type="method" if parent_name else "function",
                        file=file_path,
                        line=line
                    ))

            # Classes/Structs
            if node.type in ("CLASS_NODE_TYPE", "STRUCT_NODE_TYPE"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = content[name_node.start_byte:name_node.end_byte]
                    line = node.start_point[0] + 1

                    definitions.append(DefinitionInfo(
                        name=f"{file_path}:{class_name}",
                        type="class",
                        file=file_path,
                        line=line
                    ))

                    # Recursively visit methods inside class
                    for child in node.children:
                        visit(child, parent_name=class_name)
                    return  # Don't visit children again

            for child in node.children:
                visit(child, parent_name)

        visit(tree.root_node)
        return definitions

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """
        Extract function/method calls.

        Only implement if you want call graph support (hot functions).
        Otherwise, return [] (Layer 1 only).

        STRATEGY:
        1. Build local name map from definitions (function name -> FQN)
        2. Find all call expressions
        3. Match call names to FQN using local map
        """
        if not self.parser or not HAS_TREE_SITTER:
            return []

        calls = []
        tree = self.parser.parse(bytes(content, 'utf8'))

        # Build local name map: short name -> FQN
        name_map = {}
        for defn in definitions:
            # Extract short name from FQN
            short_name = defn.name.split(':')[-1].split('.')[-1]
            name_map[short_name] = defn.name

        def visit(node):
            if node.type == "CALL_NODE_TYPE":
                func_node = node.child_by_field_name("function")
                if func_node:
                    func_name = content[func_node.start_byte:func_node.end_byte]
                    line = node.start_point[0] + 1

                    # Try to resolve to FQN
                    target_fqn = name_map.get(func_name, func_name)

                    calls.append(CallInfo(
                        caller="",  # Will be filled by call_graph.py
                        callee=target_fqn,
                        file=file_path,
                        line=line
                    ))

            for child in node.children:
                visit(child)

        visit(tree.root_node)
        return calls

    # ===================================================================
    # OPTIONAL: Custom classification
    # ===================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify file into architectural cluster.

        Override only if you have language-specific classification needs.
        Otherwise, BaseAnalyzer.classify_file() provides good defaults.
        """
        # Custom classification example:
        if "LANGUAGE-SPECIFIC-PATTERN" in content:
            return "special_cluster"

        # Fall back to base implementation
        return super().classify_file(file_path, content)


# ═══════════════════════════════════════════════════════════════════
# USAGE CHECKLIST
# ═══════════════════════════════════════════════════════════════════
#
# ✓ Replace ALL_CAPS placeholders with actual values
# ✓ Implement extract_imports() - REQUIRED
# ✓ Implement find_entry_points() - REQUIRED
# ✓ Implement should_analyze() - RECOMMENDED
# ✓ Implement extract_definitions() - OPTIONAL (for call graphs)
# ✓ Implement extract_calls() - OPTIONAL (for call graphs)
# ✓ Delete this template docstring
# ✓ Write tests in tests/analyzers/test_LANGUAGE_analyzer.py (see below)
# ✓ Test with real code samples
# ✓ Verify auto-discovery: should appear in get_registry().get_supported_extensions()
#
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════
# TEST TEMPLATE: tests/analyzers/test_LANGUAGE_analyzer.py
# ═══════════════════════════════════════════════════════════════════
#
# Create this file following the structure below. Use pytest fixtures
# for analyzer instances and write one test per feature.
#
# """Tests for LANGUAGE analyzer."""
#
# import pytest
# from scantool.analyzers.LANGUAGE_analyzer import LANGUAGEAnalyzer
# from scantool.analyzers.models import ImportInfo, EntryPointInfo
#
#
# @pytest.fixture
# def analyzer():
#     """Create LANGUAGE analyzer instance."""
#     return LANGUAGEAnalyzer()
#
#
# class TestLANGUAGEAnalyzer:
#     """Test suite for LANGUAGE analyzer."""
#
#     def test_extensions(self, analyzer):
#         """Test that analyzer supports correct extensions."""
#         extensions = analyzer.get_extensions()
#         assert ".EXT1" in extensions
#
#     def test_language_name(self, analyzer):
#         """Test language name."""
#         assert analyzer.get_language_name() == "LANGUAGE"
#
#     def test_extract_imports_simple(self, analyzer):
#         """Test extraction of simple import statements."""
#         content = """
#         IMPORT_KEYWORD foo
#         IMPORT_KEYWORD bar.baz
#         """
#         imports = analyzer.extract_imports("test.EXT1", content)
#         assert len(imports) == 2
#         assert any(imp.target_module == "foo" for imp in imports)
#         assert any(imp.target_module == "bar.baz" for imp in imports)
#
#     def test_extract_imports_grouped(self, analyzer):
#         """Test extraction of grouped imports."""
#         content = """
#         IMPORT_KEYWORD foo::{bar, baz}
#         """
#         imports = analyzer.extract_imports("test.EXT1", content)
#         assert len(imports) == 1
#         assert imports[0].target_module == "foo"
#         assert imports[0].import_type == "grouped"
#
#     def test_find_entry_points_main(self, analyzer):
#         """Test detection of main() function."""
#         content = """
#         fn main() {
#             println!("Hello");
#         }
#         """
#         entry_points = analyzer.find_entry_points("test.EXT1", content)
#         main_entries = [ep for ep in entry_points if ep.type == "main_function"]
#         assert len(main_entries) == 1
#         assert main_entries[0].name == "main"
#
#     def test_should_analyze_skip_generated(self, analyzer):
#         """Test that generated files are skipped."""
#         assert analyzer.should_analyze("file.pb.EXT1") is False
#         assert analyzer.should_analyze("file.generated.EXT1") is False
#         assert analyzer.should_analyze("normal.EXT1") is True
#
#     def test_should_analyze_skip_minified(self, analyzer):
#         """Test that minified files are skipped."""
#         assert analyzer.should_analyze("app.min.EXT1") is False
#         assert analyzer.should_analyze("app.EXT1") is True
#
#
# # Run tests:
# # uv run pytest tests/analyzers/test_LANGUAGE_analyzer.py -v
#
# # Run with coverage:
# # uv run pytest tests/analyzers/test_LANGUAGE_analyzer.py --cov=src/scantool/analyzers
#
# ═══════════════════════════════════════════════════════════════════
