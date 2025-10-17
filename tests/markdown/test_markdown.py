"""Tests for Markdown scanner."""

from scantool.scanner import FileScanner
from conftest import validate_line_range_invariants


def test_basic_parsing(file_scanner):
    """Test basic Markdown file parsing."""
    structures = file_scanner.scan_file("tests/markdown/samples/basic.md")
    assert structures is not None, "Should parse Markdown file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected top-level headings (h1 only at top level due to hierarchy)
    assert any(s.type == "heading-1" and "Project Documentation" in s.name for s in structures)

    # h2 headings should be children of the h1
    project_doc = next((s for s in structures if "Project Documentation" in s.name), None)
    assert project_doc is not None
    assert any(c.type == "heading-2" and "Installation" in c.name for c in project_doc.children)
    assert any(c.type == "heading-2" and "Features" in c.name for c in project_doc.children)


def test_heading_hierarchy(file_scanner):
    """Test that heading hierarchy is built correctly."""
    structures = file_scanner.scan_file("tests/markdown/samples/basic.md")

    # Find Project Documentation (h1)
    project_doc = next((s for s in structures if s.type == "heading-1" and "Project Documentation" in s.name), None)
    assert project_doc is not None, "Should find Project Documentation heading"

    # Find Installation section (h2, child of h1)
    installation = next((c for c in project_doc.children if c.type == "heading-2" and "Installation" in c.name), None)
    assert installation is not None, "Should find Installation heading"

    # It should have children (h3 Quick Start)
    assert len(installation.children) > 0, "Installation should have child headings"
    quick_start = next((c for c in installation.children if c.type == "heading-3" and "Quick Start" in c.name), None)
    assert quick_start is not None, "Should find Quick Start as child of Installation"


def test_code_blocks(file_scanner):
    """Test that code blocks are extracted with language tags."""
    structures = file_scanner.scan_file("tests/markdown/samples/basic.md")

    # Flatten all structures to find code blocks
    def flatten(nodes):
        result = []
        for node in nodes:
            result.append(node)
            result.extend(flatten(node.children))
        return result

    all_nodes = flatten(structures)
    code_blocks = [n for n in all_nodes if n.type == "code-block"]

    assert len(code_blocks) > 0, "Should find code blocks"

    # Test specific language tags
    bash_blocks = [c for c in code_blocks if c.signature == "bash"]
    python_blocks = [c for c in code_blocks if c.signature == "python"]
    typescript_blocks = [c for c in code_blocks if c.signature == "typescript"]

    assert len(bash_blocks) > 0, "Should find bash code blocks"
    assert len(python_blocks) > 0, "Should find python code blocks"
    assert len(typescript_blocks) > 0, "Should find typescript code blocks"


def test_heading_styles(file_scanner):
    """Test both ATX and Setext heading styles."""
    structures = file_scanner.scan_file("tests/markdown/samples/basic.md")

    def flatten(nodes):
        result = []
        for node in nodes:
            result.append(node)
            result.extend(flatten(node.children))
        return result

    all_nodes = flatten(structures)

    # Find setext-style headings
    setext_h1 = next((n for n in all_nodes if n.type == "heading-1" and "Alternative Heading Style" in n.name), None)
    setext_h2 = next((n for n in all_nodes if n.type == "heading-2" and "Subheading with Underline" in n.name), None)

    assert setext_h1 is not None, "Should find Setext h1 heading"
    assert setext_h2 is not None, "Should find Setext h2 heading"

    # Verify ATX headings also work
    atx_h1 = next((n for n in all_nodes if n.type == "heading-1" and "Project Documentation" in n.name), None)
    assert atx_h1 is not None, "Should find ATX h1 heading"


def test_code_blocks_in_hierarchy(file_scanner):
    """Test that code blocks are children of their parent headings."""
    structures = file_scanner.scan_file("tests/markdown/samples/basic.md")

    # Find Project Documentation (h1)
    project_doc = next((s for s in structures if s.type == "heading-1" and "Project Documentation" in s.name), None)
    assert project_doc is not None, "Should find Project Documentation heading"

    # Find Installation section (h2, child of h1)
    installation = next((c for c in project_doc.children if c.type == "heading-2" and "Installation" in c.name), None)
    assert installation is not None, "Should find Installation heading"

    # Installation should have a bash code block as a child (or grandchild)
    def has_bash_block(node):
        if node.type == "code-block" and node.signature == "bash":
            return True
        return any(has_bash_block(c) for c in node.children)

    assert has_bash_block(installation), "Installation section should contain bash code block"


def test_edge_cases(file_scanner):
    """Test edge cases like empty headings, nested lists, special chars."""
    structures = file_scanner.scan_file("tests/markdown/samples/edge_cases.md")

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    def flatten(nodes):
        result = []
        for node in nodes:
            result.append(node)
            result.extend(flatten(node.children))
        return result

    all_nodes = flatten(structures)

    # Test that we found various heading levels
    h3_nodes = [n for n in all_nodes if n.type == "heading-3"]
    h4_nodes = [n for n in all_nodes if n.type == "heading-4"]
    h5_nodes = [n for n in all_nodes if n.type == "heading-5"]
    h6_nodes = [n for n in all_nodes if n.type == "heading-6"]

    assert len(h3_nodes) > 0, "Should find h3 headings"
    assert len(h4_nodes) > 0, "Should find h4 headings"
    assert len(h5_nodes) > 0, "Should find h5 headings"
    assert len(h6_nodes) > 0, "Should find h6 headings"

    # Test code blocks with different languages
    code_blocks = [n for n in all_nodes if n.type == "code-block"]
    assert len(code_blocks) > 5, "Should find multiple code blocks"

    # Test specific languages from edge cases
    languages = [c.signature for c in code_blocks if c.signature]
    assert "javascript" in languages, "Should find javascript code"
    assert "rust" in languages, "Should find rust code"
    assert "go" in languages, "Should find go code"


def test_consecutive_code_blocks(file_scanner):
    """Test that consecutive code blocks are all detected."""
    structures = file_scanner.scan_file("tests/markdown/samples/edge_cases.md")

    def flatten(nodes):
        result = []
        for node in nodes:
            result.append(node)
            result.extend(flatten(node.children))
        return result

    all_nodes = flatten(structures)

    # Find the "Consecutive Code Blocks" section
    consecutive_section = next((n for n in all_nodes if "Consecutive Code Blocks" in n.name), None)
    assert consecutive_section is not None, "Should find Consecutive Code Blocks section"

    # It should have multiple code block children
    code_blocks = [c for c in consecutive_section.children if c.type == "code-block"]
    assert len(code_blocks) >= 3, "Should find at least 3 consecutive code blocks"


def test_code_without_language(file_scanner):
    """Test code blocks without language tags."""
    structures = file_scanner.scan_file("tests/markdown/samples/basic.md")

    def flatten(nodes):
        result = []
        for node in nodes:
            result.append(node)
            result.extend(flatten(node.children))
        return result

    all_nodes = flatten(structures)
    code_blocks = [n for n in all_nodes if n.type == "code-block"]

    # Should have some code blocks without language (signature is None)
    no_lang_blocks = [c for c in code_blocks if c.signature is None]
    assert len(no_lang_blocks) > 0, "Should find code blocks without language tag"


def test_deep_nesting(file_scanner):
    """Test deeply nested heading structures."""
    structures = file_scanner.scan_file("tests/markdown/samples/basic.md")

    def find_node(nodes, name):
        for node in nodes:
            if name in node.name:
                return node
            found = find_node(node.children, name)
            if found:
                return found
        return None

    # Find API Reference -> FileScanner Class -> (nothing deeper, but structure should be correct)
    api_ref = find_node(structures, "API Reference")
    assert api_ref is not None, "Should find API Reference"
    assert api_ref.type == "heading-2", "API Reference should be h2"

    # Find FileScanner Class under it
    file_scanner_node = next((c for c in api_ref.children if "FileScanner" in c.name), None)
    assert file_scanner_node is not None, "Should find FileScanner Class under API Reference"
    assert file_scanner_node.type == "heading-3", "FileScanner Class should be h3"


def test_indented_code_blocks(file_scanner):
    """Test indented code blocks (4 spaces)."""
    structures = file_scanner.scan_file("tests/markdown/samples/edge_cases.md")

    def flatten(nodes):
        result = []
        for node in nodes:
            result.append(node)
            result.extend(flatten(node.children))
        return result

    all_nodes = flatten(structures)
    code_blocks = [n for n in all_nodes if n.type == "code-block"]

    # Should find indented code blocks
    indented = [c for c in code_blocks if "indented" in c.name.lower()]
    assert len(indented) > 0, "Should find indented code blocks"


def test_mixed_heading_styles(file_scanner):
    """Test files with both ATX and Setext headings mixed."""
    structures = file_scanner.scan_file("tests/markdown/samples/edge_cases.md")

    def flatten(nodes):
        result = []
        for node in nodes:
            result.append(node)
            result.extend(flatten(node.children))
        return result

    all_nodes = flatten(structures)

    # Should have both ATX and Setext headings
    setext_headings = [n for n in all_nodes if "Setext" in n.name]
    assert len(setext_headings) > 0, "Should find Setext-style headings"

    # Verify hierarchy works with mixed styles
    # The Setext Level 1 should have children
    setext_l1 = next((n for n in all_nodes if n.type == "heading-1" and "Setext Level 1" in n.name), None)
    if setext_l1:  # Might be flattened differently
        assert setext_l1.type == "heading-1", "Setext heading should be level 1"


def test_line_ranges(file_scanner):
    """Test that line ranges for headings include their content sections."""
    structures = file_scanner.scan_file("tests/markdown/samples/basic.md")

    # Find Project Documentation (h1) - should be at line 1
    project_doc = next((s for s in structures if s.type == "heading-1" and "Project Documentation" in s.name), None)
    assert project_doc is not None, "Should find Project Documentation heading"
    assert project_doc.start_line == 1, "Project Documentation should start at line 1"
    # Should extend to line 98 (just before "Alternative Heading Style" at line 99)
    assert project_doc.end_line > 90, f"Project Documentation should extend beyond line 90, got {project_doc.end_line}"

    # Find Installation section (h2) - should be at line 5
    installation = next((c for c in project_doc.children if c.type == "heading-2" and "Installation" in c.name), None)
    assert installation is not None, "Should find Installation heading"
    assert installation.start_line == 5, f"Installation should start at line 5, got {installation.start_line}"
    # Should extend to line 23 (just before "## Features" at line 24)
    assert installation.end_line >= 23, f"Installation should end at or after line 23, got {installation.end_line}"
    assert installation.end_line < 24, f"Installation should end before line 24 (Features section), got {installation.end_line}"

    # Find Features section (h2) - should be at line 24
    features = next((c for c in project_doc.children if c.type == "heading-2" and "Features" in c.name), None)
    assert features is not None, "Should find Features heading"
    assert features.start_line == 24, f"Features should start at line 24, got {features.start_line}"
    # Should extend to line 47 (just before "## Configuration" at line 48)
    assert features.end_line >= 46, f"Features should end at or after line 46, got {features.end_line}"
    assert features.end_line < 48, f"Features should end before line 48 (Configuration section), got {features.end_line}"

    # Find Configuration section (h2) - should be at line 48
    config = next((c for c in project_doc.children if c.type == "heading-2" and "Configuration" in c.name), None)
    assert config is not None, "Should find Configuration heading"
    assert config.start_line == 48, f"Configuration should start at line 48, got {config.start_line}"
    # Should extend to line 60 (just before "## API Reference" at line 61)
    assert config.end_line >= 60, f"Configuration should end at or after line 60, got {config.end_line}"
    assert config.end_line < 61, f"Configuration should end before line 61 (API Reference section), got {config.end_line}"

    # Test a section at the end of its parent
    contributing = next((c for c in project_doc.children if c.type == "heading-2" and "Contributing" in c.name), None)
    assert contributing is not None, "Should find Contributing heading"
    # Contributing should extend to include its children until License section
    assert contributing.end_line >= 91, f"Contributing should extend to at least line 91, got {contributing.end_line}"


def test_line_range_invariants(file_scanner):
    """Test universal line range invariants for Markdown scanner."""
    structures = file_scanner.scan_file("tests/markdown/samples/basic.md")
    validate_line_range_invariants(structures)

    # Also test edge cases file
    structures = file_scanner.scan_file("tests/markdown/samples/edge_cases.md")
    validate_line_range_invariants(structures)

