# Scantool - File Scanner MCP

MCP server for analyzing source code structure across multiple languages. Extracts classes, functions, methods, and metadata (signatures, decorators, docstrings) with precise line numbers. Includes search and filtering capabilities for large codebases.

## Features

### Core Capabilities
- **Multi-language support**: Python, JavaScript, TypeScript, Rust, Go, C/C++, Java, PHP, C#, Ruby, Markdown, Plain Text, Images
- **Structure extraction**: Classes, methods, functions, imports, headings, sections, paragraphs
- **Metadata parsing**: Function signatures with types, decorators, docstrings, modifiers (async, static, etc.)
- **File metadata**: Size, timestamps, permissions automatically included for all files
- **Image analysis**: Dimensions, format, colors, content type inference, optimization hints
- **Precise line numbers**: Every element includes (from-to) line ranges for safe file partitioning
- **Error handling**: Handles malformed files without crashing, with regex fallback parsing

### Output Options
- **Tree format**: Hierarchical display with box-drawing characters (├─, └─, │)
- **JSON format**: Structured data output for programmatic use
- **Configurable display**: Toggle signatures, decorators, docstrings, complexity metrics

### Tools
- **scan_file**: Analyze a single file with full metadata extraction
- **scan_directory**: Hierarchical directory tree with integrated code structures and statistics
- **search_structures**: Find and filter structures by type, name pattern, decorator, or complexity

## Installation

### Install with uvx (Recommended)

```bash
# From GitHub
uvx --from git+https://github.com/mariusei/file-scanner-mcp scantool

# Or from PyPI
uvx scantool
```

# Or from Smithery
https://smithery.ai/server/@mariusei/file-scanner-mcp

### Install from Source

```bash
git clone https://github.com/mariusei/file-scanner-mcp.git
cd file-scanner-mcp
uv sync
uv run scantool
```

## Configuration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "scantool": {
      "command": "uvx",
      "args": ["scantool"]
    }
  }
}
```

Or if installed from source:

```json
{
  "mcpServers": {
    "scantool": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/file-scanner-mcp", "scantool"]
    }
  }
}
```

## Usage

The server provides three MCP tools for code exploration:

**Recommended Workflow:**

1. **Get codebase overview**: Use `scan_directory()` to see compact bird's-eye view
   - Shows directory tree with inline list of classes/functions per file
   - Respects .gitignore automatically (excludes node_modules, .venv, etc.)

2. **Examine specific files**: Use `scan_file()` for detailed structure
   - Full tree with methods, signatures, decorators, docstrings
   - Precise line numbers for each element

3. **Search for patterns**: Use `search_structures()` for semantic code search
   - Find classes, functions by type, name pattern, or decorator

4. **Read targeted content**: Use Read tool only after identifying exact line ranges

### 1. scan_file - Analyze a single file

```python
scan_file(
    file_path="path/to/your/file.py",
    show_signatures=True,      # Include function signatures with types
    show_decorators=True,      # Include @decorator annotations
    show_docstrings=True,      # Include first line of docstrings
    show_complexity=False,     # Show complexity metrics (lines, depth, branches)
    output_format="tree"       # "tree" or "json"
)
```

### 2. scan_directory - Compact codebase overview

Shows directory tree with **inline** class/function names for each file.

```python
scan_directory(
    directory="./src",
    pattern="**/*",                 # Glob pattern (default: "**/*" = all files)
                                    # "**/*.py" = all Python files
                                    # "*/*" = 1 level deep only
                                    # "src/**/*.{py,ts}" = Python/TypeScript in src/
    max_files=None,                 # Limit number of files (default: None)
    respect_gitignore=True,         # Respect .gitignore (default: True)
    exclude_patterns=None,          # Additional exclusions (gitignore syntax)
    output_format="tree"            # "tree" or "json"
)
```

**Output format (compact inline):**
```
src/ (22 files, 15 classes, 127 functions, 89 methods)
├─ scanners/
│  ├─ python_scanner.py (1-329) [11.9KB, 2 hours ago] - PythonScanner
│  ├─ typescript_scanner.py (1-505) [18.9KB, 1 day ago] - TypeScriptScanner
│  └─ rust_scanner.py (1-481) [17.6KB, 3 days ago] - RustScanner
├─ scanner.py (1-232) [8.8KB, 5 mins ago] - FileScanner
├─ formatter.py (1-153) [5.7KB, 10 mins ago] - TreeFormatter
└─ server.py (1-353) [12.2KB, just now] - scan_file, scan_directory, search_structures, _filter_structures, _structures_to_json, ... (6 total)
```

**Controlling scope:**

```python
# Specific file types
scan_directory("./src", pattern="**/*.py")

# Multiple types (brace expansion)
scan_directory("./src", pattern="**/*.{py,ts,js}")

# Shallow scan (1 level deep)
scan_directory(".", pattern="*/*")

# Exclude directories (respects .gitignore by default)
scan_directory(".", exclude_patterns=["tests/**", "docs/**"])

# Scan everything (ignores .gitignore)
scan_directory(".", respect_gitignore=False)
```

### 3. search_structures - Find and filter structures

```python
# Find all test functions
search_structures(
    directory="./tests",
    type_filter="function",
    name_pattern="^test_"
)

# Find all classes ending in "Manager"
search_structures(
    directory="./src",
    type_filter="class",
    name_pattern=".*Manager$"
)

# Find functions with @staticmethod decorator
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

### Example Output

#### scan_file() - Detailed structure

Full hierarchical tree with methods, signatures, and metadata:

##### Python File
```
example.py (1-57)
├─ file-info: 1.4KB modified: 2 hours ago
├─ imports: import statements (3-5)
├─ class: DatabaseManager (8-26)
│    "Manages database connections and queries."
│  ├─ method: __init__ (self, connection_string: str) (11-13)
│  ├─ method: connect (self) (15-17)
│  │    "Establish database connection."
│  ├─ method: disconnect (self) (19-22)
│  │    "Close database connection."
│  └─ method: query (self, sql: str) -> list (24-26)
│       "Execute a SQL query."
├─ class: UserService (29-45)
│    "Handles user-related operations."
│  ├─ method: __init__ (self, db: DatabaseManager) (32-33)
│  ├─ method: create_user (self, username: str, email: str) -> int (35-37)
│  │    "Create a new user."
│  ├─ method: get_user (self, user_id: int) -> Optional[dict] (39-41)
│  │    "Retrieve user by ID."
│  └─ method: delete_user (self, user_id: int) -> bool (43-45)
│       "Delete a user."
├─ function: validate_email (email: str) -> bool (48-50)
│    "Validate email format."
└─ function: main () (53-57)
     "Main entry point."
```

#### TypeScript File
```
example.ts (1-114)
├─ file-info: 2.2KB modified: 1 day ago
├─ imports: import statements (5-6)
├─ interface: Config (11-14)
│    "Configuration interface for authentication service."
├─ class: AuthService (19-52)
│    "Service for handling user authentication and authorization."
│  ├─ method: constructor (config: Config) (26-29)
│  │    "Constructs a new AuthService instance."
│  ├─ method: login (username: string, password: string) : Promise<User | null> (34-37) [async]
│  │    "Authenticates a user with username and password."
│  ├─ method: logout (userId: string) : Promise<void> (42-44) [async]
│  │    "Logs out a user by their ID."
│  └─ method: validateToken (token: string) : boolean (49-51)
│       "Validates an authentication token."
├─ class: UserManager (57-90)
│    "Manager class for user CRUD operations."
│  ├─ method: constructor (database: Database) (60-62)
│  ├─ method: createUser (username: string, email: string) : Promise<User> (67-75) [async]
│  │    "Creates a new user in the system."
│  ├─ method: getUser (id: string) : Promise<User | null> (80-82) [async]
│  │    "Retrieves a user by their ID."
│  └─ method: updateUser (id: string, data: Partial<User>) : Promise<User> (87-89) [async]
│       "Updates a user's information."
├─ function: generateId () : string (95-97)
│    "Generates a random unique identifier."
├─ function: validateEmail (email: string) : boolean (102-104)
│    "Validates an email address format."
└─ function: calculateStats (users: User[]) : { total: number; active: number } (109-114)
     "Arrow function to calculate statistics."
```

#### Markdown File
```
example.md (1-119)
├─ file-info: 1.6KB modified: 3 hours ago
├─ heading-1: Project Documentation (1-98)
│  ├─ heading-2: Installation (5-23)
│  │  ├─ code-block: code block (bash) bash (9-12)
│  │  └─ heading-3: Quick Start (13-23)
│  │     └─ code-block: code block (python) python (17-23)
│  ├─ heading-2: Features (24-47)
│  │  ├─ code-block: code block (typescript) typescript (28-34)
│  │  └─ heading-3: Advanced Usage (35-47)
│  │     └─ code-block: code block (python) python (39-47)
│  ├─ heading-2: Configuration (48-60)
│  │  └─ heading-3: Environment Variables (52-60)
│  │     └─ code-block: code block (bash) bash (56-60)
│  └─ heading-2: API Reference (61-76)
│     ├─ heading-3: FileScanner Class (65-68)
│     └─ heading-3: TreeFormatter Class (69-76)
│        └─ heading-4: Options (73-76)
```

#### Plain Text File
```
example.txt (1-77)
├─ file-info: 2.5KB modified: 5 mins ago
├─ section: PROJECT OVERVIEW (1-6)
│  └─ paragraph: paragraph (4-5) (4-5)
├─ section: INTRODUCTION (7-12)
│  └─ paragraph: paragraph (9-11) (9-11)
├─ section: Features and Capabilities (13-23)
│  ├─ paragraph: paragraph (16-16) (16-16)
│  ├─ paragraph: paragraph (18-19) (18-19)
│  └─ paragraph: paragraph (21-22) (21-22)
├─ section: TECHNICAL DETAILS (24-33)
│  ├─ paragraph: paragraph (26-29) (26-29)
│  └─ paragraph: paragraph (31-32) (31-32)
└─ section: CONCLUSION (67-77)
   ├─ paragraph: paragraph (70-71) (70-71)
   └─ paragraph: paragraph (73-74) (73-74)
```

#### Image File
```
logo.png (1-1)
├─ file-info: 45KB modified: 2025-10-15
├─ format: PNG - RGBA (1-1)
│    "Format: PNG, Color mode: RGBA"
├─ dimensions: 512×512 (1-1)
│    "Aspect ratio: 1:1 (square)"
├─ content-type: logo (1-1)
│    "Inferred based on size and format"
├─ colors: palette (1-1)
│  ├─ color: #ff5733 (1-1)
│  ├─ color: #33ff57 (1-1)
│  └─ color: #3357ff (1-1)
└─ transparency: has alpha channel (1-1)
```

### JSON Output Format

Use `output_format="json"` for structured data:

```json
{
  "file": "example.py",
  "structures": [
    {
      "type": "class",
      "name": "DatabaseManager",
      "start_line": 8,
      "end_line": 26,
      "docstring": "Manages database connections and queries.",
      "children": [
        {
          "type": "method",
          "name": "__init__",
          "start_line": 11,
          "end_line": 13,
          "signature": "(self, connection_string: str)",
          "children": []
        },
        {
          "type": "method",
          "name": "query",
          "start_line": 24,
          "end_line": 26,
          "signature": "(self, sql: str) -> list",
          "docstring": "Execute a SQL query.",
          "modifiers": ["async"],
          "children": []
        }
      ]
    }
  ]
}
```

## Supported File Types

| Extension | Language | Extracted Elements |
|-----------|----------|-------------------|
| `.py`, `.pyw` | Python | classes, methods, functions, imports, decorators, docstrings |
| `.js`, `.jsx`, `.mjs`, `.cjs` | JavaScript | classes, methods, functions, imports, JSDoc comments |
| `.ts`, `.tsx`, `.mts`, `.cts` | TypeScript | classes, methods, functions, imports, type annotations, JSDoc |
| `.rs` | Rust | structs, enums, traits, impl blocks, functions, use statements, attributes |
| `.go` | Go | types, structs, interfaces, functions, methods, imports |
| `.c`, `.h` | C | functions, structs, enums, includes, comments |
| `.cpp`, `.hpp`, `.cc`, `.hh`, `.cxx`, `.hxx` | C++ | classes, functions, namespaces, templates, includes |
| `.java` | Java | classes, methods, interfaces, enums, annotations, imports |
| `.php`, `.phtml` | PHP | classes, methods, functions, traits, interfaces, namespaces, attributes |
| `.cs`, `.csx` | C# | classes, methods, properties, structs, enums, namespaces, attributes |
| `.rb`, `.rake`, `.gemspec` | Ruby | modules, classes, methods, singleton methods, comments |
| `.md` | Markdown | headings (h1-h6), code blocks with hierarchy |
| `.txt` | Plain Text | sections (all-caps, underlined), paragraphs |
| `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`, `.ico` | Images | format, dimensions, colors, content type, optimization hints |

**Note**: All files automatically include file metadata (size, modified date, permissions) as the first structure node.

## Use Cases

### Code Navigation & Understanding
- Get structural overview of unfamiliar codebases
- Understand file organization before reading code
- Navigate large files using precise line ranges

### Refactoring & Reorganization
- Identify class and function boundaries for safe splitting
- Find all implementations of specific patterns (e.g., all Manager classes)
- Locate functions above complexity thresholds for refactoring

### Code Review & Analysis
- Generate structural diffs between versions
- Find all functions with specific decorators
- Identify test coverage gaps by searching test_ patterns

### Documentation & Tooling
- Auto-generate table of contents with line numbers
- Extract API signatures for documentation
- Feed structured data to other analysis tools (JSON output)

### AI Code Assistance
- **Primary exploration tool**: Prefer scantool over Glob/Grep/Read for initial codebase exploration
- Partition large files intelligently for LLM context windows
- Extract relevant code sections with exact boundaries
- Search for specific patterns across entire codebases
- Reduce token usage by getting structure first, reading content only when needed

### Image & Asset Analysis
- **Quick asset inventory**: Scan image directories to understand formats and sizes
- **Optimization opportunities**: Find oversized images, unused alpha channels, inefficient formats
- **Color palette extraction**: Discover dominant colors for branding and design consistency
- **Content categorization**: Auto-detect icons, logos, photos, screenshots by size/format
- **Format recommendations**: Get suggestions for WebP conversion, JPEG vs PNG optimization

## Architecture

```
scantool/
├── scanner.py     # Core scanning logic using tree-sitter
├── formatter.py   # Pretty tree formatting with box-drawing characters
├── server.py      # FastMCP server implementation
└── tests/         # Test suite organized by language
    ├── python/
    ├── typescript/
    ├── text/
    ├── test_integration.py
    └── conftest.py
```

## Testing

Run tests using pytest:

```bash
# Run all tests
uv run pytest

# Run specific language tests
uv run pytest tests/python/
uv run pytest tests/typescript/
uv run pytest tests/text/

# Run with coverage
uv run pytest --cov=src/scantool

# Run with verbose output
uv run pytest -v
```

Tests are organized by language in `tests/python/`, `tests/typescript/`, and `tests/text/` directories.

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

Claude Desktop enforces a 25,000 token limit on MCP tool responses.

**Built-in mitigations:**
- `scan_directory()` uses compact inline format (not full tree expansion)
- Respects `.gitignore` by default (excludes node_modules, .venv, etc.)
- Shows file metadata with relative timestamps (e.g., "2 hours ago")

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
