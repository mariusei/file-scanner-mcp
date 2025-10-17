"""Tests for C# scanner."""

from pathlib import Path

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic C# file parsing."""
    file_path = Path(__file__).parent / "samples" / "Basic.cs"
    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, "Should parse C# file"
    assert len(structures) > 0, "Should find structures"

    # Verify using directives
    assert any(s.type == "imports" for s in structures), "Should find using directives"

    # Verify namespace
    assert any(s.type == "namespace" and "MyApp.Services" in s.name for s in structures), \
        "Should find namespace declaration"

    # Find namespace to check its children
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Verify interface
    assert any(s.type == "interface" and s.name == "IConfig" for s in namespace.children), \
        "Should find IConfig interface"

    # Verify classes
    assert any(s.type == "class" and s.name == "DatabaseManager" for s in namespace.children), \
        "Should find DatabaseManager class"
    assert any(s.type == "class" and s.name == "UserService" for s in namespace.children), \
        "Should find UserService class"
    assert any(s.type == "class" and s.name == "EmailValidator" for s in namespace.children), \
        "Should find EmailValidator class"

    # Verify struct
    assert any(s.type == "struct" and s.name == "Point" for s in namespace.children), \
        "Should find Point struct"

    # Verify enum
    assert any(s.type == "enum" and s.name == "UserRole" for s in namespace.children), \
        "Should find UserRole enum"


def test_signatures(file_scanner):
    """Test that method signatures are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "Basic.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find DatabaseManager class
    db_manager = next((s for s in namespace.children if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager"

    # Find Query method
    query_method = next((c for c in db_manager.children if c.name == "Query"), None)
    assert query_method is not None, "Should find Query method"
    assert query_method.signature is not None, "Should have signature"
    assert "sql" in query_method.signature, f"Signature should include parameter, got: {query_method.signature}"
    assert "List" in query_method.signature or "Dictionary" in query_method.signature, \
        f"Signature should include return type, got: {query_method.signature}"


def test_properties(file_scanner):
    """Test that properties are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "Basic.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find DatabaseManager class
    db_manager = next((s for s in namespace.children if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager"

    # Find ConnectionString property
    conn_string = next((c for c in db_manager.children if c.type == "property" and c.name == "ConnectionString"), None)
    assert conn_string is not None, "Should find ConnectionString property"
    assert conn_string.signature is not None, "Property should have type signature"
    assert "string" in conn_string.signature, f"Property signature should include type, got: {conn_string.signature}"


def test_interfaces(file_scanner):
    """Test that interface members are extracted."""
    file_path = Path(__file__).parent / "samples" / "Basic.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find IConfig interface
    config = next((s for s in namespace.children if s.type == "interface" and s.name == "IConfig"), None)
    assert config is not None, "Should find IConfig interface"

    # Check for interface properties
    assert len(config.children) > 0, "Interface should have members"
    assert any(c.name == "ApiKey" for c in config.children), "Should find ApiKey property"
    assert any(c.name == "Endpoint" for c in config.children), "Should find Endpoint property"
    assert any(c.name == "Timeout" for c in config.children), "Should find Timeout property"


def test_structs(file_scanner):
    """Test that structs are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "Basic.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find Point struct
    point = next((s for s in namespace.children if s.type == "struct" and s.name == "Point"), None)
    assert point is not None, "Should find Point struct"

    # Check for struct members
    assert len(point.children) > 0, "Struct should have members"
    assert any(c.name == "X" for c in point.children), "Should find X property"
    assert any(c.name == "Y" for c in point.children), "Should find Y property"
    assert any(c.name == "DistanceFromOrigin" for c in point.children), "Should find DistanceFromOrigin method"


def test_xml_docs(file_scanner):
    """Test that XML documentation comments are extracted."""
    file_path = Path(__file__).parent / "samples" / "Basic.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find IConfig interface
    config = next((s for s in namespace.children if s.type == "interface" and s.name == "IConfig"), None)
    assert config is not None, "Should find IConfig interface"
    assert config.docstring is not None, "Should have XML doc comment"
    assert len(config.docstring) > 0, "XML doc should not be empty"

    # Find DatabaseManager class
    db_manager = next((s for s in namespace.children if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager class"
    assert db_manager.docstring is not None, "Should have XML doc comment"
    assert "database" in db_manager.docstring.lower(), \
        f"XML doc should mention database, got: {db_manager.docstring}"


def test_attributes(file_scanner):
    """Test that attributes are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find AnnotationShowcase class
    showcase = next((s for s in namespace.children if s.type == "class" and s.name == "AnnotationShowcase"), None)
    assert showcase is not None, "Should find AnnotationShowcase class"
    assert len(showcase.decorators) > 0, "Class should have attributes"
    assert any("Serializable" in dec for dec in showcase.decorators), \
        f"Should have Serializable attribute, got: {showcase.decorators}"

    # Find OldMethod
    old_method = next((c for c in showcase.children if c.name == "OldMethod"), None)
    assert old_method is not None, "Should find OldMethod"
    assert len(old_method.decorators) > 0, "Method should have attributes"
    assert any("Obsolete" in dec or "Deprecated" in dec for dec in old_method.decorators), \
        f"Should have Obsolete or Deprecated attribute, got: {old_method.decorators}"


def test_modifiers(file_scanner):
    """Test that modifiers are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "Basic.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find EmailValidator class
    validator = next((s for s in namespace.children if s.type == "class" and s.name == "EmailValidator"), None)
    assert validator is not None, "Should find EmailValidator"
    assert "public" in validator.modifiers, "Class should be public"
    assert "static" in validator.modifiers, "Class should be static"

    # Find ValidateEmail method
    validate_method = next((c for c in validator.children if c.name == "ValidateEmail"), None)
    assert validate_method is not None, "Should find ValidateEmail method"
    assert "static" in validate_method.modifiers, "Method should be static"
    assert "public" in validate_method.modifiers, "Method should be public"


def test_generics(file_scanner):
    """Test that generic type parameters are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find GenericContainer class
    generic = next((s for s in namespace.children if s.type == "class" and s.name == "GenericContainer"), None)
    assert generic is not None, "Should find GenericContainer"
    assert generic.signature is not None, "Should have signature with type parameter"
    assert "<T>" in generic.signature, f"Should have generic type parameter, got: {generic.signature}"

    # Find KeyValueStore class
    kvstore = next((s for s in namespace.children if s.type == "class" and s.name == "KeyValueStore"), None)
    assert kvstore is not None, "Should find KeyValueStore"
    assert kvstore.signature is not None, "Should have signature"
    assert "TKey" in kvstore.signature or "TValue" in kvstore.signature, \
        f"Should have generic type parameters, got: {kvstore.signature}"


def test_async_methods(file_scanner):
    """Test that async methods are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find AsyncExample class
    async_example = next((s for s in namespace.children if s.type == "class" and s.name == "AsyncExample"), None)
    assert async_example is not None, "Should find AsyncExample"

    # Find async method
    fetch_data = next((c for c in async_example.children if c.name == "FetchDataAsync"), None)
    assert fetch_data is not None, "Should find FetchDataAsync method"
    assert "async" in fetch_data.modifiers, "Method should be async"


def test_abstract_classes(file_scanner):
    """Test that abstract classes and methods are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find AbstractService class
    abstract_service = next((s for s in namespace.children if s.type == "class" and s.name == "AbstractService"), None)
    assert abstract_service is not None, "Should find AbstractService"
    assert "abstract" in abstract_service.modifiers, "Class should be abstract"

    # Find abstract method
    execute = next((c for c in abstract_service.children if c.name == "Execute"), None)
    assert execute is not None, "Should find Execute method"
    assert "abstract" in execute.modifiers, "Method should be abstract"


def test_nested_classes(file_scanner):
    """Test that nested classes are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find OuterClass
    outer = next((s for s in namespace.children if s.type == "class" and s.name == "OuterClass"), None)
    assert outer is not None, "Should find OuterClass"
    assert len(outer.children) > 0, "Should have nested structures"

    # Find InnerClass
    inner = next((c for c in outer.children if c.type == "class" and c.name == "InnerClass"), None)
    assert inner is not None, "Should find InnerClass"

    # Find StaticNestedClass
    static_nested = next((c for c in outer.children if c.type == "class" and c.name == "StaticNestedClass"), None)
    assert static_nested is not None, "Should find StaticNestedClass"
    assert "static" in static_nested.modifiers, "StaticNestedClass should be static"


def test_enum_with_base_type(file_scanner):
    """Test that enums with base types are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find Status enum
    status = next((s for s in namespace.children if s.type == "enum" and s.name == "Status"), None)
    assert status is not None, "Should find Status enum"
    assert status.signature is not None, "Enum should have base type signature"
    assert "byte" in status.signature, f"Enum signature should include base type, got: {status.signature}"


def test_virtual_override(file_scanner):
    """Test that virtual and override modifiers are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find AbstractService class
    abstract_service = next((s for s in namespace.children if s.type == "class" and s.name == "AbstractService"), None)
    assert abstract_service is not None, "Should find AbstractService"

    # Find virtual method
    initialize = next((c for c in abstract_service.children if c.name == "Initialize"), None)
    assert initialize is not None, "Should find Initialize method"
    assert "virtual" in initialize.modifiers, "Method should be virtual"

    # Find ConcreteService class
    concrete = next((s for s in namespace.children if s.type == "class" and s.name == "ConcreteService"), None)
    assert concrete is not None, "Should find ConcreteService"

    # Find override method
    execute_override = next((c for c in concrete.children if c.name == "Execute"), None)
    assert execute_override is not None, "Should find Execute method"
    assert "override" in execute_override.modifiers, "Method should be override"


def test_sealed_class(file_scanner):
    """Test that sealed classes are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find SealedService class
    sealed_service = next((s for s in namespace.children if s.type == "class" and s.name == "SealedService"), None)
    assert sealed_service is not None, "Should find SealedService"
    assert "sealed" in sealed_service.modifiers, "Class should be sealed"


def test_readonly_struct(file_scanner):
    """Test that readonly structs are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find Vector3 struct
    vector3 = next((s for s in namespace.children if s.type == "struct" and s.name == "Vector3"), None)
    assert vector3 is not None, "Should find Vector3 struct"
    assert "readonly" in vector3.modifiers, "Struct should be readonly"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)
    file_path = Path(__file__).parent / "samples" / "Broken.cs"

    # Should not crash
    structures = scanner.scan_file(str(file_path))

    assert structures is not None, "Should return structures even for broken code"

    # Should show parse errors or valid structures
    has_error = any(s.type in ("parse-error", "error") for s in structures)
    has_valid = any(s.type in ("class", "interface", "method", "struct", "enum", "namespace") for s in structures)

    assert has_error or has_valid, "Should have either errors or valid structures"


def test_constructors(file_scanner):
    """Test that constructors are extracted."""
    file_path = Path(__file__).parent / "samples" / "Basic.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find DatabaseManager class
    db_manager = next((s for s in namespace.children if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager"

    # Find constructor
    constructor = next((c for c in db_manager.children if c.type == "constructor"), None)
    assert constructor is not None, "Should find constructor"
    assert constructor.name == "DatabaseManager", "Constructor should have class name"
    assert constructor.signature is not None, "Constructor should have signature"
    assert "connectionString" in constructor.signature, \
        f"Constructor signature should include parameter, got: {constructor.signature}"


def test_complex_method_signatures(file_scanner):
    """Test that complex method signatures are extracted."""
    file_path = Path(__file__).parent / "samples" / "EdgeCases.cs"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should have namespace"

    # Find GenericContainer class
    generic = next((s for s in namespace.children if s.type == "class" and s.name == "GenericContainer"), None)
    assert generic is not None, "Should find GenericContainer"

    # Find ProcessAsync method with complex signature
    process = next((c for c in generic.children if c.name == "ProcessAsync"), None)
    assert process is not None, "Should find ProcessAsync method"
    assert process.signature is not None, "Should have signature"

    # Check that complex types are preserved
    sig = process.signature
    assert "Task" in sig or "IEnumerable" in sig or "Func" in sig or "Predicate" in sig, \
        f"Should preserve complex types in: {sig}"
