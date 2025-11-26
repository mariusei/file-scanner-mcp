# Contributing to File Scanner MCP

This guide covers how to add support for a new programming language.

**Two systems for different purposes:**
- **Scanners** (this guide): Extract file structure (classes, functions, methods) for scan_file/scan_directory
- **Analyzers** (see below): Extract imports, entry points, calls for code map and preview_directory

## Adding a New Language

The plugin system auto-discovers scanners. Create one file with the required methods and it will be automatically registered.

### Step 1: Copy the Template

```bash
cp src/scantool/scanners/_template.py src/scantool/scanners/YOUR_LANGUAGE_scanner.py
```

### Step 2: Fill in the Blanks

Edit your new file and implement 3 required methods:

```python
@classmethod
def get_extensions(cls) -> list[str]:
    return [".your", ".ext"]  # File extensions you handle

@classmethod
def get_language_name(cls) -> str:
    return "YourLanguage"  # Human-readable name

def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
    # Your parsing logic here
    pass
```

### Step 3: Test It

```bash
uv run python -c "
from scantool.scanner import FileScanner
scanner = FileScanner()
print(scanner.scan_file('tests/yourlang/samples/basic.your'))
"
```

The scanner will be automatically discovered and registered.

---

## Complete Example: Adding Ruby Support

Here's a full walkthrough of adding Ruby (`.rb`) support:

### 1. Create the Scanner File

**File**: `src/scantool/scanners/ruby_scanner.py`

```python
"""Ruby language scanner."""

from typing import Optional
import tree_sitter_ruby  # pip install tree-sitter-ruby
from tree_sitter import Language, Parser

from .base import BaseScanner, StructureNode


class RubyScanner(BaseScanner):
    """Scanner for Ruby files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_ruby.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".rb"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Ruby"

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Ruby source code."""
        try:
            tree = self.parser.parse(source_code)

            # Check for too many errors
            if self._should_use_fallback(tree.root_node):
                return self._fallback_extract(source_code)

            return self._extract_structure(tree.root_node, source_code)
        except Exception as e:
            return [StructureNode(
                type="error",
                name=f"Failed to parse: {str(e)}",
                start_line=1,
                end_line=1
            )]

    def _extract_structure(self, root, source_code: bytes):
        """Extract Ruby classes, methods, etc."""
        structures = []

        def traverse(node, parent_structures):
            # Handle errors gracefully
            if node.type == "ERROR":
                if self.show_errors:
                    parent_structures.append(StructureNode(
                        type="parse-error",
                        name="⚠ invalid syntax",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1
                    ))
                return

            # Extract classes
            if node.type == "class":
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                class_node = StructureNode(
                    type="class",
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    children=[]
                )
                parent_structures.append(class_node)

                # Recurse into children
                for child in node.children:
                    traverse(child, class_node.children)

            # Extract methods
            elif node.type == "method":
                name_node = node.child_by_field_name("name")
                name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

                # Get parameters
                params_node = node.child_by_field_name("parameters")
                signature = None
                if params_node:
                    params_text = self._get_node_text(params_node, source_code)
                    signature = f"({params_text})"

                method_node = StructureNode(
                    type="method",
                    name=name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    signature=signature,
                    children=[]
                )
                parent_structures.append(method_node)

            else:
                # Keep traversing
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _fallback_extract(self, source_code: bytes):
        """Regex fallback for broken files."""
        import re
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find classes
        for match in re.finditer(r'^class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find methods
        for match in re.finditer(r'^def\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        return structures
```

### 2. Add Dependencies

```toml
# Add to pyproject.toml dependencies:
"tree-sitter-ruby>=0.23.0",
```

Then run:
```bash
uv sync
```

### 3. Create Test Files

**Directory structure**: `tests/ruby/samples/basic.rb`

```ruby
class UserManager
  def initialize(database)
    @database = database
  end

  def create_user(name, email)
    @database.insert(name: name, email: email)
  end

  def find_user(id)
    @database.find(id)
  end
end

def validate_email(email)
  email.include?("@")
end
```

### 4. Create Scanner Test

**File**: `tests/ruby/test_ruby.py`

```python
"""Tests for Ruby scanner."""

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic Ruby file parsing."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")
    assert structures is not None, "Should parse Ruby file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected structures
    assert any(s.type == "class" and s.name == "UserManager" for s in structures)


def test_signatures(file_scanner):
    """Test that method signatures are extracted."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")

    # Find UserManager class
    user_manager = next((s for s in structures if s.type == "class" and s.name == "UserManager"), None)
    assert user_manager is not None, "Should find UserManager"
    assert len(user_manager.children) > 0, "Should have methods"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)

    # Should not crash on broken files
    structures = scanner.scan_file("tests/ruby/samples/broken.rb")
    assert structures is not None, "Should return structures even for broken code"
```

### 5. Run Tests

Run tests for your language:
```bash
uv run pytest tests/ruby/
```

Run a specific test:
```bash
uv run pytest tests/ruby/test_ruby.py::test_basic_parsing
```

Run all tests:
```bash
uv run pytest
```

Run with coverage:
```bash
uv run pytest --cov=src/scantool
```

---

## Architecture Overview

```
src/scantool/
├── scanners/
│   ├── __init__.py          # Auto-discovery (don't modify)
│   ├── base.py              # BaseScanner class (utilities)
│   ├── _template.py         # Copy this to start
│   ├── python_scanner.py    # Example: full-featured
│   ├── text_scanner.py      # Example: simple (no tree-sitter)
│   └── YOUR_scanner.py      # Your new scanner!
├── scanner.py               # Main orchestrator
├── formatter.py             # Output formatting
└── server.py                # MCP server tools
```

---

## Advanced Features

### Extracting Signatures with Types

```python
def _extract_signature(self, node, source_code):
    """Get function signature with type annotations."""
    parts = []

    # Parameters
    params = node.child_by_field_name("parameters")
    if params:
        parts.append(self._get_node_text(params, source_code))

    # Return type
    return_type = node.child_by_field_name("return_type")
    if return_type:
        type_text = self._get_node_text(return_type, source_code).strip()
        parts.append(f" -> {type_text}")

    return "".join(parts) if parts else None
```

### Extracting Decorators

```python
def _extract_decorators(self, node, source_code):
    """Get decorators above a function/class."""
    decorators = []
    prev = node.prev_sibling

    while prev and prev.type == "decorator":
        dec_text = self._get_node_text(prev, source_code).strip()
        decorators.insert(0, dec_text)
        prev = prev.prev_sibling

    return decorators
```

### Extracting Docstrings

```python
def _extract_docstring(self, node, source_code):
    """Get first line of docstring."""
    body = node.child_by_field_name("body")
    if body and len(body.children) > 0:
        first_stmt = body.children[0]
        if first_stmt.type == "expression_statement":
            for child in first_stmt.children:
                if child.type == "string":
                    doc = self._get_node_text(child, source_code)
                    # Clean and get first line
                    doc = doc.strip('"""').strip("'''").split('\n')[0].strip()
                    return doc if doc else None
    return None
```

### Calculating Complexity

```python
# Built into BaseScanner - just call it:
complexity = self._calculate_complexity(node)
# Returns: {"lines": int, "max_depth": int, "branches": int}
```

---

## Checklist for New Scanners

- [ ] Create `src/scantool/scanners/LANG_scanner.py`
- [ ] Implement required methods: `get_extensions()`, `get_language_name()`, `scan()`
- [ ] Add tree-sitter dependency to `pyproject.toml`
- [ ] Create test directory: `tests/LANG/samples/`
- [ ] Create test file: `tests/LANG/samples/basic.EXT`
- [ ] Create scanner test: `tests/LANG/test_LANG.py`
- [ ] Run tests: `uv run pytest tests/LANG/`
- [ ] Add entry to README.md supported languages table
- [ ] (Optional) Add signature extraction
- [ ] (Optional) Add decorator extraction
- [ ] (Optional) Add docstring extraction
- [ ] (Optional) Add fallback regex parser for malformed files

---

## Testing Your Scanner

### Using pytest

Run tests for a specific language:
```bash
uv run pytest tests/ruby/
```

Run a specific test file:
```bash
uv run pytest tests/ruby/test_ruby.py
```

Run a specific test function:
```bash
uv run pytest tests/ruby/test_ruby.py::test_basic_parsing
```

Run all tests:
```bash
uv run pytest
```

Run with verbose output:
```bash
uv run pytest -v
```

Run with coverage:
```bash
uv run pytest --cov=src/scantool
```

### Manual Test

```bash
uv run python -c "
from scantool.scanner import FileScanner
from scantool.formatter import TreeFormatter

scanner = FileScanner()
formatter = TreeFormatter()

# Test your file
structures = scanner.scan_file('tests/ruby/samples/basic.rb')
print(formatter.format('tests/ruby/samples/basic.rb', structures))
"
```

### Check Consistency

The base scanner includes consistency checks:

```python
# Automatically checks:
# ✓ Line numbers are sequential
# ✓ Parent/child ranges are nested properly
# ✓ No overlapping siblings
# ✓ Signatures are properly formatted
```

### Test with Malformed Files

```bash
# Create a broken file
echo "class Broken:" > tests/ruby/samples/broken.rb

# Should handle errors without crashing
uv run python -c "
from scantool.scanner import FileScanner
scanner = FileScanner()
result = scanner.scan_file('tests/ruby/samples/broken.rb')
print(result)  # Should show error nodes, not crash
"
```

---

## Parallel Development

Multiple people can work on different scanners simultaneously without conflicts.

### Agent Assignment Example

```bash
# Agent 1: JavaScript/TypeScript
git checkout -b feat/javascript-scanner
cp src/scantool/scanners/_template.py src/scantool/scanners/javascript_scanner.py
# ... implement ...

# Agent 2: Rust
git checkout -b feat/rust-scanner
cp src/scantool/scanners/_template.py src/scantool/scanners/rust_scanner.py
# ... implement ...

# Agent 3: Go
git checkout -b feat/go-scanner
cp src/scantool/scanners/_template.py src/scantool/scanners/go_scanner.py
# ... implement ...
```

Each scanner is isolated, avoiding conflicts during merges.

---

## Pull Request Template

When submitting a new scanner:

```markdown
## Adding [Language] Support

### Scanner Implementation
- [ ] Created `LANG_scanner.py` with all required methods
- [ ] Extracts: classes, functions/methods, [other structures]
- [ ] Includes signatures with type annotations
- [ ] Includes docstrings/comments
- [ ] Includes decorators/attributes

### Testing
- [ ] Created `tests/LANG/samples/basic.EXT`
- [ ] Created `tests/LANG/test_LANG.py`
- [ ] All tests pass locally
- [ ] Tested with malformed files (handles gracefully)

### Dependencies
- [ ] Added `tree-sitter-LANG` to `pyproject.toml`
- [ ] Documented version requirements

### Documentation
- [ ] Updated README.md supported languages table
- [ ] Added language to server.py docstring

### Example Output
```
[Paste example output here]
```
```

---

## Debugging Tips

### Enable Error Visibility

```python
scanner = FileScanner(show_errors=True)
# Shows ERROR nodes in output
```

### Inspect Tree-Sitter Output

```python
from tree_sitter import Language, Parser
import tree_sitter_YOURLANG

parser = Parser()
parser.language = Language(tree_sitter_YOURLANG.language())

with open("test.EXT", "rb") as f:
    tree = parser.parse(f.read())

# Print tree
print(tree.root_node.sexp())
```

### Check Node Types

```python
def print_node_types(node, depth=0):
    print("  " * depth + node.type)
    for child in node.children:
        print_node_types(child, depth + 1)

print_node_types(tree.root_node)
```

### Tree-Sitter API Variations

**Important:** Different tree-sitter packages may have different APIs.

Check available functions before assuming `language()` exists:

```python
import tree_sitter_YOUR_LANGUAGE
print(dir(tree_sitter_YOUR_LANGUAGE))
```

**Common patterns:**
- `language()` - Most packages (Python, JavaScript, Go, Rust)
- `language_typescript()` / `language_tsx()` - TypeScript package has two parsers
- `language_cpp()` / `language_c()` - C/C++ package

**Example for TypeScript:**
```python
# TypeScript has two language functions
import tree_sitter_typescript
from tree_sitter import Language

# Use TSX parser (superset of TypeScript)
self.parser.language = Language(tree_sitter_typescript.language_tsx())
```

### Handling Multiple Parsers

Some languages have multiple parsers (e.g., TypeScript has `typescript` and `tsx`):

**Option 1: Use the superset parser for all files** (recommended if available)
```python
# TSX is a superset of TypeScript, so use it for both .ts and .tsx
self.parser.language = Language(tree_sitter_typescript.language_tsx())
```

**Option 2: Different parsers per extension** (if languages are truly different)
Note: The `scan()` method only receives bytes, not the filename. You'd need to detect file type from content or add custom logic in the main scanner.

### Common Node Type Patterns

When implementing `traverse()`, watch for these common patterns:

**Export/Import Wrappers:**
```python
# Many languages wrap declarations in export statements
elif node.type == "export_statement":
    # Don't create a structure for the export itself
    # Traverse children to find what's being exported
    for child in node.children:
        traverse(child, parent_structures)
```

**Declaration Statements:**
```python
# Some parsers wrap declarations (variable_declaration, etc.)
elif node.type in ("variable_declaration", "lexical_declaration"):
    # Extract the actual declaration inside
    for child in node.children:
        traverse(child, parent_structures)
```

---

## Quality Standards

### Required for All Scanners

1. **Error Handling**: Must not crash on malformed input
2. **Line Numbers**: Must be accurate (1-indexed)
3. **Consistency**: Child ranges must be within parent ranges
4. **Fallback**: Regex-based fallback for severely broken files

### Nice to Have

1. **Signatures**: Extract function/method signatures with types
2. **Docstrings**: First line of documentation
3. **Decorators**: Language-specific annotations
4. **Modifiers**: async, static, public/private, etc.
5. **Complexity**: For functions/methods

---

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/mariusei/file-scanner-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/mariusei/file-scanner-mcp/discussions)
- **Examples**: Check `python_scanner.py` (full-featured) and `text_scanner.py` (simple)

---

## Example Scanners to Study

1. **`python_scanner.py`**: Full-featured with all metadata
2. **`text_scanner.py`**: Simple, no tree-sitter required
3. **`_template.py`**: Starter template with TODOs

---

# Adding a New Analyzer (Code Map System)

Analyzers power the code map system (preview_directory, code_map). They extract imports, entry points, and optionally function definitions and calls for building import graphs and call graphs.

## Quick Start

### 1. Copy the Template

```bash
cp src/scantool/analyzers/_analyzer_template.py src/scantool/analyzers/LANGUAGE_analyzer.py
```

### 2. Implement Required Methods

**Minimum viable analyzer** (Layer 1 only):
```python
class LANGUAGEAnalyzer(BaseAnalyzer):
    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".ext"]  # Your file extensions

    @classmethod
    def get_language_name(cls) -> str:
        return "LANGUAGE"  # Human-readable name

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        # Extract import/use/require statements
        pass

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        # Find main(), if __name__, app instances, exports
        pass

    def should_analyze(self, file_path: str) -> bool:
        # Skip minified, generated, compiled files
        return True
```

**Full analyzer** (Layer 1 + Layer 2):
Add these for call graph support:
```python
def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
    # Extract functions, classes, methods
    pass

def extract_calls(self, file_path: str, content: str, definitions: list[DefinitionInfo]) -> list[CallInfo]:
    # Extract function calls
    pass
```

### 3. Auto-Discovery

No registration needed. The analyzer is automatically discovered on startup.

Verify:
```bash
uv run python -c "
from scantool.analyzers import get_registry
registry = get_registry()
print(registry.get_supported_extensions())  # Should include .your_ext
"
```

### 4. Test It

```bash
# Create test file
mkdir -p tests/analyzers
cat > tests/analyzers/test_LANGUAGE_analyzer.py << 'EOF'
from scantool.analyzers.LANGUAGE_analyzer import LANGUAGEAnalyzer

def test_extract_imports():
    analyzer = LANGUAGEAnalyzer()
    content = "import foo"  # Your language syntax
    imports = analyzer.extract_imports("test.ext", content)
    assert len(imports) > 0
    assert imports[0].target_module == "foo"
EOF

# Run tests
uv run pytest tests/analyzers/test_LANGUAGE_analyzer.py -v
```

---

## Two-Tier Noise Filtering

Analyzers integrate with two-tier skip system:

**Tier 1**: Directory/file patterns (fast, structural)
- Handled by `skip_patterns.py`: COMMON_SKIP_DIRS, COMMON_SKIP_FILES, COMMON_SKIP_EXTENSIONS
- Filters .git/, node_modules/, .pyc, .dll before analyzer sees them

**Tier 2**: Language-specific patterns (semantic)
- Handled by `should_analyze()` in your analyzer
- Filters minified JS, type declarations, generated protobuf files

### Example: TypeScript Analyzer

```python
def should_analyze(self, file_path: str) -> bool:
    filename = Path(file_path).name.lower()

    # Skip minified files
    if filename.endswith(('.min.js', '.min.mjs', '.min.cjs')):
        return False

    # Skip type declarations
    if filename.endswith('.d.ts'):
        return False

    # Skip bundles
    if 'bundle' in filename or 'chunk' in filename:
        return False

    return True
```

**Principle**: Tier 1 filters by structure (directories, extensions), Tier 2 filters by naming patterns specific to your language ecosystem.

---

## Regex vs Tree-Sitter

**Use regex when:**
- Import syntax is simple and consistent
- Language has strict conventions (e.g., Python imports, Rust use statements)
- Performance matters (analyzing thousands of files)

**Use tree-sitter when:**
- Syntax is complex or has many edge cases
- Need to distinguish comments from code
- Need to handle nested structures (definitions inside classes)

**Recommendation**: Start with regex, add tree-sitter if you hit edge cases.

### Example: Regex-based Imports (Rust)

```python
def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
    imports = []

    # use foo::bar;
    # use foo::{bar, baz};
    pattern = r'^\s*use\s+([^;]+);'

    for match in re.finditer(pattern, content, re.MULTILINE):
        module = match.group(1).strip()
        # Remove curly braces: foo::{bar, baz} -> foo
        module = re.sub(r'\{[^}]*\}', '', module).strip()
        line = content[:match.start()].count('\n') + 1

        imports.append(ImportInfo(
            source_file=file_path,
            target_module=module,
            import_type="use",
            line=line
        ))

    return imports
```

### Example: Tree-Sitter-based Definitions (Go)

```python
def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
    if not self.parser:
        return []

    definitions = []
    tree = self.parser.parse(bytes(content, 'utf8'))

    def visit(node, parent_name=None):
        # func main() or func (r *Receiver) Method()
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = content[name_node.start_byte:name_node.end_byte]
                line = node.start_point[0] + 1

                # Check if it's a method (has receiver)
                receiver = node.child_by_field_name("receiver")
                if receiver:
                    fqn = f"{file_path}:{parent_name}.{name}"
                    def_type = "method"
                else:
                    fqn = f"{file_path}:{name}"
                    def_type = "function"

                definitions.append(DefinitionInfo(
                    name=fqn,
                    type=def_type,
                    file=file_path,
                    line=line
                ))

        for child in node.children:
            visit(child, parent_name)

    visit(tree.root_node)
    return definitions
```

---

## Entry Point Detection Patterns

Entry points vary by language. Here are common patterns:

### main() Functions
```python
# Pattern: fn main(), func main(), def main(), public static void main
pattern = r'^\s*(?:pub\s+)?(?:fn|func|def|public\s+static\s+void)\s+main\s*\('
```

### Conditional Execution Guards
```python
# Python: if __name__ == "__main__"
# Ruby: if __FILE__ == $0
pattern = r'if\s+__(?:name|FILE)__\s*==\s*["\'](?:__main__|\\$0)["\']\s*:'
```

### Framework Entry Points
```python
# Flask: app = Flask(__name__)
# Express: const app = express()
# FastAPI: app = FastAPI()
pattern = r'(\w+)\s*=\s*(Flask|express|FastAPI|Rocket)\('
```

### Module Exports
```python
# JavaScript: export default function
# TypeScript: export { foo, bar }
pattern = r'^\s*export\s+(?:default\s+)?(?:function|class|const)\s+(\w+)'
```

---

## Testing Analyzers

### Unit Tests

Create `tests/analyzers/test_LANGUAGE_analyzer.py`:

```python
import pytest
from scantool.analyzers.LANGUAGE_analyzer import LANGUAGEAnalyzer

class TestLANGUAGEAnalyzer:
    def test_extract_imports(self):
        analyzer = LANGUAGEAnalyzer()
        content = """
        import foo
        import bar.baz
        """
        imports = analyzer.extract_imports("test.ext", content)
        assert len(imports) == 2
        assert imports[0].target_module == "foo"
        assert imports[1].target_module == "bar.baz"

    def test_find_entry_points(self):
        analyzer = LANGUAGEAnalyzer()
        content = """
        def main():
            pass
        """
        entry_points = analyzer.find_entry_points("test.ext", content)
        assert len(entry_points) == 1
        assert entry_points[0].type == "main_function"

    def test_should_analyze_skip_minified(self):
        analyzer = LANGUAGEAnalyzer()
        assert analyzer.should_analyze("app.min.js") is False
        assert analyzer.should_analyze("app.js") is True
```

### Integration Tests

Test with real project:

```python
import tempfile
from pathlib import Path
from scantool.code_map import CodeMap

def test_code_map_integration():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create test files
        (project_dir / "main.ext").write_text("""
        import helper

        def main():
            helper.do_something()
        """)

        (project_dir / "helper.ext").write_text("""
        def do_something():
            pass
        """)

        # Run code map
        cm = CodeMap(str(project_dir), respect_gitignore=False)
        result = cm.analyze()

        # Verify imports were detected
        assert result.total_files == 2
        assert len(result.import_graph) == 2

        # Verify entry points
        assert len(result.entry_points) == 1
        assert result.entry_points[0].name == "main"
```

### Run Tests

```bash
# Specific analyzer tests
uv run pytest tests/analyzers/test_LANGUAGE_analyzer.py -v

# All analyzer tests
uv run pytest tests/analyzers/ -v

# With coverage
uv run pytest tests/analyzers/test_LANGUAGE_analyzer.py --cov=src/scantool/analyzers
```

---

## Checklist for New Analyzers

**Required:**
- [ ] Create `src/scantool/analyzers/LANGUAGE_analyzer.py`
- [ ] Implement `get_extensions()`, `get_language_name()`
- [ ] Implement `extract_imports()` (Layer 1)
- [ ] Implement `find_entry_points()` (Layer 1)
- [ ] Implement `should_analyze()` for language-specific skip patterns
- [ ] Create unit tests in `tests/analyzers/test_LANGUAGE_analyzer.py`
- [ ] All tests pass: `uv run pytest tests/analyzers/test_LANGUAGE_analyzer.py`

**Optional (for call graph support):**
- [ ] Implement `extract_definitions()` (Layer 2)
- [ ] Implement `extract_calls()` (Layer 2)
- [ ] Add integration test with CodeMap

**Documentation:**
- [ ] Add to README.md supported languages table
- [ ] Document any tree-sitter dependencies in pyproject.toml

---

## Philosophy: Raskt-Enkelt-Pålitelig

**Raskt (Fast):**
- Use regex for simple patterns (imports, entry points)
- Reserve tree-sitter for complex syntax (nested definitions, calls)
- Two-tier filtering eliminates noise before parsing

**Enkelt (Simple):**
- One file per language, auto-discovered
- No registration boilerplate
- Copy template, fill in patterns, done
- DRY: Use BaseAnalyzer helpers (_resolve_relative_import, classify_file)

**Pålitelig (Reliable):**
- No TODOs, no placeholders, no shortcuts
- Handle edge cases (relative imports, framework detection)
- Complete implementation: both happy path and error cases
- Tests verify correctness on real code

**No Overabstraction:**
- Direct regex patterns, not regex builders
- Tree-sitter queries when needed, not everywhere
- Simple if/else, not factory patterns

---

## Examples to Study

**Regex-based (simple, fast):**
- `src/scantool/analyzers/python_analyzer.py` - Import variants, relative imports, if __name__
- `src/scantool/analyzers/go_analyzer.py` - Package imports, func main(), skip .pb.go

**Tree-sitter-based (robust):**
- `src/scantool/analyzers/typescript_analyzer.py` - Dynamic imports, export patterns
- `src/scantool/analyzers/python_analyzer.py` - extract_definitions(), extract_calls()

**Template (copy this):**
- `src/scantool/analyzers/_analyzer_template.py` - Complete reference with all options

---

## Debugging Tips

### Verify Auto-Discovery

```bash
uv run python -c "
from scantool.analyzers import get_registry
registry = get_registry()
print('Supported extensions:', registry.get_supported_extensions())
print('Analyzer for .rs:', registry.get_analyzer('.rs'))
"
```

### Test Analyzer Directly

```bash
uv run python -c "
from scantool.analyzers.rust_analyzer import RustAnalyzer

analyzer = RustAnalyzer()
content = open('tests/samples/main.rs').read()

imports = analyzer.extract_imports('main.rs', content)
print('Imports:', imports)

entry_points = analyzer.find_entry_points('main.rs', content)
print('Entry points:', entry_points)
"
```

### Test with Code Map

```bash
uv run python -c "
from scantool.code_map import CodeMap

cm = CodeMap('.', respect_gitignore=True, enable_layer2=False)
result = cm.analyze()

print(f'Files analyzed: {result.total_files}')
print(f'Entry points: {len(result.entry_points)}')
print(f'Import edges: {sum(len(n.imports) for n in result.files)}')
"
```

---

## Getting Help

- **Template**: Copy `src/scantool/analyzers/_analyzer_template.py`
- **Examples**: Study `python_analyzer.py`, `typescript_analyzer.py`, `go_analyzer.py`
- **Issues**: [GitHub Issues](https://github.com/mariusei/file-scanner-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/mariusei/file-scanner-mcp/discussions)
