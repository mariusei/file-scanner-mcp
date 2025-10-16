# File Scanner MCP Documentation

Complete guide to using the File Scanner MCP server for extracting file structure.

## Overview

The File Scanner MCP provides a powerful tool for analyzing source code structure across multiple programming languages.

### Key Features

- Multi-language support
- Beautiful tree formatting
- Precise line number tracking
- Safe partitioning information

### Supported Languages

Currently supports:
- Python
- JavaScript & TypeScript
- Rust
- Go
- Markdown

## Installation

### Prerequisites

Ensure you have Python 3.13+ and uv installed.

### Quick Install

```bash
uvx scantool
```

### From Source

```bash
git clone https://github.com/yourusername/scantool.git
cd scantool
uv sync
```

## Usage

### Basic Usage

Scan a single file:

```python
scan_file(file_path="path/to/file.py")
```

### Advanced Examples

#### Python Files

```python
# Scan a Python module
result = scan_file("myapp/models.py")
print(result)
```

#### TypeScript Files

```typescript
// Example TypeScript scanning
const result = scanFile("src/index.ts");
```

## API Reference

### scan_file

Scans a source file and returns its structure.

**Parameters:**
- `file_path` (str): Path to the file to scan

**Returns:**
- str: Formatted tree structure with line numbers

## Configuration

### MCP Settings

Add to your Claude Desktop config:

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

## Examples

### Output Format

The scanner returns beautifully formatted output showing the file structure.

## Contributing

We welcome contributions! Please see our contributing guidelines.

### Development Setup

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions, please visit our GitHub repository.
