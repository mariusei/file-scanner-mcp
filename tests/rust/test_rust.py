"""Tests for Rust scanner."""

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic Rust file parsing."""
    structures = file_scanner.scan_file("tests/rust/samples/basic.rs")
    assert structures is not None, "Should parse Rust file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected structures
    assert any(s.type == "struct" and s.name == "User" for s in structures)
    assert any(s.type == "struct" and s.name == "DatabaseManager" for s in structures)
    assert any(s.type == "trait" and s.name == "Validate" for s in structures)
    assert any(s.type == "function" and s.name == "validate_email" for s in structures)


def test_impl_blocks(file_scanner):
    """Test that impl blocks are extracted correctly."""
    structures = file_scanner.scan_file("tests/rust/samples/basic.rs")

    # Find impl block for DatabaseManager
    impl_block = next((s for s in structures if s.type == "impl" and "DatabaseManager" in s.name), None)
    assert impl_block is not None, "Should find DatabaseManager impl block"
    assert len(impl_block.children) > 0, "Impl block should have methods"

    # Check that methods are extracted
    assert any(c.type == "method" and c.name == "new" for c in impl_block.children)
    assert any(c.type == "method" and c.name == "connect" for c in impl_block.children)


def test_trait_impl(file_scanner):
    """Test trait implementation blocks."""
    structures = file_scanner.scan_file("tests/rust/samples/basic.rs")

    # Find trait impl (Validate for User)
    trait_impl = next((s for s in structures if s.type == "impl" and "Validate" in s.name and "User" in s.name), None)
    assert trait_impl is not None, "Should find Validate trait impl for User"
    assert len(trait_impl.children) > 0, "Trait impl should have methods"


def test_signatures(file_scanner):
    """Test that signatures are extracted correctly."""
    structures = file_scanner.scan_file("tests/rust/samples/basic.rs")

    # Find validate_email function
    func = next((s for s in structures if s.type == "function" and s.name == "validate_email"), None)
    assert func is not None, "Should find validate_email"
    assert func.signature is not None, "Should have signature"
    assert "email: &str" in func.signature, f"Signature should contain parameter, got: {func.signature}"
    assert "-> bool" in func.signature, f"Signature should contain return type, got: {func.signature}"


def test_doc_comments(file_scanner):
    """Test that doc comments are extracted."""
    structures = file_scanner.scan_file("tests/rust/samples/basic.rs")

    # Find User struct
    user_struct = next((s for s in structures if s.type == "struct" and s.name == "User"), None)
    assert user_struct is not None, "Should find User struct"
    assert user_struct.docstring is not None, "Should have docstring"
    assert "User account" in user_struct.docstring or "basic information" in user_struct.docstring, \
        f"Docstring should describe struct, got: {user_struct.docstring}"


def test_attributes(file_scanner):
    """Test that attributes are extracted."""
    structures = file_scanner.scan_file("tests/rust/samples/basic.rs")

    # Find User struct with derive attribute
    user_struct = next((s for s in structures if s.type == "struct" and s.name == "User"), None)
    assert user_struct is not None, "Should find User struct"
    assert len(user_struct.decorators) > 0, "Should have attributes"
    assert any("#[derive" in dec for dec in user_struct.decorators), \
        f"Should have derive attribute, got: {user_struct.decorators}"


def test_modifiers(file_scanner):
    """Test that modifiers are extracted."""
    structures = file_scanner.scan_file("tests/rust/samples/basic.rs")

    # Find public struct
    user_struct = next((s for s in structures if s.type == "struct" and s.name == "User"), None)
    assert user_struct is not None, "Should find User struct"
    assert "pub" in user_struct.modifiers, f"Should have pub modifier, got: {user_struct.modifiers}"


def test_edge_cases(file_scanner):
    """Test edge cases like generics, lifetimes, async, unsafe."""
    structures = file_scanner.scan_file("tests/rust/samples/edge_cases.rs")

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    # Test generics
    container = next((s for s in structures if s.type == "struct" and s.name == "Container"), None)
    assert container is not None, "Should find Container struct"
    assert container.signature is not None, "Should have generic signature"
    assert "T" in container.signature, f"Should have type parameter, got: {container.signature}"

    # Test async function
    async_fetch = next((s for s in structures if s.type == "function" and s.name == "async_fetch"), None)
    assert async_fetch is not None, "Should find async_fetch function"
    assert "async" in async_fetch.modifiers, f"Should have async modifier, got: {async_fetch.modifiers}"

    # Test unsafe function
    unsafe_func = next((s for s in structures if s.type == "function" and s.name == "raw_pointer_access"), None)
    assert unsafe_func is not None, "Should find raw_pointer_access function"
    assert "unsafe" in unsafe_func.modifiers, f"Should have unsafe modifier, got: {unsafe_func.modifiers}"

    # Test const function
    const_func = next((s for s in structures if s.type == "function" and s.name == "const_multiply"), None)
    assert const_func is not None, "Should find const_multiply function"
    assert "const" in const_func.modifiers, f"Should have const modifier, got: {const_func.modifiers}"


def test_complex_generics(file_scanner):
    """Test complex generic signatures."""
    structures = file_scanner.scan_file("tests/rust/samples/edge_cases.rs")

    # Find ComplexStruct with multiple lifetimes and type parameters
    complex = next((s for s in structures if s.type == "struct" and s.name == "ComplexStruct"), None)
    assert complex is not None, "Should find ComplexStruct"
    assert complex.signature is not None, "Should have signature"
    # Check for multiple parameters (lifetimes and types)
    sig = complex.signature
    assert "'" in sig or "T" in sig or "U" in sig, \
        f"Should have lifetime or type parameters, got: {sig}"


def test_multiple_attributes(file_scanner):
    """Test extraction of multiple attributes."""
    structures = file_scanner.scan_file("tests/rust/samples/edge_cases.rs")

    # Find struct with multiple attributes
    attr_showcase = next((s for s in structures if s.type == "struct" and s.name == "AttributeShowcase"), None)
    assert attr_showcase is not None, "Should find AttributeShowcase"
    assert len(attr_showcase.decorators) > 1, \
        f"Should have multiple attributes, got: {attr_showcase.decorators}"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)

    # Should not crash
    structures = scanner.scan_file("tests/rust/samples/broken.rs")

    assert structures is not None, "Should return structures even for broken code"

    # Should show parse errors or valid structures
    has_error = any(s.type in ("parse-error", "error") for s in structures)
    has_valid = any(s.type in ("struct", "function", "enum", "trait") for s in structures)

    assert has_error or has_valid, "Should have either errors or valid structures"


def test_trait_definition(file_scanner):
    """Test trait definition extraction."""
    structures = file_scanner.scan_file("tests/rust/samples/basic.rs")

    # Find Validate trait
    trait = next((s for s in structures if s.type == "trait" and s.name == "Validate"), None)
    assert trait is not None, "Should find Validate trait"
    assert trait.docstring is not None, "Trait should have docstring"


def test_enums(file_scanner):
    """Test enum extraction."""
    structures = file_scanner.scan_file("tests/rust/samples/edge_cases.rs")

    # Find enum
    result_enum = next((s for s in structures if s.type == "enum" and s.name == "Result"), None)
    assert result_enum is not None, "Should find Result enum"

    # Find message enum with complex variants
    message_enum = next((s for s in structures if s.type == "enum" and s.name == "Message"), None)
    assert message_enum is not None, "Should find Message enum"


def test_imports(file_scanner):
    """Test that use statements are grouped."""
    structures = file_scanner.scan_file("tests/rust/samples/basic.rs")

    # Should have imports group
    imports = next((s for s in structures if s.type == "imports"), None)
    assert imports is not None, "Should group use statements"
