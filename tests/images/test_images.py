"""Tests for image scanner."""

import pytest
from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic image file parsing."""
    structures = file_scanner.scan_file("tests/images/samples/test_logo.png")
    assert structures is not None, "Should parse image file"
    assert len(structures) > 0, "Should find structures"

    # Verify file-info is present (with new file metadata feature)
    file_info = structures[0]
    assert file_info.type == "file-info", "First node should be file-info"
    assert file_info.file_metadata is not None, "Should have file metadata"

    # Verify expected image structures (skip file-info node)
    image_structures = structures[1:]
    assert any(s.type == "format" for s in image_structures), "Should find format info"
    assert any(s.type == "dimensions" for s in image_structures), "Should find dimensions"
    assert any(s.type == "content-type" for s in image_structures), "Should find content type"


def test_png_with_transparency(file_scanner):
    """Test PNG with alpha channel detection."""
    structures = file_scanner.scan_file("tests/images/samples/test_logo.png")
    image_structures = [s for s in structures if s.type != "file-info"]

    # Find transparency node
    transparency = next((s for s in image_structures if s.type == "transparency"), None)
    assert transparency is not None, "Should detect transparency in RGBA PNG"
    assert "alpha" in transparency.name.lower(), "Should mention alpha channel"


def test_jpeg_format(file_scanner):
    """Test JPEG format detection."""
    structures = file_scanner.scan_file("tests/images/samples/test_photo.jpg")
    image_structures = [s for s in structures if s.type != "file-info"]

    # Find format node
    format_node = next((s for s in image_structures if s.type == "format"), None)
    assert format_node is not None, "Should find format"
    assert "JPEG" in format_node.name, "Should detect JPEG format"
    assert "RGB" in format_node.name, "Should show RGB mode"


def test_dimensions_and_aspect_ratio(file_scanner):
    """Test dimension extraction and aspect ratio calculation."""
    structures = file_scanner.scan_file("tests/images/samples/test_photo.jpg")
    image_structures = [s for s in structures if s.type != "file-info"]

    # Find dimensions node
    dimensions = next((s for s in image_structures if s.type == "dimensions"), None)
    assert dimensions is not None, "Should find dimensions"
    assert "1920×1080" in dimensions.name, "Should show correct dimensions"
    assert dimensions.docstring is not None, "Should have aspect ratio in docstring"
    assert "16:9" in dimensions.docstring, "Should detect 16:9 aspect ratio"


def test_content_type_inference(file_scanner):
    """Test content type inference (icon, logo, photo, etc.)."""
    # Test icon detection (small)
    structures = file_scanner.scan_file("tests/images/samples/test_icon.png")
    image_structures = [s for s in structures if s.type != "file-info"]
    content_type = next((s for s in image_structures if s.type == "content-type"), None)
    assert content_type is not None, "Should infer content type"
    assert content_type.name == "icon", "Should detect icon based on size"

    # Test logo detection (medium with transparency)
    structures = file_scanner.scan_file("tests/images/samples/test_logo.png")
    image_structures = [s for s in structures if s.type != "file-info"]
    content_type = next((s for s in image_structures if s.type == "content-type"), None)
    assert content_type.name == "logo", "Should detect logo based on size and transparency"


def test_color_extraction(file_scanner):
    """Test dominant color extraction."""
    structures = file_scanner.scan_file("tests/images/samples/test_logo.png")
    image_structures = [s for s in structures if s.type != "file-info"]

    # Find colors node
    colors = next((s for s in image_structures if s.type == "colors"), None)
    assert colors is not None, "Should extract colors"
    assert colors.name == "palette", "Should have palette name"
    assert len(colors.children) > 0, "Should have color children"

    # Verify color format
    for color in colors.children:
        assert color.type == "color", "Children should be color nodes"
        assert color.name.startswith("#"), "Colors should be in hex format"
        assert len(color.name) == 7, "Hex colors should be 7 chars (#rrggbb)"


def test_optimization_hints(file_scanner):
    """Test optimization hint generation."""
    structures = file_scanner.scan_file("tests/images/samples/large_noisy.png")
    image_structures = [s for s in structures if s.type != "file-info"]

    # Find optimization node
    optimization = next((s for s in image_structures if s.type == "optimization"), None)
    assert optimization is not None, "Should provide optimization hints for large PNG"
    assert len(optimization.children) > 0, "Should have optimization suggestions"

    # Check for specific hints
    hints = [h.name for h in optimization.children]
    assert any("JPEG" in h for h in hints), "Should suggest JPEG for large RGB PNG"
    assert any("size" in h.lower() for h in hints), "Should mention large file size"


def test_unused_alpha_detection(file_scanner):
    """Test detection of unused alpha channel."""
    structures = file_scanner.scan_file("tests/images/samples/unused_alpha.png")
    image_structures = [s for s in structures if s.type != "file-info"]

    # Find optimization hints
    optimization = next((s for s in image_structures if s.type == "optimization"), None)
    assert optimization is not None, "Should have optimization hints"

    hints = [h.name for h in optimization.children]
    assert any("alpha" in h.lower() and "unused" in h.lower() for h in hints), \
        "Should detect unused alpha channel"


def test_file_metadata_included(file_scanner):
    """Test that file metadata is included for all images."""
    structures = file_scanner.scan_file("tests/images/samples/test_icon.png")

    # First node should be file-info
    assert structures[0].type == "file-info", "First node should be file-info"

    metadata = structures[0].file_metadata
    assert metadata is not None, "Should have file metadata"
    assert "size" in metadata, "Should include size in bytes"
    assert "size_formatted" in metadata, "Should include formatted size"
    assert "modified" in metadata, "Should include modified timestamp"
    assert "created" in metadata, "Should include created timestamp"
    assert "permissions" in metadata, "Should include permissions"


def test_error_handling():
    """Test that malformed/corrupted images are handled without crashing."""
    scanner = FileScanner(show_errors=True)

    # Create a fake corrupted image file
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as f:
        f.write(b"not a valid image")
        temp_path = f.name

    try:
        # Should not crash on corrupted file
        structures = scanner.scan_file(temp_path)
        assert structures is not None, "Should return structures even for corrupted file"

        # Should have error node (after file-info)
        image_structures = [s for s in structures if s.type != "file-info"]
        assert any(s.type == "error" for s in image_structures), \
            "Should include error node for corrupted file"
    finally:
        os.unlink(temp_path)


def test_multiple_formats(file_scanner):
    """Test that scanner handles multiple image formats."""
    formats = [
        ("tests/images/samples/test_logo.png", "PNG"),
        ("tests/images/samples/test_photo.jpg", "JPEG"),
    ]

    for file_path, expected_format in formats:
        structures = file_scanner.scan_file(file_path)
        image_structures = [s for s in structures if s.type != "file-info"]
        format_node = next((s for s in image_structures if s.type == "format"), None)
        assert format_node is not None, f"Should parse {expected_format} file"
        assert expected_format in format_node.name, f"Should detect {expected_format} format"


def test_scanner_registry(file_scanner):
    """Test that image scanner is properly registered."""
    extensions = file_scanner.get_supported_extensions()

    # Check for image extensions
    image_exts = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico']
    for ext in image_exts:
        assert ext in extensions, f"{ext} should be supported"

    # Check scanner info
    scanner_info = file_scanner.get_scanner_info()
    assert '.png' in scanner_info, "PNG should be in scanner info"
    assert scanner_info['.png'] == 'Image', "PNG should map to Image scanner"
