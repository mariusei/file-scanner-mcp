# Contributing to File Scanner MCP

This guide covers how to add support for a new programming language.

## Architecture Overview

The codebase uses a **unified language system** where each language has a single file in `src/scantool/languages/` that provides both:
- **Structure scanning**: Extract classes, functions, methods for `scan_file`/`scan_directory`
- **Semantic analysis**: Extract imports, entry points, definitions for `code_map` and `preview_directory`

```
src/scantool/
├── languages/               # Unified language system (one file per language)
│   ├── __init__.py         # Registry + auto-discovery
│   ├── base.py             # BaseLanguage class
│   ├── models.py           # Data models (StructureNode, ImportInfo, etc.)
│   ├── skip_patterns.py    # Directory/file skip patterns
│   ├── python.py           # PythonLanguage
│   ├── typescript.py       # TypeScriptLanguage
│   └── ...                 # 20 languages total
│
├── scanner.py              # Main orchestrator (uses languages/)
├── code_map.py             # Code map analysis (uses languages/)
├── entropy/                # Saliency analysis (uses languages/ for function detection)
└── server.py               # MCP server tools
```

## Adding a New Language

Create a single file in `src/scantool/languages/` that inherits from `BaseLanguage`.

### Step 1: Create the Language File

```bash
# Use an existing language as template
cp src/scantool/languages/python.py src/scantool/languages/YOUR_LANGUAGE.py
```

### Step 2: Implement Required Methods

```python
from typing import Optional
from .base import BaseLanguage
from .models import StructureNode, ImportInfo, EntryPointInfo, DefinitionInfo, CallInfo

class YourLanguage(BaseLanguage):
    """Unified language handler for YourLanguage files."""

    # === Metadata (REQUIRED) ===
    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".your", ".ext"]

    @classmethod
    def get_language_name(cls) -> str:
        return "YourLanguage"

    @classmethod
    def get_priority(cls) -> int:
        return 10  # Higher = preferred when multiple languages match

    # === Structure Scanning (REQUIRED) ===
    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Extract classes, functions, methods from source code."""
        # Use tree-sitter or regex to parse
        pass

    # === Semantic Analysis (REQUIRED) ===
    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract import/use/require statements."""
        pass

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find main functions, app instances, exports."""
        pass

    # === Optional Methods ===
    # extract_definitions() - Default reuses scan() output
    # extract_calls() - Default returns empty list
    # classify_file() - Default uses path-based heuristics
    # should_skip() - Default returns False
    # should_analyze() - Default returns True
    # is_low_value_for_inventory() - Identifies small/boilerplate files
    # resolve_import_to_file() - Enables import graph building
    # format_entry_point() - Custom display formatting
```

### Step 3: Test It

```bash
uv run python -c "
from scantool.languages import get_language

# Test language registration
lang = get_language('.your')
print(f'Language: {lang.get_language_name()}')

# Test scanning
code = open('tests/yourlang/samples/basic.your', 'rb').read()
structures = lang.scan(code)
for s in structures:
    print(f'  {s.type}: {s.name}')

# Test imports
content = open('tests/yourlang/samples/basic.your').read()
imports = lang.extract_imports('test.your', content)
for imp in imports:
    print(f'  Import: {imp.target_module}')
"
```

### Key Design Principles

1. **One file per language**: Combines scanner + analyzer into a single `BaseLanguage` subclass
2. **Reuse scan() output**: `extract_definitions()` defaults to converting `scan()` output, avoiding duplicate parsing
3. **Auto-discovery**: Place the file in `languages/` and it's automatically registered
4. **Tree-sitter preferred**: Use tree-sitter for AST-based parsing with regex fallback for malformed files

---

## Complete Example: Adding Ruby Support

### 1. Create the Language File

**File**: `src/scantool/languages/ruby.py`

```python
"""Ruby language support."""

from typing import Optional
import re

try:
    import tree_sitter_ruby
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from .base import BaseLanguage
from .models import StructureNode, ImportInfo, EntryPointInfo


class RubyLanguage(BaseLanguage):
    """Unified language handler for Ruby files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if TREE_SITTER_AVAILABLE:
            self.parser = Parser()
            self.parser.language = Language(tree_sitter_ruby.language())
        else:
            self.parser = None

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".rb", ".rake", ".gemspec"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Ruby"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Ruby source code."""
        if not self.parser:
            return self._fallback_extract(source_code)

        try:
            tree = self.parser.parse(source_code)
            if self._has_too_many_errors(tree.root_node):
                return self._fallback_extract(source_code)
            return self._extract_structure(tree.root_node, source_code)
        except Exception as e:
            return [StructureNode(
                type="error",
                name=f"Parse error: {e}",
                start_line=1,
                end_line=1
            )]

    def _extract_structure(self, root, source_code: bytes) -> list[StructureNode]:
        """Extract structure using tree-sitter."""
        structures = []
        # ... traverse AST and build StructureNode list
        return structures

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex fallback for broken files."""
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        for match in re.finditer(r'^class\s+(\w+)', text, re.MULTILINE):
            line = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1),
                start_line=line,
                end_line=line
            ))

        for match in re.finditer(r'^  def\s+(\w+)', text, re.MULTILINE):
            line = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1),
                start_line=line,
                end_line=line
            ))

        return structures

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract require/require_relative statements."""
        imports = []

        for match in re.finditer(r"require\s+['\"]([^'\"]+)['\"]", content):
            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=match.group(1),
                line=line,
                import_type="require"
            ))

        for match in re.finditer(r"require_relative\s+['\"]([^'\"]+)['\"]", content):
            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=match.group(1),
                line=line,
                import_type="require_relative"
            ))

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in Ruby file."""
        entry_points = []

        # if __FILE__ == $0
        if re.search(r'if\s+__FILE__\s*==\s*\$0', content):
            match = re.search(r'if\s+__FILE__\s*==\s*\$0', content)
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="if_file",
                name="$0",
                line=line
            ))

        # Rails/Sinatra app detection
        if 'Sinatra::Base' in content or 'Rails.application' in content:
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="app_instance",
                name="app",
                line=1
            ))

        return entry_points
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
require 'json'
require_relative 'helper'

class UserManager
  def initialize(database)
    @database = database
  end

  def create_user(name, email)
    @database.insert(name: name, email: email)
  end
end

def validate_email(email)
  email.include?("@")
end

if __FILE__ == $0
  puts "Running..."
end
```

### 4. Create Tests

**File**: `tests/ruby/test_ruby.py`

```python
"""Tests for Ruby language."""

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic Ruby file parsing."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")
    assert structures is not None
    assert any(s.type == "class" and s.name == "UserManager" for s in structures)


def test_imports():
    """Test import extraction."""
    from scantool.languages.ruby import RubyLanguage

    lang = RubyLanguage()
    content = open("tests/ruby/samples/basic.rb").read()
    imports = lang.extract_imports("basic.rb", content)

    assert len(imports) >= 2
    assert any(imp.target_module == "json" for imp in imports)


def test_entry_points():
    """Test entry point detection."""
    from scantool.languages.ruby import RubyLanguage

    lang = RubyLanguage()
    content = open("tests/ruby/samples/basic.rb").read()
    entry_points = lang.find_entry_points("basic.rb", content)

    assert len(entry_points) >= 1
    assert any(ep.type == "if_file" for ep in entry_points)
```

### 5. Run Tests

```bash
# Run language-specific tests
uv run pytest tests/ruby/ -v

# Run all tests
uv run pytest
```

---

## Two-Tier Noise Filtering

Languages integrate with two-tier skip system:

**Tier 1**: Directory/file patterns (fast, structural)
- Handled by `skip_patterns.py`: COMMON_SKIP_DIRS, COMMON_SKIP_FILES
- Filters .git/, node_modules/, .pyc before language sees them

**Tier 2**: Language-specific patterns (semantic)
- Handled by `should_analyze()` in your language class
- Filters minified JS, type declarations, generated files

### Example

```python
def should_analyze(self, file_path: str) -> bool:
    filename = Path(file_path).name.lower()

    # Skip minified files
    if filename.endswith('.min.js'):
        return False

    # Skip generated files
    if filename.endswith('.pb.go'):
        return False

    return True
```

---

## Key Methods Reference

| Method | Purpose | Default |
|--------|---------|---------|
| `get_extensions()` | File extensions to handle | **Required** |
| `get_language_name()` | Human-readable name | **Required** |
| `scan()` | Extract structure from bytes | **Required** |
| `extract_imports()` | Find import statements | **Required** |
| `find_entry_points()` | Find main/app instances | **Required** |
| `extract_definitions()` | Get functions/classes | Reuses `scan()` |
| `extract_calls()` | Find function calls | Returns `[]` |
| `should_skip()` | Skip file before reading | Returns `False` |
| `should_analyze()` | Skip file after reading | Returns `True` |
| `classify_file()` | Categorize file | Path-based heuristics |
| `resolve_import_to_file()` | Map import to file path | Returns `None` |
| `format_entry_point()` | Display formatting | Default format |

---

## Checklist for New Languages

- [ ] Create `src/scantool/languages/LANG.py`
- [ ] Implement required methods (metadata, scan, imports, entry points)
- [ ] Add tree-sitter dependency to `pyproject.toml`
- [ ] Create test directory: `tests/LANG/samples/`
- [ ] Create test file: `tests/LANG/test_LANG.py`
- [ ] Run tests: `uv run pytest tests/LANG/`
- [ ] Run all tests: `uv run pytest`

---

## Examples to Study

| File | Features |
|------|----------|
| `python.py` | Full-featured: tree-sitter, signatures, decorators, docstrings, complexity |
| `typescript.py` | Multiple extensions (.ts, .tsx, .js), JSDoc extraction |
| `go.py` | Simple imports, method receivers, generated file skipping |
| `swift.py` | @main detection, protocol extraction, SwiftUI patterns |
| `generic.py` | Fallback for unsupported extensions |

---

## Debugging Tips

### Verify Auto-Discovery

```bash
uv run python -c "
from scantool.languages import get_registry
registry = get_registry()
print('Extensions:', list(registry.extensions()))
print('Language for .py:', registry.get('.py'))
"
```

### Inspect Tree-Sitter AST

```python
from tree_sitter import Language, Parser
import tree_sitter_YOUR_LANG

parser = Parser()
parser.language = Language(tree_sitter_YOUR_LANG.language())

with open("test.ext", "rb") as f:
    tree = parser.parse(f.read())

print(tree.root_node.sexp())
```

### Test with MCP Tools

```bash
uv run python -c "
from scantool.scanner import FileScanner
scanner = FileScanner()
result = scanner.scan_file('path/to/file.ext')
for node in result:
    print(f'{node.type}: {node.name} @{node.start_line}')
"
```

---

## Getting Help

- **Examples**: Check existing languages in `src/scantool/languages/`
- **Issues**: [GitHub Issues](https://github.com/mariusei/file-scanner-mcp/issues)
