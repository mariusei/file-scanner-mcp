```
  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
  ░                                                                          ░
  ░   ███████╗ ██████╗ █████╗ ███╗   ██╗████████╗ ██████╗  ██████╗ ██╗       ░
  ░   ██╔════╝██╔════╝██╔══██╗████╗  ██║╚══██╔══╝██╔═══██╗██╔═══██╗██║       ░
  ░   ███████╗██║     ███████║██╔██╗ ██║   ██║   ██║   ██║██║   ██║██║       ░
  ░   ╚════██║██║     ██╔══██║██║╚██╗██║   ██║   ██║   ██║██║   ██║██║       ░
  ░   ███████║╚██████╗██║  ██║██║ ╚████║   ██║   ╚██████╔╝╚██████╔╝███████╗  ░
  ░   ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝  ░
  ░                                                                          ░
  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

                ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓

                ╔═══════════════════════════════════════════╗
                ║  ▶ [▓▓▓▓▓▓▓▓▓░░] Scanning codebase...     ║
                ║                                           ║
                ║  ╭───────────────────────────────────╮    ║
                ║  │ ✓ Classes    ▓▓▓▓▓▓▓▓▓▓ 100%      │    ║
                ║  │ ✓ Functions  ▓▓▓▓▓▓▓▓▓▓ 100%      │    ║
                ║  │ ✓ Metadata   ▓▓▓▓▓▓▓▓▓▓ 100%      │    ║
                ║  ╰───────────────────────────────────╯    ║
                ║                                           ║
                ║    tree-sitter powered  •  MCP ready      ║
                ╚═══════════════════════════════════════════╝

                ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
```

# Scantool - File Scanner MCP

MCP server for analyzing source code structure across 20+ languages. Extracts classes, functions, methods, and metadata (signatures, decorators, docstrings) with precise line numbers. Powered by tree-sitter.

## Quick Start

### Claude Code

```bash
claude mcp add --transport stdio scantool -- uvx --from scantool scantool
```

That's it. Restart Claude Code and you're ready to go.

### Claude Desktop

Add to config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "scantool": {
      "command": "uvx",
      "args": ["--from", "scantool", "scantool"]
    }
  }
}
```

Restart Claude Desktop after configuration.

### Troubleshooting: `uvx` not found

`uvx` comes with [uv](https://docs.astral.sh/uv/), the Python package manager. Install it first:

```bash
# macOS / Linux / WSL
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**After installing uv, restart your terminal** (or open a new one) so `uvx` is on your PATH. Then re-run the setup command above.

If `uvx` still isn't found after restarting the terminal, add it to your PATH manually:

```bash
# Linux / WSL - add to ~/.bashrc or ~/.zshrc:
export PATH="$HOME/.local/bin:$PATH"

# macOS - usually works out of the box, but if not:
export PATH="$HOME/.local/bin:$PATH"
```

### Alternative: Install from source

```bash
git clone https://github.com/mariusei/file-scanner-mcp.git
cd file-scanner-mcp
uv sync

# Claude Code
claude mcp add --transport stdio scantool -- uv run --directory /path/to/file-scanner-mcp scantool

# Claude Desktop
# Use command: "uv", args: ["run", "--directory", "/path/to/file-scanner-mcp", "scantool"]
```

### Share with your team (.mcp.json)

Add a `.mcp.json` file to your project root to share the config with your team:

```json
{
  "mcpServers": {
    "scantool": {
      "command": "uvx",
      "args": ["--from", "scantool", "scantool"]
    }
  }
}
```

Claude Code will prompt team members for approval on first use.

## Features

### Multi-language Support
Python, JavaScript, TypeScript, Rust, Go, C/C++, Java, PHP, C#, Ruby, Zig, Swift, SQL (PostgreSQL, MySQL, SQLite), HTML, CSS, SCSS, Markdown, Plain Text, Images

### Structure Extraction
- Classes, methods, functions, imports
- Function signatures with type annotations
- Decorators and attributes
- Docstrings and JSDoc comments
- Precise line numbers (from-to ranges)

### Analysis Tools
- **preview_directory**: Intelligent codebase analysis with entry points, import graph, call graph, and hot functions (5-10s)
- **scan_file**: Detailed file structure with signatures and metadata
- **scan_directory**: Compact directory tree with inline function/class names
- **search_structures**: Filter by type, name pattern, decorator, or complexity
- **list_directories**: Directory tree (folders only)

### Output Formats
- Tree format with box-drawing characters
- JSON format for programmatic use
- Configurable display options

## Usage

### preview_directory - Code analysis (primary tool)

Analyzes codebase structure including entry points, import graph, call graph, and hot functions.

```python
preview_directory(
    directory=".",
    depth="deep",             # "quick", "normal", or "deep" (default: "deep")
    max_files=10000,          # Safety limit (default: 10000)
    max_entries=20,           # Entries per section (default: 20)
    respect_gitignore=True    # Honor .gitignore (default: True)
)
```

**Depth levels:**
- `"quick"`: Metadata only (0.5s) - file counts, sizes, types
- `"normal"`: Architecture analysis (2-5s) - imports, entry points, clusters
- `"deep"`: Full analysis (5-10s) - includes hot functions and call graph (default)

**Example output (depth="deep"):**

```
project/

--- ENTRY POINTS ---
  main.py:main() @1
  backend/application.py:Flask app @15
  frontend/index.ts:export default

--- CORE FILES (by centrality) ---
  backend/database.py: imports 0, used by 15 files
  backend/auth.py: imports 1, used by 8 files
  shared/utils.py: imports 2, used by 12 files

--- ARCHITECTURE ---
  Entry Points: 25 files
  Core Logic: 68 files
  Plugins: 15 files
  Tests: 42 files

--- HOT FUNCTIONS (most called) ---
  get_database() (function): called by 41, calls 1 @backend/database.py
  authenticate() (function): called by 23, calls 5 @backend/auth.py
  validate_input() (function): called by 15, calls 2 @shared/utils.py

Analysis: 486 files in 4.82s (layer1+layer2)
```

**Use cases:**
- First-time codebase exploration
- Understanding multi-modality projects (frontend/backend/database)
- Finding critical functions (hot spots)
- Identifying entry points

### scan_file - Detailed file analysis

```python
scan_file(
    file_path="path/to/file.py",
    show_signatures=True,      # Include function signatures with types
    show_decorators=True,      # Include @decorator annotations
    show_docstrings=True,      # Include first line of docstrings
    show_complexity=False,     # Show complexity metrics
    output_format="tree"       # "tree" or "json"
)
```

**Example output:**

```
example.py (1-57)
├─ file-info: 1.4KB modified: 2 hours ago
├─ imports: import statements (3-5)
├─ class: DatabaseManager (8-26)
│    "Manages database connections and queries."
│  ├─ method: __init__ (self, connection_string: str) (11-13)
│  ├─ method: connect (self) (15-17)
│  │    "Establish database connection."
│  └─ method: query (self, sql: str) -> list (24-26)
│       "Execute a SQL query."
└─ function: main () (53-57)
     "Main entry point."
```

### scan_file_content - Analyze content directly

Scan content without requiring a file path. Works with remote files, APIs, or in-memory content.

```python
scan_file_content(
    content="def hello(): pass\n\nclass MyClass:\n    pass",
    filename="example.py",     # Extension determines parser
    show_signatures=True,
    show_decorators=True,
    show_docstrings=True,
    show_complexity=False,
    output_format="tree"
)
```

### scan_directory - Compact overview

Shows directory tree with inline class/function names.

```python
scan_directory(
    directory="./src",
    pattern="**/*",                 # Glob pattern
    max_files=None,                 # File limit
    respect_gitignore=True,         # Honor .gitignore
    exclude_patterns=None,          # Additional exclusions
    output_format="tree"            # "tree" or "json"
)
```

**Example output:**

```
src/ (22 files, 15 classes, 127 functions, 89 methods)
├─ languages/
│  ├─ python.py (1-329) [11.9KB, 2 hours ago] - PythonLanguage
│  ├─ typescript.py (1-505) [18.9KB, 1 day ago] - TypeScriptLanguage
│  └─ rust.py (1-481) [17.6KB, 3 days ago] - RustLanguage
├─ scanner.py (1-232) [8.8KB, 5 mins ago] - FileScanner
└─ server.py (1-735) [27.2KB, just now] - scan_file, scan_directory, ...
```

**Pattern examples:**

```python
# Specific file types
scan_directory("./src", pattern="**/*.py")

# Multiple types
scan_directory("./src", pattern="**/*.{py,ts,js}")

# Shallow scan (1 level deep)
scan_directory(".", pattern="*/*")

# Exclude directories
scan_directory(".", exclude_patterns=["tests/**", "docs/**"])
```

### search_structures - Find and filter

```python
# Find test functions
search_structures(
    directory="./tests",
    type_filter="function",
    name_pattern="^test_"
)

# Find classes ending in "Manager"
search_structures(
    directory="./src",
    type_filter="class",
    name_pattern=".*Manager$"
)

# Find functions with @staticmethod
search_structures(
    directory="./src",
    has_decorator="@staticmethod"
)

# Find complex functions (>100 lines)
search_structures(
    directory="./src",
    type_filter="function",
    min_complexity=100
)
```

### list_directories - Folder structure

Shows directory tree without files.

```python
list_directories(
    directory=".",
    max_depth=3,              # Maximum depth (default: 3)
    respect_gitignore=True    # Honor .gitignore (default: True)
)
```

**Example output:**

```
/Users/user/project/
├─ src/
│  ├─ components/
│  ├─ services/
│  └─ utils/
├─ tests/
│  ├─ unit/
│  └─ integration/
└─ docs/
```

## Supported Languages

| Extension | Language | Extracted Elements |
|-----------|----------|-------------------|
| `.py`, `.pyw` | Python | classes, methods, functions, imports, decorators, docstrings |
| `.js`, `.jsx`, `.mjs`, `.cjs` | JavaScript | classes, methods, functions, imports, JSDoc comments |
| `.ts`, `.tsx`, `.mts`, `.cts` | TypeScript | classes, methods, functions, imports, type annotations, JSDoc |
| `.rs` | Rust | structs, enums, traits, impl blocks, functions, use statements |
| `.go` | Go | types, structs, interfaces, functions, methods, imports |
| `.c`, `.h` | C | functions, structs, enums, includes |
| `.cpp`, `.hpp`, `.cc`, `.hh` | C++ | classes, functions, namespaces, templates, includes |
| `.java` | Java | classes, methods, interfaces, enums, annotations, imports |
| `.php` | PHP | classes, methods, functions, traits, interfaces, namespaces |
| `.cs` | C# | classes, methods, properties, structs, enums, namespaces |
| `.rb` | Ruby | modules, classes, methods, singleton methods |
| `.zig` | Zig | functions, structs, enums, unions, tests |
| `.swift` | Swift | classes, structs, enums, protocols, functions, extensions |
| `.sql` | SQL | tables, views, functions, procedures, indexes, columns |
| `.html` | HTML | document structure, elements, attributes |
| `.css` | CSS | selectors, properties, media queries |
| `.scss` | SCSS | selectors, mixins, variables, nesting |
| `.md` | Markdown | headings (h1-h6), code blocks with hierarchy |
| `.txt` | Plain Text | sections, paragraphs |
| `.png`, `.jpg`, `.gif`, `.webp` | Images | format, dimensions, colors, content type |

All files include metadata (size, modified date, permissions) automatically.

## Use Cases

### Code Navigation
- Structural overview of unfamiliar codebases
- File organization understanding
- Navigation using precise line ranges

### Refactoring
- Identify class and function boundaries for safe splitting
- Find implementations of specific patterns
- Locate functions above complexity thresholds

### Code Review
- Generate structural diffs
- Find functions with specific decorators
- Identify test coverage gaps

### Documentation
- Auto-generate table of contents with line numbers
- Extract API signatures
- Feed structured data to analysis tools (JSON output)

### AI Code Assistance
- Primary exploration tool (replaces ls/grep/find workflows)
- Partition large files intelligently for LLM context windows
- Extract code sections with exact boundaries
- Search patterns across codebases
- Reduce token usage: get structure first, read content only when needed

## Architecture

```
scantool/
├── server.py        # FastMCP server (stdio + HTTP entry points)
├── scanner.py       # Core scanning logic using tree-sitter
├── formatter.py     # Tree formatting with box-drawing characters
├── code_map.py      # Architecture analysis (Layer 1 + 2)
├── call_graph.py    # Hot functions, centrality analysis
├── preview.py       # Quick directory preview
└── languages/       # Unified language system (one file per language)
    ├── base.py      # BaseLanguage - all languages inherit from this
    ├── models.py    # StructureNode, CallInfo, ImportInfo, etc.
    ├── python.py    # PythonLanguage
    ├── typescript.py
    ├── rust.py
    └── ...          # 20+ languages
```

## HTTP Transport (advanced)

For environments where stdio doesn't work, or when sharing a server across multiple clients:

```bash
# Start the HTTP server
uvx --from scantool scantool-http
# Listens on port 8080 by default (set PORT env var to change)

# Connect Claude Code to it
claude mcp add --transport http scantool http://127.0.0.1:8080/mcp
```

Note: The HTTP server must be started separately and kept running. For most users, the stdio transport (default) is simpler and recommended.

## Testing

```bash
# Run all tests
uv run pytest

# Run specific tests
uv run pytest tests/languages/
uv run pytest tests/python/
uv run pytest tests/typescript/

# Run with coverage
uv run pytest --cov=src/scantool

# Run with verbose output
uv run pytest -v
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on adding language support.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Dependencies

- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [tree-sitter](https://tree-sitter.github.io/) - Parsing library
- [uv](https://github.com/astral-sh/uv) - Python package installer

## Known Limitations

### MCP Tool Response Size Limit

Claude Desktop enforces a 25,000 token limit on MCP tool responses. Claude Code has a configurable limit (set `MAX_MCP_OUTPUT_TOKENS` env var to adjust).

**Built-in mitigations:**
- `scan_directory()` uses compact inline format
- Respects `.gitignore` by default (excludes node_modules, .venv, etc.)
- Shows file metadata with relative timestamps

**Manual controls:**
- Use `pattern` to limit scope: `"**/*.py"` vs `"*/*"` (shallow)
- Use `max_files` to cap number of files processed
- Use `exclude_patterns` for additional exclusions
- Scan specific subdirectories instead of entire codebase

**For large codebases:**
```python
# Scan specific areas
scan_directory("./src", pattern="**/*.py")
scan_directory("./tests", pattern="**/*.py")
```

### Agent Delegation

When using Claude Code, asking to "explore the codebase" may delegate to the Explore agent which doesn't have access to MCP tools. Be explicit: "use scantool to scan the codebase" to ensure the MCP tool is used directly.

## Support

- [GitHub Issues](https://github.com/mariusei/file-scanner-mcp/issues)
- [GitHub Discussions](https://github.com/mariusei/file-scanner-mcp/discussions)
