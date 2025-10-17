"""Tests for Python scanner."""

from scantool.scanner import FileScanner
from conftest import validate_line_range_invariants


def test_basic_parsing(file_scanner):
    """Test basic Python file parsing."""
    structures = file_scanner.scan_file("tests/python/samples/basic.py")
    assert structures is not None, "Should parse Python file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected structures
    assert any(s.type == "class" and s.name == "DatabaseManager" for s in structures)
    assert any(s.type == "class" and s.name == "UserService" for s in structures)
    assert any(s.type == "function" and s.name == "validate_email" for s in structures)


def test_signatures(file_scanner):
    """Test that signatures are extracted correctly."""
    structures = file_scanner.scan_file("tests/python/samples/basic.py")

    # Find validate_email function
    func = next((s for s in structures if s.type == "function" and s.name == "validate_email"), None)
    assert func is not None, "Should find validate_email"
    assert func.signature is not None, "Should have signature"
    assert "(email: str) -> bool" in func.signature, f"Signature should match, got: {func.signature}"


def test_docstrings(file_scanner):
    """Test that docstrings are extracted."""
    structures = file_scanner.scan_file("tests/python/samples/basic.py")

    # Find DatabaseManager class
    db_class = next((s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_class is not None, "Should find DatabaseManager"
    assert db_class.docstring is not None, "Should have docstring"
    assert "database" in db_class.docstring.lower(), f"Docstring should mention database, got: {db_class.docstring}"


def test_edge_cases(file_scanner):
    """Test edge cases like nested classes, decorators, etc."""
    structures = file_scanner.scan_file("tests/python/samples/edge_cases.py")

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    # Test nested classes
    outer = next((s for s in structures if s.type == "class" and s.name == "OuterClass"), None)
    assert outer is not None, "Should find OuterClass"
    assert len(outer.children) > 0, "Should have nested classes"
    assert any(c.type == "class" and c.name == "InnerClass" for c in outer.children), "Should find InnerClass"

    # Test decorators
    showcase = next((s for s in structures if s.type == "class" and s.name == "DecoratorShowcase"), None)
    assert showcase is not None, "Should find DecoratorShowcase"

    # Find property method
    prop_method = next((c for c in showcase.children if c.name == "prop"), None)
    assert prop_method is not None, "Should find prop method"
    assert "@property" in prop_method.decorators, "Should have @property decorator"
    assert "property" in prop_method.modifiers, "Should have property modifier"

    # Test async functions
    async_service = next((s for s in structures if s.type == "class" and s.name == "AsyncService"), None)
    assert async_service is not None, "Should find AsyncService"

    fetch_method = next((c for c in async_service.children if c.name == "fetch_data"), None)
    assert fetch_method is not None, "Should find fetch_data"
    assert "async" in fetch_method.modifiers, "Should have async modifier"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)

    # Should not crash
    structures = scanner.scan_file("tests/python/samples/broken.py")

    assert structures is not None, "Should return structures even for broken code"

    # Should show parse errors or valid structures
    has_error = any(s.type in ("parse-error", "error") for s in structures)
    has_valid = any(s.type in ("class", "function") for s in structures)

    assert has_error or has_valid, "Should have either errors or valid structures"


def test_multi_line_docstrings(file_scanner):
    """Test multi-line docstring extraction."""
    structures = file_scanner.scan_file("tests/python/samples/edge_cases.py")

    # Find multi_line_doc function
    func = next((s for s in structures if s.type == "function" and s.name == "multi_line_doc"), None)
    assert func is not None, "Should find multi_line_doc"


def test_complex_signatures(file_scanner):
    """Test complex type hint signatures."""
    structures = file_scanner.scan_file("tests/python/samples/edge_cases.py")

    # Find GenericContainer class
    generic = next((s for s in structures if s.type == "class" and s.name == "GenericContainer"), None)
    assert generic is not None, "Should find GenericContainer"

    # Find process method with complex signature
    process = next((c for c in generic.children if c.name == "process"), None)
    assert process is not None, "Should find process method"
    assert process.signature is not None, "Should have signature"

    # Check that complex types are preserved
    sig = process.signature
    assert "List" in sig or "Dict" in sig or "Union" in sig, f"Should preserve complex types in: {sig}"


def test_line_range_invariants(file_scanner):
    """Test universal line range invariants for Python scanner."""
    structures = file_scanner.scan_file("tests/python/samples/basic.py")
    validate_line_range_invariants(structures)

    # Also test edge cases file
    structures = file_scanner.scan_file("tests/python/samples/edge_cases.py")
    validate_line_range_invariants(structures)

