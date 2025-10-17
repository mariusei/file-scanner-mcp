"""Tests for Text scanner."""

from pathlib import Path


def test_basic_parsing(file_scanner):
    """Test basic text file parsing."""
    test_dir = Path(__file__).parent
    structures = file_scanner.scan_file(str(test_dir / "samples" / "basic.txt"))
    assert structures is not None, "Should parse text file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected structures
    assert any(s.type == "section" and "PROJECT OVERVIEW" in s.name for s in structures)
    assert any(s.type == "section" and "INTRODUCTION" in s.name for s in structures)

    # Check that sections have paragraphs
    project_section = next(s for s in structures if "PROJECT OVERVIEW" in s.name)
    assert len(project_section.children) > 0, "Section should have paragraphs"


def test_section_detection(file_scanner):
    """Test different section header formats."""
    test_dir = Path(__file__).parent
    structures = file_scanner.scan_file(str(test_dir / "samples" / "edge_cases.txt"))

    # All-caps sections
    assert any(s.type == "section" and s.name.isupper() for s in structures), "Should find all-caps sections"

    # Underlined sections
    underlined = [s for s in structures if "underline" in s.name.lower()]
    assert len(underlined) > 0, "Should find underlined sections"


def test_paragraph_detection(file_scanner):
    """Test paragraph extraction."""
    test_dir = Path(__file__).parent
    structures = file_scanner.scan_file(str(test_dir / "samples" / "basic.txt"))

    # Count paragraphs
    total_paragraphs = 0
    for section in structures:
        if section.type == "section":
            total_paragraphs += len([c for c in section.children if c.type == "paragraph"])

    assert total_paragraphs > 0, "Should find paragraphs"


def test_edge_cases(file_scanner):
    """Test edge cases."""
    test_dir = Path(__file__).parent
    structures = file_scanner.scan_file(str(test_dir / "samples" / "edge_cases.txt"))

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    # Test long name truncation
    long_section = next((s for s in structures if "EXCEED" in s.name), None)
    assert long_section is not None, "Should find long section name"
    assert len(long_section.name) <= 50, f"Section name should be truncated to 50 chars, got {len(long_section.name)}"

    # Test Unicode handling
    unicode_section = next((s for s in structures if "UNICODE" in s.name), None)
    assert unicode_section is not None, "Should handle Unicode section names"

    # Test very short sections
    short_sections = [s for s in structures if len(s.name) <= 5 and s.type == "section"]
    assert len(short_sections) > 0, "Should handle very short section names"


def test_empty_sections(file_scanner):
    """Test sections with no content."""
    test_dir = Path(__file__).parent
    structures = file_scanner.scan_file(str(test_dir / "samples" / "edge_cases.txt"))

    # Find section with no content
    no_content = next((s for s in structures if "NO CONTENT" in s.name), None)
    assert no_content is not None, "Should find section with no content"
    # It's okay to have 0 children for empty sections
    assert len(no_content.children) == 0, "Empty section should have no children"


def test_line_numbers(file_scanner):
    """Test that line numbers are accurate."""
    test_dir = Path(__file__).parent
    structures = file_scanner.scan_file(str(test_dir / "samples" / "basic.txt"))

    for section in structures:
        # Line numbers should be valid
        assert section.start_line > 0, "Start line should be positive"
        assert section.end_line >= section.start_line, "End line should be >= start line"

        # Check children
        for para in section.children:
            assert para.start_line >= section.start_line, "Child should start after parent"
            assert para.end_line <= section.end_line, "Child should end before parent"


def test_unicode_content(file_scanner):
    """Test Unicode character handling."""
    test_dir = Path(__file__).parent
    structures = file_scanner.scan_file(str(test_dir / "samples" / "edge_cases.txt"))

    # Should not crash on Unicode
    assert structures is not None, "Should handle Unicode content"

    # Find Unicode section
    unicode_section = next((s for s in structures if "UNICODE" in s.name), None)
    assert unicode_section is not None, "Should parse Unicode section"


def test_mixed_formatting(file_scanner):
    """Test files with mixed formatting."""
    test_dir = Path(__file__).parent
    structures = file_scanner.scan_file(str(test_dir / "samples" / "edge_cases.txt"))

    # Should handle mixed all-caps and underlined headers
    all_caps = [s for s in structures if s.name.isupper() and s.type == "section"]
    mixed_case = [s for s in structures if not s.name.isupper() and s.type == "section"]

    assert len(all_caps) > 0, "Should find all-caps sections"
    assert len(mixed_case) > 0, "Should find mixed-case sections"
