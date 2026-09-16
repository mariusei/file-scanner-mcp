"""Tests for Zig scanner."""


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
    assert any(c.type == "method" and c.name == "total" for c in config.children), (
        f"Should find total method, got: {[c.name for c in config.children]}"
    )


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
    assert "Configuration" in config.docstring, (
        f"Docstring should describe struct, got: {config.docstring}"
    )


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
    c_api = next(
        (s for s in structures if s.type == "function" and s.name == "c_api_function"), None
    )
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
    generic_list = next(
        (s for s in structures if s.type == "function" and s.name == "GenericList"), None
    )
    assert generic_list is not None, "Should find GenericList function"

    # Test complex union
    parse_result = next(
        (s for s in structures if s.type == "union" and s.name == "ParseResult"), None
    )
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
    assert any("AnotherStruct" in s.name for s in structures), (
        f"Should find AnotherStruct, got: {[s.name for s in structures]}"
    )


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


def test_privacy_is_pub_or_export_not_the_name():
    """No naming convention in Zig: the keyword decides. `export` is the C-ABI
    surface, `extern` only declares a symbol defined elsewhere."""
    from scantool.languages import get_language
    from scantool.languages.models import StructureNode

    zig = get_language(".zig")

    def node(name, modifiers, type="function"):
        return StructureNode(type=type, name=name, start_line=1, end_line=1, modifiers=modifiers)

    assert not zig.is_private(node("shown", ["pub"]))
    assert not zig.is_private(node("_shown", ["pub", "inline"]))
    assert not zig.is_private(node("c_api", ["export"]))
    assert zig.is_private(node("helper", []))
    assert zig.is_private(node("declared_elsewhere", ["extern"]))
    assert zig.is_private(node("basic test", [], type="test"))


def test_surface_is_each_files_pub_declarations(tmp_path):
    from scantool.surface import read_surface

    (tmp_path / "lib.zig").write_text(
        'const std = @import("std");\npub const Config = struct {\n    pub fn total() i32 {\n'
        "        return 1;\n    }\n};\nconst Hidden = struct {};\npub fn shown() void {}\n"
        'fn helper() void {}\nexport fn c_api() void {}\ntest "it" {}\n'
    )
    rows = [(e.name, e.kind, e.via) for e in read_surface(str(tmp_path)).exports]
    assert rows == [
        ("Config", "struct", "definition"),
        ("shown", "function", "definition"),
        ("c_api", "function", "definition"),
    ]


# ===========================================================================
# File-scope constants (the rule Python's module constants set)
# ===========================================================================

CONSTANTS_ZIG = (
    'const std = @import("std");\n'
    'const Thing = @import("thing.zig").Thing;\n'
    "\n"
    "/// Attempts before giving up.\n"
    "pub const LIMIT: u32 = 3;\n"
    "var counter: u32 = 0;\n"
    'const name = "x";\n'
    "const alias = f;\n"
    "pub const Point = struct { x: i32 };\n"
    "pub fn f() u32 {\n"
    "    const inner = 1;\n"
    "    return inner;\n"
    "}\n"
)


def test_file_scope_values_become_variable_nodes(tmp_path, file_scanner):
    """A plain `const`/`var` at file scope is a variable node, `= value` as
    signature, the doc comment as docstring and `pub` recorded as on a
    function; a struct/enum/union const stays what it was."""
    path = tmp_path / "consts.zig"
    path.write_text(CONSTANTS_ZIG)
    structures = file_scanner.scan_file(str(path), include_file_metadata=False)
    variables = {s.name: s for s in structures if s.type == "variable"}

    assert set(variables) == {"LIMIT", "counter", "name", "alias"}
    assert variables["LIMIT"].signature == "= 3"
    assert variables["LIMIT"].modifiers == ["pub"]
    assert variables["LIMIT"].docstring == "Attempts before giving up."
    assert variables["counter"].signature == "= 0"
    assert variables["counter"].modifiers == []
    assert variables["name"].signature == '= "x"'
    assert variables["alias"].signature == "= f"
    assert [s.type for s in structures if s.name == "Point"] == ["struct"]
    assert all(not v.synthetic for v in variables.values())


def test_imports_and_inner_bindings_are_not_file_scope_values(tmp_path, file_scanner):
    """`@import(...)` and a name taken from one are imports; a const inside a
    function is not the file's; a function is bound once (an alias holds a
    name, not a second definition)."""
    path = tmp_path / "consts.zig"
    path.write_text(CONSTANTS_ZIG)
    structures = file_scanner.scan_file(str(path), include_file_metadata=False)

    names = [s.name for s in structures]
    assert not set(names) & {"std", "Thing", "inner"}
    assert names.count("f") == 1


def test_surface_lists_a_pub_constant_not_a_file_private_one(tmp_path):
    from scantool.surface import read_surface

    (tmp_path / "m.zig").write_text(
        "pub const LIMIT: u32 = 3;\nvar counter: u32 = 0;\npub fn f() void {}\n"
    )
    rows = [(e.name, e.kind, e.signature) for e in read_surface(str(tmp_path)).exports]
    assert rows == [("LIMIT", "variable", "= 3"), ("f", "function", "() void")]
