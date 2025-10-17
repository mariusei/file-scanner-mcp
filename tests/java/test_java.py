"""Tests for Java scanner."""

from pathlib import Path

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic Java file parsing."""
    file_path = Path(__file__).parent / "samples" / "Basic.java"
    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, "Should parse Java file"
    assert len(structures) > 0, "Should find structures"

    # Verify package declaration
    assert any(s.type == "package" and "com.example.demo" in s.name for s in structures), \
        "Should find package declaration"

    # Verify import statements
    assert any(s.type == "imports" for s in structures), "Should find import statements"

    # Verify interface
    assert any(s.type == "interface" and s.name == "Config" for s in structures), \
        "Should find Config interface"

    # Verify classes
    assert any(s.type == "class" and s.name == "DatabaseManager" for s in structures), \
        "Should find DatabaseManager class"
    assert any(s.type == "class" and s.name == "UserService" for s in structures), \
        "Should find UserService class"
    assert any(s.type == "class" and s.name == "EmailValidator" for s in structures), \
        "Should find EmailValidator class"


def test_signatures(file_scanner):
    """Test that method signatures are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "Basic.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find DatabaseManager class
    db_manager = next((s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager"

    # Find query method
    query_method = next((c for c in db_manager.children if c.name == "query"), None)
    assert query_method is not None, "Should find query method"
    assert query_method.signature is not None, "Should have signature"
    assert "sql" in query_method.signature, f"Signature should include parameter, got: {query_method.signature}"
    assert "List" in query_method.signature, f"Signature should include return type, got: {query_method.signature}"


def test_javadoc_extraction(file_scanner):
    """Test that JavaDoc comments are extracted."""
    file_path = Path(__file__).parent / "samples" / "Basic.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find Config interface
    config = next((s for s in structures if s.type == "interface" and s.name == "Config"), None)
    assert config is not None, "Should find Config interface"
    assert config.docstring is not None, "Should have JavaDoc comment"
    assert len(config.docstring) > 0, "JavaDoc should not be empty"

    # Find DatabaseManager class
    db_manager = next((s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager class"
    assert db_manager.docstring is not None, "Should have JavaDoc comment"
    assert "database" in db_manager.docstring.lower(), \
        f"JavaDoc should mention database, got: {db_manager.docstring}"


def test_constructors(file_scanner):
    """Test that constructors are extracted."""
    file_path = Path(__file__).parent / "samples" / "Basic.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find DatabaseManager class
    db_manager = next((s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager"

    # Find constructor
    constructor = next((c for c in db_manager.children if c.type == "constructor"), None)
    assert constructor is not None, "Should find constructor"
    assert constructor.name == "DatabaseManager", "Constructor should have class name"
    assert constructor.signature is not None, "Constructor should have signature"
    assert "connectionString" in constructor.signature, \
        f"Constructor signature should include parameter, got: {constructor.signature}"


def test_interfaces(file_scanner):
    """Test that interface methods are extracted."""
    file_path = Path(__file__).parent / "samples" / "Basic.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find Config interface
    config = next((s for s in structures if s.type == "interface" and s.name == "Config"), None)
    assert config is not None, "Should find Config interface"

    # Check for interface methods
    assert len(config.children) > 0, "Interface should have method declarations"
    assert any(c.name == "getApiKey" for c in config.children), "Should find getApiKey method"
    assert any(c.name == "getEndpoint" for c in config.children), "Should find getEndpoint method"


def test_modifiers(file_scanner):
    """Test that modifiers are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "Basic.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find EmailValidator class
    validator = next((s for s in structures if s.type == "class" and s.name == "EmailValidator"), None)
    assert validator is not None, "Should find EmailValidator"
    assert "public" in validator.modifiers, "Class should be public"

    # Find validateEmail method
    validate_method = next((c for c in validator.children if c.name == "validateEmail"), None)
    assert validate_method is not None, "Should find validateEmail method"
    assert "static" in validate_method.modifiers, "Method should be static"
    assert "public" in validate_method.modifiers, "Method should be public"


def test_annotations(file_scanner):
    """Test that annotations are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find AnnotationShowcase class
    showcase = next((s for s in structures if s.type == "class" and s.name == "AnnotationShowcase"), None)
    assert showcase is not None, "Should find AnnotationShowcase class"

    # Find deprecated method
    old_method = next((c for c in showcase.children if c.name == "oldMethod"), None)
    assert old_method is not None, "Should find oldMethod"
    assert any("@Deprecated" in dec for dec in old_method.decorators), \
        f"Should have @Deprecated annotation, got: {old_method.decorators}"

    # Find override method
    to_string = next((c for c in showcase.children if c.name == "toString"), None)
    assert to_string is not None, "Should find toString"
    assert any("@Override" in dec for dec in to_string.decorators), \
        f"Should have @Override annotation, got: {to_string.decorators}"


def test_generics(file_scanner):
    """Test that generic type parameters are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find GenericContainer class
    generic = next((s for s in structures if s.type == "class" and s.name == "GenericContainer"), None)
    assert generic is not None, "Should find GenericContainer"
    assert generic.signature is not None, "Should have signature with type parameter"
    assert "<T>" in generic.signature, f"Should have generic type parameter, got: {generic.signature}"

    # Find KeyValueStore class
    kvstore = next((s for s in structures if s.type == "class" and s.name == "KeyValueStore"), None)
    assert kvstore is not None, "Should find KeyValueStore"
    assert kvstore.signature is not None, "Should have signature"
    assert "<K, V>" in kvstore.signature or "K" in kvstore.signature, \
        f"Should have generic type parameters, got: {kvstore.signature}"


def test_inner_classes(file_scanner):
    """Test that inner classes are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find OuterClass
    outer = next((s for s in structures if s.type == "class" and s.name == "OuterClass"), None)
    assert outer is not None, "Should find OuterClass"
    assert len(outer.children) > 0, "Should have nested structures"

    # Find InnerClass
    inner = next((c for c in outer.children if c.type == "class" and c.name == "InnerClass"), None)
    assert inner is not None, "Should find InnerClass"

    # Find StaticNestedClass
    static_nested = next((c for c in outer.children if c.type == "class" and c.name == "StaticNestedClass"), None)
    assert static_nested is not None, "Should find StaticNestedClass"
    assert "static" in static_nested.modifiers, "StaticNestedClass should be static"


def test_enums(file_scanner):
    """Test that enums are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find UserRole enum
    user_role = next((s for s in structures if s.type == "enum" and s.name == "UserRole"), None)
    assert user_role is not None, "Should find UserRole enum"
    assert "public" in user_role.modifiers, "Enum should be public"


def test_abstract_classes(file_scanner):
    """Test that abstract classes and methods are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find AbstractService class
    abstract_service = next((s for s in structures if s.type == "class" and s.name == "AbstractService"), None)
    assert abstract_service is not None, "Should find AbstractService"
    assert "abstract" in abstract_service.modifiers, "Class should be abstract"

    # Find abstract method
    execute = next((c for c in abstract_service.children if c.name == "execute"), None)
    assert execute is not None, "Should find execute method"
    assert "abstract" in execute.modifiers, "Method should be abstract"


def test_synchronized_methods(file_scanner):
    """Test that synchronized modifier is extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find SynchronizedService class
    sync_service = next((s for s in structures if s.type == "class" and s.name == "SynchronizedService"), None)
    assert sync_service is not None, "Should find SynchronizedService"

    # Find synchronized method
    increment = next((c for c in sync_service.children if c.name == "increment"), None)
    assert increment is not None, "Should find increment method"
    assert "synchronized" in increment.modifiers, "Method should be synchronized"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)
    file_path = Path(__file__).parent / "samples" / "Broken.java"

    # Should not crash
    structures = scanner.scan_file(str(file_path))

    assert structures is not None, "Should return structures even for broken code"

    # Should show parse errors or valid structures
    has_error = any(s.type in ("parse-error", "error") for s in structures)
    has_valid = any(s.type in ("class", "interface", "method") for s in structures)

    assert has_error or has_valid, "Should have either errors or valid structures"


def test_complex_signatures(file_scanner):
    """Test that complex method signatures are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find GenericContainer class
    generic = next((s for s in structures if s.type == "class" and s.name == "GenericContainer"), None)
    assert generic is not None, "Should find GenericContainer"

    # Find process method with complex signature
    process = next((c for c in generic.children if c.name == "process"), None)
    assert process is not None, "Should find process method"
    assert process.signature is not None, "Should have signature"

    # Check that complex types are preserved
    sig = process.signature
    assert "Map" in sig or "List" in sig or "Function" in sig, \
        f"Should preserve complex types in: {sig}"


def test_method_parameters(file_scanner):
    """Test that method parameters are extracted in signatures."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.java"
    structures = file_scanner.scan_file(str(file_path))

    # Find LambdaExample class
    lambda_example = next((s for s in structures if s.type == "class" and s.name == "LambdaExample"), None)
    assert lambda_example is not None, "Should find LambdaExample"

    # Find transformData method
    transform = next((c for c in lambda_example.children if c.name == "transformData"), None)
    assert transform is not None, "Should find transformData method"
    assert transform.signature is not None, "Should have signature"

    # Check that parameters are in signature
    sig = transform.signature
    assert "input" in sig or "mapper" in sig or "filter" in sig, \
        f"Should include parameters in signature: {sig}"
