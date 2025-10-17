# Contributing to File Scanner MCP

This guide covers how to add support for a new programming language.

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
