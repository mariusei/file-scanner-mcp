"""Tests for PHP scanner."""

from pathlib import Path

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic PHP file parsing."""
    file_path = Path(__file__).parent / "samples" / "basic.php"
    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, "Should parse PHP file"
    assert len(structures) > 0, "Should find structures"

    # Verify namespace declaration
    assert any(s.type == "namespace" and "App\\Database" in s.name for s in structures), \
        "Should find namespace declaration"

    # Verify use statements
    assert any(s.type == "imports" for s in structures), "Should find use statements"

    # Verify interface
    assert any(s.type == "interface" and s.name == "DatabaseConfig" for s in structures), \
        "Should find DatabaseConfig interface"

    # Verify classes
    assert any(s.type == "class" and s.name == "DatabaseManager" for s in structures), \
        "Should find DatabaseManager class"
    assert any(s.type == "class" and s.name == "UserService" for s in structures), \
        "Should find UserService class"

    # Verify trait
    assert any(s.type == "trait" and s.name == "Loggable" for s in structures), \
        "Should find Loggable trait"

    # Verify standalone functions
    assert any(s.type == "function" and s.name == "validateEmail" for s in structures), \
        "Should find validateEmail function"
    assert any(s.type == "function" and s.name == "formatName" for s in structures), \
        "Should find formatName function"


def test_signatures(file_scanner):
    """Test that method signatures are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "basic.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find DatabaseManager class
    db_manager = next((s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager"

    # Find query method
    query_method = next((c for c in db_manager.children if c.name == "query"), None)
    assert query_method is not None, "Should find query method"
    assert query_method.signature is not None, "Should have signature"
    assert "sql" in query_method.signature, f"Signature should include parameter, got: {query_method.signature}"
    assert "array" in query_method.signature.lower(), f"Signature should include return type, got: {query_method.signature}"


def test_phpdoc_extraction(file_scanner):
    """Test that PHPDoc comments are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find DatabaseConfig interface
    config = next((s for s in structures if s.type == "interface" and s.name == "DatabaseConfig"), None)
    assert config is not None, "Should find DatabaseConfig interface"
    assert config.docstring is not None, "Should have PHPDoc comment"
    assert len(config.docstring) > 0, "PHPDoc should not be empty"

    # Find DatabaseManager class
    db_manager = next((s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager class"
    assert db_manager.docstring is not None, "Should have PHPDoc comment"
    assert "database" in db_manager.docstring.lower(), \
        f"PHPDoc should mention database, got: {db_manager.docstring}"


def test_traits(file_scanner):
    """Test that traits and their methods are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find Loggable trait
    loggable = next((s for s in structures if s.type == "trait" and s.name == "Loggable"), None)
    assert loggable is not None, "Should find Loggable trait"

    # Check for trait methods
    assert len(loggable.children) > 0, "Trait should have methods"
    assert any(c.name == "log" for c in loggable.children), "Should find log method"
    assert any(c.name == "getLogs" for c in loggable.children), "Should find getLogs method"


def test_interfaces(file_scanner):
    """Test that interface methods are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find DatabaseConfig interface
    config = next((s for s in structures if s.type == "interface" and s.name == "DatabaseConfig"), None)
    assert config is not None, "Should find DatabaseConfig interface"

    # Check for interface methods
    assert len(config.children) > 0, "Interface should have method declarations"
    assert any(c.name == "getHost" for c in config.children), "Should find getHost method"
    assert any(c.name == "getPort" for c in config.children), "Should find getPort method"
    assert any(c.name == "getDatabase" for c in config.children), "Should find getDatabase method"


def test_modifiers(file_scanner):
    """Test that modifiers are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find AbstractService class
    abstract_service = next((s for s in structures if s.type == "class" and s.name == "AbstractService"), None)
    assert abstract_service is not None, "Should find AbstractService"
    assert "abstract" in abstract_service.modifiers, "Class should be abstract"

    # Find ImmutableConfig class
    immutable = next((s for s in structures if s.type == "class" and s.name == "ImmutableConfig"), None)
    assert immutable is not None, "Should find ImmutableConfig"
    assert "final" in immutable.modifiers, "Class should be final"

    # Find StaticExample class and its static method
    static_example = next((s for s in structures if s.type == "class" and s.name == "StaticExample"), None)
    assert static_example is not None, "Should find StaticExample"

    increment_method = next((c for c in static_example.children if c.name == "increment"), None)
    assert increment_method is not None, "Should find increment method"
    assert "static" in increment_method.modifiers, "Method should be static"


def test_attributes(file_scanner):
    """Test that PHP 8 attributes are extracted."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find AttributeShowcase class
    showcase = next((s for s in structures if s.type == "class" and s.name == "AttributeShowcase"), None)
    assert showcase is not None, "Should find AttributeShowcase class"
    assert len(showcase.decorators) > 0, "Class should have attributes"

    # Find listUsers method
    list_users = next((c for c in showcase.children if c.name == "listUsers"), None)
    assert list_users is not None, "Should find listUsers method"
    assert len(list_users.decorators) > 0, "Method should have attributes"


def test_enums(file_scanner):
    """Test that enums are extracted."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find UserRole enum
    user_role = next((s for s in structures if s.type == "enum" and s.name == "UserRole"), None)
    assert user_role is not None, "Should find UserRole enum"
    assert user_role.signature is not None, "Enum should have type signature"
    assert "string" in user_role.signature, f"Enum should be backed by string, got: {user_role.signature}"

    # Find HttpStatus enum
    http_status = next((s for s in structures if s.type == "enum" and s.name == "HttpStatus"), None)
    assert http_status is not None, "Should find HttpStatus enum"
    assert http_status.signature is not None, "Enum should have type signature"
    assert "int" in http_status.signature, f"Enum should be backed by int, got: {http_status.signature}"


def test_abstract_methods(file_scanner):
    """Test that abstract classes and methods are extracted."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find AbstractService class
    abstract_service = next((s for s in structures if s.type == "class" and s.name == "AbstractService"), None)
    assert abstract_service is not None, "Should find AbstractService"
    assert "abstract" in abstract_service.modifiers, "Class should be abstract"

    # Find abstract method
    execute = next((c for c in abstract_service.children if c.name == "execute"), None)
    assert execute is not None, "Should find execute method"
    assert "abstract" in execute.modifiers, "Method should be abstract"


def test_type_hints(file_scanner):
    """Test that complex type hints are preserved."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find TypeHintExample class
    type_hints = next((s for s in structures if s.type == "class" and s.name == "TypeHintExample"), None)
    assert type_hints is not None, "Should find TypeHintExample"

    # Find processValue method with union types
    process_value = next((c for c in type_hints.children if c.name == "processValue"), None)
    assert process_value is not None, "Should find processValue method"
    assert process_value.signature is not None, "Should have signature"


def test_standalone_functions(file_scanner):
    """Test that standalone functions are extracted with signatures."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find processData function
    process_data = next((s for s in structures if s.type == "function" and s.name == "processData"), None)
    assert process_data is not None, "Should find processData function"
    assert process_data.signature is not None, "Should have signature"
    assert "input" in process_data.signature or "mapper" in process_data.signature, \
        f"Signature should include parameters, got: {process_data.signature}"

    # Find sum function with variadic parameters
    sum_func = next((s for s in structures if s.type == "function" and s.name == "sum"), None)
    assert sum_func is not None, "Should find sum function"
    assert sum_func.signature is not None, "Should have signature"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)
    file_path = Path(__file__).parent / "samples" / "broken.php"

    # Should not crash
    structures = scanner.scan_file(str(file_path))

    assert structures is not None, "Should return structures even for broken code"

    # Should show parse errors or valid structures
    has_error = any(s.type in ("parse-error", "error") for s in structures)
    has_valid = any(s.type in ("class", "interface", "trait", "function") for s in structures)

    assert has_error or has_valid, "Should have either errors or valid structures"


def test_namespace_extraction(file_scanner):
    """Test that namespaces are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "basic.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find namespace
    namespace = next((s for s in structures if s.type == "namespace"), None)
    assert namespace is not None, "Should find namespace declaration"
    assert "App\\Database" in namespace.name, f"Should have correct namespace, got: {namespace.name}"


def test_visibility_modifiers(file_scanner):
    """Test that visibility modifiers are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find DatabaseManager class
    db_manager = next((s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager"

    # Find public method
    connect = next((c for c in db_manager.children if c.name == "connect"), None)
    assert connect is not None, "Should find connect method"
    assert "public" in connect.modifiers, "Method should be public"


def test_return_types(file_scanner):
    """Test that return types are extracted in signatures."""
    file_path = Path(__file__).parent / "samples" / "basic.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find validateEmail function
    validate = next((s for s in structures if s.type == "function" and s.name == "validateEmail"), None)
    assert validate is not None, "Should find validateEmail function"
    assert validate.signature is not None, "Should have signature"
    assert "bool" in validate.signature, f"Signature should include return type, got: {validate.signature}"


def test_multiple_use_statements(file_scanner):
    """Test that multiple use statements are grouped."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.php"
    structures = file_scanner.scan_file(str(file_path))

    # Should group use statements
    imports = [s for s in structures if s.type == "imports"]
    assert len(imports) > 0, "Should find grouped use statements"


def test_repository_interface(file_scanner):
    """Test that repository interface methods are extracted."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.php"
    structures = file_scanner.scan_file(str(file_path))

    # Find Repository interface
    repository = next((s for s in structures if s.type == "interface" and s.name == "Repository"), None)
    assert repository is not None, "Should find Repository interface"
    assert len(repository.children) > 0, "Interface should have methods"

    # Check for specific methods
    find = next((c for c in repository.children if c.name == "find"), None)
    assert find is not None, "Should find 'find' method"
    assert find.signature is not None, "Method should have signature"
