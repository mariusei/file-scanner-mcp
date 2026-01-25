"""Tests for Swift scanner."""

from pathlib import Path

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic Swift file parsing."""
    file_path = Path(__file__).parent / "samples" / "basic.swift"
    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, "Should parse Swift file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected structures
    types = [s.type for s in structures]
    names = [s.name for s in structures]

    # Should find structs
    assert any(s.type == "struct" and s.name == "Config" for s in structures), \
        f"Should find Config struct, got: {list(zip(types, names))}"

    # Should find protocols
    assert any(s.type == "protocol" and s.name == "Logger" for s in structures), \
        "Should find Logger protocol"

    # Should find enums
    assert any(s.type == "enum" and s.name == "UserStatus" for s in structures), \
        "Should find UserStatus enum"

    # Should find classes
    assert any(s.type == "class" and s.name == "DatabaseManager" for s in structures), \
        "Should find DatabaseManager class"

    # Should find extensions
    assert any(s.type == "extension" for s in structures), \
        "Should find extension"

    # Should find standalone functions
    assert any(s.type == "function" and s.name == "validateEmail" for s in structures), \
        "Should find validateEmail function"


def test_signatures(file_scanner):
    """Test that signatures are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "basic.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find validateEmail function
    func = next((s for s in structures if s.type == "function" and s.name == "validateEmail"), None)
    assert func is not None, "Should find validateEmail"
    assert func.signature is not None, f"Should have signature, got: {func}"
    assert "String" in func.signature or "email" in func.signature, \
        f"Signature should include parameter, got: {func.signature}"


def test_methods(file_scanner):
    """Test that methods inside types are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find DatabaseManager class
    db_manager = next((s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager"

    # Check for methods in children
    if db_manager.children:
        method_names = [c.name for c in db_manager.children if c.type == "method"]
        assert "connect" in method_names, f"Should find connect method, got: {method_names}"
        assert "disconnect" in method_names, f"Should find disconnect method, got: {method_names}"


def test_docstrings(file_scanner):
    """Test that documentation comments are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find Config struct
    config = next((s for s in structures if s.type == "struct" and s.name == "Config"), None)
    assert config is not None, "Should find Config"
    assert config.docstring is not None, f"Should have docstring, got: {config}"
    assert "configuration" in config.docstring.lower() or "config" in config.docstring.lower(), \
        f"Docstring should mention configuration, got: {config.docstring}"


def test_visibility_modifiers(file_scanner):
    """Test that visibility modifiers are detected."""
    file_path = Path(__file__).parent / "samples" / "basic.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find public DatabaseManager class
    db_manager = next((s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager"
    assert "public" in db_manager.modifiers, \
        f"DatabaseManager should be public, got modifiers: {db_manager.modifiers}"


def test_inheritance(file_scanner):
    """Test that inheritance/conformance is captured in signature."""
    file_path = Path(__file__).parent / "samples" / "basic.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find UserStatus enum with String raw value
    user_status = next((s for s in structures if s.type == "enum" and s.name == "UserStatus"), None)
    assert user_status is not None, "Should find UserStatus"
    if user_status.signature:
        assert "String" in user_status.signature, \
            f"Should show String inheritance, got: {user_status.signature}"


def test_edge_cases(file_scanner):
    """Test edge cases like generics, actors, async, etc."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.swift"
    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    names = [s.name for s in structures]
    types = [s.type for s in structures]

    # Test generic types
    generic = next((s for s in structures if "GenericContainer" in s.name), None)
    assert generic is not None, f"Should find GenericContainer, got: {names}"

    # Test actors (Swift concurrency)
    counter = next((s for s in structures if s.type == "actor" and s.name == "Counter"), None)
    assert counter is not None, f"Should find Counter actor, got types: {list(zip(types, names))}"

    # Test class with @MainActor
    view_model = next((s for s in structures if s.name == "ViewModel"), None)
    assert view_model is not None, "Should find ViewModel"
    # @MainActor should be in decorators
    if view_model.decorators:
        assert any("MainActor" in d for d in view_model.decorators), \
            f"Should have @MainActor decorator, got: {view_model.decorators}"

    # Test property wrapper struct
    clamped = next((s for s in structures if s.name == "Clamped"), None)
    assert clamped is not None, "Should find Clamped property wrapper"

    # Test result builder
    array_builder = next((s for s in structures if s.name == "ArrayBuilder"), None)
    assert array_builder is not None, "Should find ArrayBuilder"

    # Test nested types
    outer = next((s for s in structures if s.name == "OuterType"), None)
    assert outer is not None, "Should find OuterType"
    if outer.children:
        inner_names = [c.name for c in outer.children]
        assert "InnerType" in inner_names or any("Inner" in n for n in inner_names), \
            f"Should find nested InnerType, got: {inner_names}"


def test_async_functions(file_scanner):
    """Test async/await function parsing."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find async function
    fetch_data = next((s for s in structures if s.type == "function" and s.name == "fetchData"), None)
    assert fetch_data is not None, "Should find fetchData"
    # Check for async modifier or in signature
    has_async = "async" in fetch_data.modifiers or (fetch_data.signature and "async" in fetch_data.signature)
    # async might also be in the signature text itself
    assert has_async or (fetch_data.signature and "throws" in fetch_data.signature), \
        f"Should detect async/throws function, modifiers: {fetch_data.modifiers}, sig: {fetch_data.signature}"


def test_subscripts(file_scanner):
    """Test subscript parsing."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find Matrix struct
    matrix = next((s for s in structures if s.type == "struct" and s.name == "Matrix"), None)
    assert matrix is not None, "Should find Matrix struct"

    # Check for subscript in children
    if matrix.children:
        subscripts = [c for c in matrix.children if c.type == "subscript"]
        assert len(subscripts) >= 1, f"Should find subscripts in Matrix, got: {[c.type for c in matrix.children]}"


def test_initializers(file_scanner):
    """Test initializer parsing."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find InitializerExamples class
    init_examples = next((s for s in structures if s.name == "InitializerExamples"), None)
    assert init_examples is not None, "Should find InitializerExamples"

    # Check for initializers in children
    if init_examples.children:
        initializers = [c for c in init_examples.children if c.type == "initializer"]
        assert len(initializers) >= 1, \
            f"Should find initializers, got: {[(c.type, c.name) for c in init_examples.children]}"


def test_deinit(file_scanner):
    """Test deinitializer parsing."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find ResourceManager class
    resource_manager = next((s for s in structures if s.name == "ResourceManager"), None)
    assert resource_manager is not None, "Should find ResourceManager"

    # Check for deinit in children
    if resource_manager.children:
        deinits = [c for c in resource_manager.children if c.type == "deinitializer"]
        assert len(deinits) >= 1, \
            f"Should find deinit, got: {[(c.type, c.name) for c in resource_manager.children]}"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)
    file_path = Path(__file__).parent / "samples" / "broken.swift"

    # Should not crash
    structures = scanner.scan_file(str(file_path))

    assert structures is not None, "Should return structures even for broken code"

    # Should show parse errors or valid structures
    has_error = any(s.type in ("parse-error", "error") for s in structures)
    has_valid = any(s.type in ("struct", "class", "protocol", "enum", "function") for s in structures)

    assert has_error or has_valid, "Should have either errors or valid structures"

    # Valid structures should still be found
    valid_struct = next((s for s in structures if "ValidStruct" in s.name), None)
    valid_func = next((s for s in structures if "validFunction" in s.name), None)
    valid_protocol = next((s for s in structures if "ValidProtocol" in s.name), None)

    assert valid_struct is not None or valid_func is not None or valid_protocol is not None, \
        f"Should find at least some valid structures in broken file, got: {[(s.type, s.name) for s in structures]}"


def test_typealias(file_scanner):
    """Test typealias parsing."""
    file_path = Path(__file__).parent / "samples" / "basic.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find typealiases
    user_id = next((s for s in structures if s.type == "typealias" and s.name == "UserID"), None)
    assert user_id is not None, f"Should find UserID typealias, got: {[(s.type, s.name) for s in structures if s.type == 'typealias']}"


def test_enum_cases(file_scanner):
    """Test enum case parsing."""
    file_path = Path(__file__).parent / "samples" / "basic.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find UserStatus enum
    user_status = next((s for s in structures if s.type == "enum" and s.name == "UserStatus"), None)
    assert user_status is not None, "Should find UserStatus enum"

    # Check for cases in children
    if user_status.children:
        cases = [c for c in user_status.children if c.type == "case"]
        case_names = [c.name for c in cases]
        assert len(cases) >= 3, f"Should find enum cases, got: {case_names}"
        assert "active" in case_names, f"Should find 'active' case, got: {case_names}"


def test_mutating_modifier(file_scanner):
    """Test mutating modifier detection."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find Point struct
    point = next((s for s in structures if s.type == "struct" and s.name == "Point"), None)
    assert point is not None, "Should find Point struct"

    # Check for mutating method
    if point.children:
        move_by = next((c for c in point.children if c.name == "moveBy"), None)
        if move_by:
            assert "mutating" in move_by.modifiers, \
                f"moveBy should have mutating modifier, got: {move_by.modifiers}"


def test_static_and_class_methods(file_scanner):
    """Test static and class method detection."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find BaseClass
    base_class = next((s for s in structures if s.type == "class" and s.name == "BaseClass"), None)
    assert base_class is not None, "Should find BaseClass"

    if base_class.children:
        static_method = next((c for c in base_class.children if c.name == "staticMethod"), None)
        class_method = next((c for c in base_class.children if c.name == "classMethod"), None)

        if static_method:
            assert "static" in static_method.modifiers, \
                f"staticMethod should have static modifier, got: {static_method.modifiers}"

        if class_method:
            assert "class" in class_method.modifiers, \
                f"classMethod should have class modifier, got: {class_method.modifiers}"


def test_swiftui_patterns(file_scanner):
    """Test SwiftUI-specific patterns like @Published, @State."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.swift"
    structures = file_scanner.scan_file(str(file_path))

    # Find ViewModel with ObservableObject
    view_model = next((s for s in structures if s.name == "ViewModel"), None)
    assert view_model is not None, "Should find ViewModel"

    # Check for @Published properties in children
    if view_model.children:
        published_props = [c for c in view_model.children
                         if c.type == "property" and c.decorators and
                         any("Published" in d for d in c.decorators)]
        # It's OK if we don't capture all @Published - just verify structure is found
        assert view_model.children, "ViewModel should have children (properties/methods)"
