"""Tests for Zig scanner."""

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic Zig file parsing."""
    structures = file_scanner.scan_file("tests/zig/samples/basic.zig")
    assert structures is not None, "Should parse Zig file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected structures
    assert any(s.type == "struct" and s.name == "Config" for s in structures)
    assert any(s.type == "enum" and s.name == "Status" for s in structures)
    assert any(s.type == "union" and s.name == "Result" for s in structures)
    assert any(s.type == "function" and s.name == "main" for s in structures)
    assert any(s.type == "function" and s.name == "helper" for s in structures)


def test_struct_methods(file_scanner):
    """Test that struct methods are extracted correctly."""
    structures = file_scanner.scan_file("tests/zig/samples/basic.zig")

    # Find Config struct
    config = next((s for s in structures if s.type == "struct" and s.name == "Config"), None)
    assert config is not None, "Should find Config struct"
    assert len(config.children) > 0, "Struct should have methods"

    # Check that methods are extracted
    assert any(c.type == "method" and c.name == "total" for c in config.children), \
        f"Should find total method, got: {[c.name for c in config.children]}"


def test_signatures(file_scanner):
    """Test that signatures are extracted correctly."""
    structures = file_scanner.scan_file("tests/zig/samples/basic.zig")

    # Find helper function
    func = next((s for s in structures if s.type == "function" and s.name == "helper"), None)
    assert func is not None, "Should find helper"
    assert func.signature is not None, "Should have signature"
    assert "x: i32" in func.signature, f"Signature should contain parameter, got: {func.signature}"
    assert "i32" in func.signature, f"Signature should contain return type, got: {func.signature}"


def test_doc_comments(file_scanner):
    """Test that doc comments are extracted."""
    structures = file_scanner.scan_file("tests/zig/samples/basic.zig")

    # Find Config struct
    config = next((s for s in structures if s.type == "struct" and s.name == "Config"), None)
    assert config is not None, "Should find Config struct"
    assert config.docstring is not None, "Should have docstring"
    assert "Configuration" in config.docstring, \
        f"Docstring should describe struct, got: {config.docstring}"


def test_modifiers(file_scanner):
    """Test that modifiers are extracted."""
    structures = file_scanner.scan_file("tests/zig/samples/basic.zig")

    # Find public struct
    config = next((s for s in structures if s.type == "struct" and s.name == "Config"), None)
    assert config is not None, "Should find Config struct"
    assert "pub" in config.modifiers, f"Should have pub modifier, got: {config.modifiers}"

    # Find inline function
    fast_add = next((s for s in structures if s.type == "function" and s.name == "fastAdd"), None)
    assert fast_add is not None, "Should find fastAdd"
    assert "inline" in fast_add.modifiers, f"Should have inline modifier, got: {fast_add.modifiers}"
    assert "pub" in fast_add.modifiers, f"Should have pub modifier, got: {fast_add.modifiers}"

    # Find export function
    c_api = next((s for s in structures if s.type == "function" and s.name == "c_api_function"), None)
    assert c_api is not None, "Should find c_api_function"
    assert "export" in c_api.modifiers, f"Should have export modifier, got: {c_api.modifiers}"


def test_tests(file_scanner):
    """Test that test declarations are extracted."""
    structures = file_scanner.scan_file("tests/zig/samples/basic.zig")

    # Find test declarations
    tests = [s for s in structures if s.type == "test"]
    assert len(tests) >= 2, f"Should find at least 2 tests, found {len(tests)}"
    assert any(t.name == "basic test" for t in tests), "Should find 'basic test'"
    assert any(t.name == "addition works" for t in tests), "Should find 'addition works'"


def test_edge_cases(file_scanner):
    """Test edge cases like generics, complex unions, extern structs."""
    structures = file_scanner.scan_file("tests/zig/samples/edge_cases.zig")

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    # Test generic function
    generic_list = next((s for s in structures if s.type == "function" and s.name == "GenericList"), None)
    assert generic_list is not None, "Should find GenericList function"

    # Test complex union
    parse_result = next((s for s in structures if s.type == "union" and s.name == "ParseResult"), None)
    assert parse_result is not None, "Should find ParseResult union"

    # Test extern struct
    c_struct = next((s for s in structures if s.type == "struct" and s.name == "CStruct"), None)
    assert c_struct is not None, "Should find CStruct"

    # Test packed struct
    packed = next((s for s in structures if s.type == "struct" and s.name == "PackedHeader"), None)
    assert packed is not None, "Should find PackedHeader"


def test_broken_file(file_scanner):
    """Test that broken files still parse what they can."""
    structures = file_scanner.scan_file("tests/zig/samples/broken.zig")

    # Should still find some structures
    assert structures is not None, "Should return structures even for broken file"

    # Tree-sitter should still find the valid struct at the end
    assert any("AnotherStruct" in s.name for s in structures), \
        f"Should find AnotherStruct, got: {[s.name for s in structures]}"


def test_complexity(file_scanner):
    """Test that complexity is calculated."""
    structures = file_scanner.scan_file("tests/zig/samples/basic.zig")

    # Find main function
    main_func = next((s for s in structures if s.type == "function" and s.name == "main"), None)
    assert main_func is not None, "Should find main"
    assert main_func.complexity is not None, "Should have complexity"
    assert "lines" in main_func.complexity, "Should have lines count"


def test_enum_values(file_scanner):
    """Test that enum is correctly identified."""
    structures = file_scanner.scan_file("tests/zig/samples/basic.zig")

    # Find Status enum
    status = next((s for s in structures if s.type == "enum" and s.name == "Status"), None)
    assert status is not None, "Should find Status enum"
    assert "pub" in status.modifiers, f"Should have pub modifier, got: {status.modifiers}"


def test_union(file_scanner):
    """Test that union is correctly identified."""
    structures = file_scanner.scan_file("tests/zig/samples/basic.zig")

    # Find Result union
    result = next((s for s in structures if s.type == "union" and s.name == "Result"), None)
    assert result is not None, "Should find Result union"
