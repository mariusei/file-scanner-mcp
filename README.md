# File Scanner MCP

> Beautiful file scanner MCP that creates table of contents with line numbers for safe file partitioning.

A powerful MCP server that analyzes source code structure across multiple programming languages and returns beautifully formatted tree views with precise line ranges—perfect for safe file partitioning and code navigation.

## ✨ Features

- **🎨 Beautiful output**: Tree-formatted structure with box-drawing characters (├─, └─, │)
- **📍 Precise line numbers**: Every element shows (from-to) line ranges for safe partitioning
- **🌍 Multi-language support**: Python, JavaScript, TypeScript, Rust, Go, Markdown
- **🔍 Deep structure analysis**: Classes, methods, functions, imports, headings, code blocks
- **📊 Hierarchical display**: Nested structures shown with proper indentation

## 🚀 Quick Start

### Install with uvx (Recommended)

```bash
# From GitHub
uvx --from git+https://github.com/mariusei/file-scanner-mcp scantool

# Or if published to PyPI
uvx scantool
```

### Install from Source

```bash
git clone https://github.com/mariusei/file-scanner-mcp.git
cd file-scanner-mcp
uv sync
uv run scantool
```

## ⚙️ Configuration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "scantool": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/mariusei/file-scanner-mcp", "scantool"]
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

## 📖 Usage

The server provides a single tool: `scan_file`

```python
scan_file(file_path="path/to/your/file.py")
```

### Example Outputs

#### Python File
```
example.py (3-57)
├─ imports: import statements (3-5)
├─ class: DatabaseManager (8-26)
│  ├─ method: __init__ (11-13)
│  ├─ method: connect (15-17)
│  ├─ method: disconnect (19-22)
│  └─ method: query (24-26)
├─ class: UserService (29-45)
│  ├─ method: __init__ (32-33)
│  ├─ method: create_user (35-37)
│  ├─ method: get_user (39-41)
│  └─ method: delete_user (43-45)
├─ function: validate_email (48-50)
└─ function: main (53-57)
```

#### TypeScript File
```
example.ts (3-66)
├─ imports: import statements (3-4)
├─ class: AuthService (11-32)
│  ├─ method: constructor (15-18)
│  ├─ method: login (20-23)
│  ├─ method: logout (25-27)
│  └─ method: validateToken (29-31)
└─ class: UserManager (34-58)
   ├─ method: constructor (37-39)
   ├─ method: createUser (41-49)
   ├─ method: getUser (51-53)
   └─ method: updateUser (55-57)
```

#### Markdown File
```
example.md (1-123)
└─ heading-1: Documentation (1-2)
   ├─ heading-2: Overview (5-6)
   │  ├─ heading-3: Features (9-10)
   │  └─ heading-3: Installation (16-17)
   │     └─ code-block: ```bash``` (19-23)
   └─ heading-2: Usage (24-25)
      └─ heading-3: Examples (28-29)
```

## 🗂️ Supported File Types

| Extension | Language | Extracted Elements |
|-----------|----------|-------------------|
| `.py` | Python | classes, methods, functions, imports |
| `.js`, `.jsx` | JavaScript | classes, methods, functions, imports |
| `.ts`, `.tsx` | TypeScript | classes, methods, functions, imports |
| `.rs` | Rust | structs, enums, traits, impl blocks, functions, use statements |
| `.go` | Go | types, functions, methods, imports |
| `.md` | Markdown | headings (h1-h6), code blocks with hierarchy |

## 💡 Use Cases

- **Safe file partitioning**: Know exact line ranges for splitting large files
- **Code navigation**: Quickly understand file structure before diving in
- **Documentation**: Generate structural overviews automatically
- **Refactoring**: Identify boundaries for safe code reorganization
- **Code review**: Get quick structural overview before deep dive
- **LLM context optimization**: Partition files intelligently for AI code assistants

## 🏗️ Architecture

```
scantool/
├── scanner.py     # Core scanning logic using tree-sitter
├── formatter.py   # Pretty tree formatting with box-drawing characters
├── server.py      # FastMCP server implementation
└── tests/         # Comprehensive test suite
    ├── test_all.py
    └── samples/   # Example files for all supported languages
```

## 🧪 Testing

Run the comprehensive test suite:

```bash
uv run python tests/test_all.py
```

This tests scanning across all supported languages (Python, JavaScript, TypeScript, Rust, Go, Markdown).

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Add language support**: Implement new `_extract_*_structure` methods
2. **Improve formatting**: Enhance the tree output formatting
3. **Fix bugs**: Check the issues tab for known problems
4. **Add tests**: More test cases are always appreciated

### Development Setup

```bash
git clone https://github.com/mariusei/file-scanner-mcp.git
cd file-scanner-mcp
uv sync
uv run python tests/test_all.py
```

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Built with:
- [FastMCP](https://github.com/jlowin/fastmcp) - Fast, simple MCP server framework
- [tree-sitter](https://tree-sitter.github.io/) - Incremental parsing library
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer

## 📮 Support

- **Issues**: [GitHub Issues](https://github.com/mariusei/file-scanner-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/mariusei/file-scanner-mcp/discussions)

---

Made with ❤️ for developers who need to understand code structure quickly and safely.
