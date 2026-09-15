"""Tests for Go scanner."""

from pathlib import Path

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic Go file parsing."""
    file_path = Path(__file__).parent / "samples" / "basic.go"
    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, "Should parse Go file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected structures
    assert any(s.type == "struct" and s.name == "Config" for s in structures), (
        "Should find Config struct"
    )
    assert any(s.type == "struct" and s.name == "DatabaseManager" for s in structures), (
        "Should find DatabaseManager struct"
    )
    assert any(s.type == "interface" and s.name == "Logger" for s in structures), (
        "Should find Logger interface"
    )
    assert any(s.type == "function" and s.name == "ValidateEmail" for s in structures), (
        "Should find ValidateEmail function"
    )


def test_signatures(file_scanner):
    """Test that signatures are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "basic.go"
    structures = file_scanner.scan_file(str(file_path))

    # Find ValidateEmail function
    func = next((s for s in structures if s.type == "function" and s.name == "ValidateEmail"), None)
    assert func is not None, "Should find ValidateEmail"
    assert func.signature is not None, "Should have signature"
    assert "email string" in func.signature, (
        f"Signature should include parameter, got: {func.signature}"
    )
    assert "bool" in func.signature, f"Signature should include return type, got: {func.signature}"


def test_methods(file_scanner):
    """Test that methods with receivers are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.go"
    structures = file_scanner.scan_file(str(file_path))

    # Find Connect method
    method = next((s for s in structures if s.type == "method" and s.name == "Connect"), None)
    assert method is not None, "Should find Connect method"
    assert method.signature is not None, "Should have signature"
    # Receiver should be in signature
    assert "DatabaseManager" in method.signature, (
        f"Signature should include receiver, got: {method.signature}"
    )


def test_docstrings(file_scanner):
    """Test that comments are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.go"
    structures = file_scanner.scan_file(str(file_path))

    # Find DatabaseManager struct
    struct = next(
        (s for s in structures if s.type == "struct" and s.name == "DatabaseManager"), None
    )
    assert struct is not None, "Should find DatabaseManager"
    assert struct.docstring is not None, "Should have docstring"
    assert "database" in struct.docstring.lower(), (
        f"Docstring should mention database, got: {struct.docstring}"
    )


def test_visibility_modifiers(file_scanner):
    """Test that public/private visibility is detected based on capitalization."""
    file_path = Path(__file__).parent / "samples" / "basic.go"
    structures = file_scanner.scan_file(str(file_path))

    # Public struct (capitalized)
    config = next((s for s in structures if s.type == "struct" and s.name == "Config"), None)
    assert config is not None, "Should find Config"
    assert "public" in config.modifiers, "Config should be public"

    # Public function (capitalized)
    validate = next(
        (s for s in structures if s.type == "function" and s.name == "ValidateEmail"), None
    )
    assert validate is not None, "Should find ValidateEmail"
    assert "public" in validate.modifiers, "ValidateEmail should be public"

    # Private function (lowercase) - main is not public in Go
    main_func = next((s for s in structures if s.type == "function" and s.name == "main"), None)
    if main_func:
        # main function exists but is not marked as public
        assert "public" not in main_func.modifiers, "main should not be public"


def test_edge_cases(file_scanner):
    """Test edge cases like generics, channels, defer, etc."""
    file_path = Path(__file__).parent / "samples" / "edge_cases.go"
    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    # Test generic types
    generic = next(
        (s for s in structures if s.type == "struct" and "GenericContainer" in s.name), None
    )
    assert generic is not None, "Should find GenericContainer"

    # Test named return values
    divide = next(
        (s for s in structures if s.type == "function" and s.name == "DivideWithRemainder"), None
    )
    assert divide is not None, "Should find DivideWithRemainder"
    assert divide.signature is not None, "Should have signature"
    # Should have multiple return values
    assert "quotient" in divide.signature or "int" in divide.signature, (
        f"Should show return values, got: {divide.signature}"
    )

    # Test variadic function
    sum_func = next((s for s in structures if s.type == "function" and s.name == "Sum"), None)
    assert sum_func is not None, "Should find Sum function"
    assert sum_func.signature is not None, "Should have signature"
    assert "..." in sum_func.signature or "numbers" in sum_func.signature, (
        f"Should show variadic parameter, got: {sum_func.signature}"
    )

    # Test pointer vs value receiver
    increment = next((s for s in structures if s.type == "method" and s.name == "Increment"), None)
    assert increment is not None, "Should find Increment method"
    assert increment.signature is not None, "Should have signature"
    # Pointer receiver should be indicated
    assert "*Counter" in increment.signature, (
        f"Should show pointer receiver, got: {increment.signature}"
    )

    # Test embedded interfaces
    read_writer = next(
        (s for s in structures if s.type == "interface" and s.name == "ReadWriter"), None
    )
    assert read_writer is not None, "Should find ReadWriter interface"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)
    file_path = Path(__file__).parent / "samples" / "broken.go"

    # Should not crash
    structures = scanner.scan_file(str(file_path))

    assert structures is not None, "Should return structures even for broken code"

    # Should show parse errors or valid structures
    has_error = any(s.type in ("parse-error", "error") for s in structures)
    has_valid = any(s.type in ("struct", "interface", "function", "method") for s in structures)

    assert has_error or has_valid, "Should have either errors or valid structures"

    # Valid structures should still be found
    valid_struct = next((s for s in structures if "ValidStruct" in s.name), None)
    valid_func = next((s for s in structures if "ValidFunction" in s.name), None)

    assert valid_struct is not None or valid_func is not None, (
        "Should find at least some valid structures in broken file"
    )


def test_interface_detection(file_scanner):
    """Test that interfaces are properly detected."""
    file_path = Path(__file__).parent / "samples" / "basic.go"
    structures = file_scanner.scan_file(str(file_path))

    logger = next((s for s in structures if s.type == "interface" and s.name == "Logger"), None)
    assert logger is not None, "Should find Logger interface"
    assert logger.docstring is not None, "Should have docstring"


def test_multiple_return_values(file_scanner):
    """Test that functions with multiple return values have signatures."""
    file_path = Path(__file__).parent / "samples" / "basic.go"
    structures = file_scanner.scan_file(str(file_path))

    # Find CreateUser method with multiple returns
    create_user = next(
        (s for s in structures if s.type == "method" and s.name == "CreateUser"), None
    )
    assert create_user is not None, "Should find CreateUser"
    assert create_user.signature is not None, "Should have signature"
    # Should show both parameters and return types
    assert "username" in create_user.signature or "string" in create_user.signature, (
        f"Should show parameters, got: {create_user.signature}"
    )


def test_privacy_is_capitalisation_not_the_underscore():
    """The handler records a capitalised identifier as "public"; that is the
    whole rule, so is_private reads it and ignores the name's first letter."""
    from scantool.languages import get_language
    from scantool.languages.models import StructureNode

    go = get_language(".go")

    def node(name, modifiers):
        return StructureNode(
            type="function", name=name, start_line=1, end_line=1, modifiers=modifiers
        )

    assert not go.is_private(node("Exported", ["public"]))
    assert go.is_private(node("unexported", []))
    assert go.is_private(node("main", []))
    assert go.is_private(node("_unexported", []))


def test_go_test_runs_test_functions_by_rule():
    from scantool.languages import get_language
    from scantool.languages.models import DefinitionInfo

    go = get_language(".go")

    def definition(name, file="pkg/thing_test.go"):
        return DefinitionInfo(file=file, type="function", name=name, line=1)

    for name in (
        "TestParse",
        "Test",
        "TestMain",
        "Benchmark_x",
        "ExampleParse",
        "FuzzParse",
        "Test1",
    ):
        assert go.is_exempt_from_unreferenced(definition(name)), name
    assert not go.is_exempt_from_unreferenced(definition("Testing"))  # lower-case after the prefix
    assert not go.is_exempt_from_unreferenced(definition("Fuzzy"))
    assert not go.is_exempt_from_unreferenced(definition("helper"))
    assert not go.is_exempt_from_unreferenced(definition("TestParse", file="pkg/thing.go"))


def test_surface_is_the_exported_identifiers_outside_test_files(tmp_path):
    from scantool.surface import read_surface

    (tmp_path / "a.go").write_text(
        "package p\n\ntype Thing struct{}\n\nfunc (t *Thing) Run() {}\n\nfunc (t *Thing) hide() {}\n\n"
        "func New() *Thing { return nil }\n\nfunc helper() {}\n"
    )
    (tmp_path / "a_test.go").write_text(
        "package p\n\nfunc TestNew(t *testing.T) {}\n\nfunc Helper() {}\n"
    )
    rows = [(e.name, e.kind, e.path) for e in read_surface(str(tmp_path)).exports]
    pkg = tmp_path.name
    assert rows == [
        ("Thing", "struct", f"{pkg}/a.go"),
        ("Run", "method", f"{pkg}/a.go"),
        ("New", "function", f"{pkg}/a.go"),
    ]
