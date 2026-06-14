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
    # Tree-sitter languages: set up self.parser in __init__ and implement
    # _extract_structure(). The base scan() handles parsing, error detection
    # and regex fallback. Languages without tree-sitter override scan().
    def _extract_structure(self, root, source_code: bytes) -> list[StructureNode]:
        """Traverse the tree-sitter AST and build StructureNode list."""
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

    # === Optional Pattern Tables (drive base-class regex fallbacks) ===
    # REGEX_FALLBACK_PATTERNS - structures for severely malformed files
    # REGEX_DEFINITION_PATTERNS - definitions when scan() fails
    # REGEX_CALL_KEYWORDS (+ REGEX_CALL_PATTERN) - call extraction fallback
    # IMPORT_GROUP_LABEL - label for grouped imports (e.g. "use statements")
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

    # Base scan() parses with self.parser, switches to the regex fallback on
    # heavy errors, and calls _extract_structure() — no override needed.

    # Regex fallback for broken files: declarative pattern table
    REGEX_FALLBACK_PATTERNS = [
        {"pattern": r"^class\s+(\w+)", "type": "class"},
        {"pattern": r"^  def\s+(\w+)", "type": "method"},
    ]

    def _extract_structure(self, root, source_code: bytes) -> list[StructureNode]:
        """Extract structure using tree-sitter."""
        structures = []
        # ... traverse AST and build StructureNode list
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
| `_extract_structure()` | Tree-sitter AST traversal | **Required** (or override `scan()`) |
| `scan()` | Extract structure from bytes | Tree-sitter pipeline w/ regex fallback |
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
- [ ] Freeze the output format: add a `basic.*` sample, add the language
      to `SAMPLES` in `tests/test_golden.py`, then generate the snapshot
      with `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`
- [ ] Run tests: `uv run pytest tests/LANG/`
- [ ] Run all tests: `uv run pytest tests/`

---

## The Output Contract (golden tests)

The default output format IS the API for LLM consumers — see "Output
Contract" in README.md. `tests/test_golden.py` freezes it as snapshots
in `tests/golden/` and fails CI on any drift. How to work with it:

1. **Golden tests fail and you didn't intend a format change** → that's
   a caught bug in your change, not a flaky test. Don't update the
   snapshots; fix the cause.
2. **You intend to change the format** → update deliberately:
   `UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`, then review
   `git diff tests/golden/` — every changed line must be explainable by
   your change. Commit code and snapshots together and name the format
   change in the commit message.

Rules that keep the snapshots deterministic:

- Environment-dependent output (file size/mtime, git churn, delta
  notes) belongs in the server layer — never in the frozen
  scanner+formatter layer.
- `tests/golden/fixture_dir/` is frozen input for the directory
  snapshot — don't "improve" those files.
- `.gitattributes` pins LF in working trees: CRLF input measurably
  changes output for html/markdown/sql, so don't remove it.
- `tests/golden/consensus_fixture/` is frozen input for the peer-divergence
  snapshot (`consensus.txt`); it has one planted outlier — don't "fix" it.

---

## Peer Divergence (drift detection)

`consensus.py` mines sites that break a call pattern their siblings follow
(API-usage rule mining — Engler 2001 / PR-Miner 2005). It runs on
`CodeMap.analyze()` output and is wired into `scan_diff` (review: suspects =
changed functions) and `preview_directory` (audit: whole corpus).

The honest framing matters: **it is an attention director, not a defect
oracle.** Peers legitimately differ, so the output says "look here," never
"this is a bug." Keep that framing in any change — the header/footer in
`format_divergences` exist to stop an LLM consumer treating a hint as a fact.

How it stays honest (see the `consensus.py` file header for the full rationale):

- **The call graph is the aligner.** A finding's cohort is "callers of X,"
  aligned by X — not file locality or type. This is what made it work where
  seven footprint-distance attempts failed (`experiments/network_consensus/`).
- **Directional.** Only a *missing* coupled call is a finding; an *extra* call
  is richness and is ignored. A symmetric metric conflates the two.
- **Name-qualified.** Builtins / common container methods carry no contract and
  are dropped (`_NOISE_NAMES`); test/throwaway dirs are not a sibling family
  and are dropped from the corpus (`_NONSOURCE_DIRS`).
- **Self-levelling gate, no domain-tuned thresholds (REP).** Strength fuses a
  scale-free enrichment surprise (`-log10` binomial tail vs base rate) with an
  exceptionality term (how rare the missing side is). Emission requires both
  statistical significance (`SIG`, a universal p-value) and far-out-outlier
  status vs the corpus's own distribution (Tukey `Q3 + 3·IQR`). A consistent
  codebase produces no outliers, hence silence — the truthful signal. The only
  constants are universal statistical ones, documented in `DivergenceConfig`.
- **Role-conditioned (multiview-gate).** The residual confound was architectural-
  style heterogeneity: a function's call pattern depends on its ROLE, so cross-
  role comparison yields false divergences. A finding survives only if the site's
  role equals the conformers' modal role under EVERY orthogonal lens —
  name-morphology, file-cluster (`file_clusters`), and edge-invariant graph
  position. Orthogonality to the usage bags is mandatory (else conditioning
  defines away the signal); graph out-degree EXCLUDES the contested edge so a
  missing call cannot shift the site's own band (the circularity, hardened and
  measured against an adversarial true positive in
  `experiments/role_conditioning/graph_harden.py`). Measured to dissolve
  base-delegation, alt-parser and traverse-style false positives while keeping
  true knock-outs.

**Audit vs review — the precision levers are audit-only.** The fence and role
conditioning are precision levers, and a planted-knock-out recall measurement
(`experiments/norm_inference/inject_recall.py`, with the precision side in
`precision_review.py`) showed they belong in AUDIT only:

- **Audit** (`find_divergence`, `preview_directory`; `suspects=None`) has no
  other precision lever, so it keeps the fence + all three conditioning lenses —
  that is what produces silence on a consistent codebase.
- **Review** (`scan_diff`; `suspects` set) gets its precision from the suspect
  filter (changed code only), so it uses NEITHER the fence NOR conditioning
  (`review_lenses=()`). With them on, review recall of qualified planted
  regressions was ~20%; without, 100%. The graph lens specifically trades recall
  for precision 1:1 — it removes the cross-role false positives by the same
  coarse fan-out test that dissolves real same-name/cluster regressions, so it
  cannot keep both. And those "false positives" are mostly the right class (a
  route missing the `require_permission` its peers call — CWE-862), adjudicable
  in review. So review leans on recall + the "look here, not a bug" framing.
  This is one config line (`review_lenses`) if a project wants precision-first.

Tests: `tests/test_consensus.py` (knock-out recovery, directional asymmetry,
self-levelling silence, base-rate suppression, suspect filter) + the golden.

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
