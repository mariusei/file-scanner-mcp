# Project Documentation

This is a sample Markdown file for testing the scanner.

## Installation

To install the package, run:

```bash
pip install scantool
```

### Quick Start

Here's a simple example:

```python
from scantool import FileScanner

scanner = FileScanner()
structures = scanner.scan_file("example.py")
```

## Features

The scanner supports multiple languages:

```typescript
interface User {
  name: string;
  email: string;
}
```

### Advanced Usage

For more control over the output:

```python
from scantool.formatter import TreeFormatter

formatter = TreeFormatter(
    show_signatures=True,
    show_decorators=True
)
```

## Configuration

Settings can be adjusted in the config file.

### Environment Variables

Set the following variables:

```bash
export SCANTOOL_DEBUG=1
export SCANTOOL_PATH=/usr/local/bin
```

## API Reference

Main components of the system.

### FileScanner Class

The main scanner class handles file parsing.

### TreeFormatter Class

Formats output as a tree structure.

#### Options

Multiple formatting options are available.

## Contributing

Guidelines for contributors.

### Code Style

Follow PEP 8 for Python code.

### Testing

Run the test suite:

```bash
pytest tests/
```

## License

MIT License

Copyright information goes here.

Alternative Heading Style
=========================

This is a level 1 heading using Setext style.

Subheading with Underline
--------------------------

This is a level 2 heading using Setext style.

Code without language tag:

```
plain text code block
no syntax highlighting
```

### Final Section

Closing remarks.
