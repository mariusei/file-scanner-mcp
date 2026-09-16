"""Tests for TypeScript and TSX scanner."""

import os
import tempfile
from pathlib import Path

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner, tree_formatter):
    """Test that TypeScript scanner can parse a basic .ts file."""
    file_path = Path(__file__).parent / "samples" / "basic.ts"

    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, f"Should parse {file_path}"
    assert len(structures) > 0, "Should find at least one structure"

    assert any(s.type == "interface" and s.name == "Config" for s in structures), (
        "Should find Config interface"
    )

    assert any(s.type == "class" and s.name == "AuthService" for s in structures), (
        "Should find AuthService class"
    )

    assert any(s.type == "class" and s.name == "UserManager" for s in structures), (
        "Should find UserManager class"
    )

    assert any(s.type == "function" and s.name == "generateId" for s in structures), (
        "Should find generateId function"
    )

    assert any(s.type == "function" and s.name == "validateEmail" for s in structures), (
        "Should find validateEmail function"
    )


def test_tsx_parsing(file_scanner, tree_formatter):
    """Test that TypeScript scanner can parse TSX files with React components."""
    file_path = Path(__file__).parent / "samples" / "jsx.tsx"

    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, f"Should parse {file_path}"
    assert len(structures) > 0, "Should find at least one structure"

    assert any(s.type == "interface" and s.name == "UserCardProps" for s in structures), (
        "Should find UserCardProps interface"
    )

    assert any(s.type == "interface" and s.name == "User" for s in structures), (
        "Should find User interface"
    )

    has_user_card = any(s.type == "function" and "UserCard" in s.name for s in structures)
    assert has_user_card, "Should find UserCard component"

    assert any(s.type == "class" and s.name == "UserList" for s in structures), (
        "Should find UserList class component"
    )

    assert any(s.type == "function" and s.name == "useUserData" for s in structures), (
        "Should find useUserData hook"
    )


def test_signatures(file_scanner):
    """Test that function signatures are extracted correctly."""
    file_path = Path(__file__).parent / "samples" / "basic.ts"
    structures = file_scanner.scan_file(str(file_path))

    func = next((s for s in structures if s.type == "function" and s.name == "generateId"), None)
    assert func is not None, "Should find generateId function"

    assert func.signature is not None, "Should have signature"
    assert "string" in func.signature, "Signature should include return type"

    func = next((s for s in structures if s.type == "function" and s.name == "validateEmail"), None)
    assert func is not None, "Should find validateEmail function"

    assert func.signature is not None, "Should have signature"
    assert "email" in func.signature, "Signature should include parameter"
    assert "boolean" in func.signature, "Signature should include return type"


def test_jsdoc_extraction(file_scanner):
    """Test that JSDoc comments are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.ts"
    structures = file_scanner.scan_file(str(file_path))

    config = next((s for s in structures if s.type == "interface" and s.name == "Config"), None)
    assert config is not None, "Should find Config interface"

    assert config.docstring is not None, "Should have JSDoc comment"
    assert len(config.docstring) > 0, "JSDoc should not be empty"

    auth_service = next(
        (s for s in structures if s.type == "class" and s.name == "AuthService"), None
    )
    assert auth_service is not None, "Should find AuthService class"

    assert auth_service.docstring is not None, "Should have JSDoc comment"


def test_nested_structures(file_scanner):
    """Test that nested structures (methods in classes) work correctly."""
    file_path = Path(__file__).parent / "samples" / "basic.ts"
    structures = file_scanner.scan_file(str(file_path))

    auth_service = next(
        (s for s in structures if s.type == "class" and s.name == "AuthService"), None
    )
    assert auth_service is not None, "Should find AuthService class"

    assert len(auth_service.children) > 0, "Class should have methods"

    has_login = any(c.type == "method" and c.name == "login" for c in auth_service.children)
    assert has_login, "Should find login method in AuthService"

    has_logout = any(c.type == "method" and c.name == "logout" for c in auth_service.children)
    assert has_logout, "Should find logout method in AuthService"

    login_method = next((c for c in auth_service.children if c.name == "login"), None)
    assert login_method is not None, "Should find login method"
    assert login_method.signature is not None, "Login method should have signature"
    assert "username" in login_method.signature, "Signature should include username parameter"
    assert "password" in login_method.signature, "Signature should include password parameter"


def test_modifiers(file_scanner):
    """Test that modifiers (async, private, etc.) are extracted."""
    file_path = Path(__file__).parent / "samples" / "basic.ts"
    structures = file_scanner.scan_file(str(file_path))

    auth_service = next(
        (s for s in structures if s.type == "class" and s.name == "AuthService"), None
    )
    assert auth_service is not None, "Should find AuthService class"

    login_method = next((c for c in auth_service.children if c.name == "login"), None)
    assert login_method is not None, "Should find login method"
    assert "async" in login_method.modifiers, "Login method should be marked as async"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)

    malformed_code = """
    class Broken {
        method(incomplete
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
        f.write(malformed_code)
        temp_path = f.name

    try:
        structures = scanner.scan_file(temp_path)

        assert structures is not None, "Should return structures even for broken code"

        has_error = any(
            s.type in ("parse-error", "error") or "\u26a0" in s.name for s in structures
        )

    finally:
        os.unlink(temp_path)


def test_fallback_mode():
    """Test that regex fallback works for severely broken files."""
    scanner = FileScanner(fallback_on_errors=True)

    very_broken_code = """
    class SomewhatRecognizable {{{
        broken syntax here

    interface AnotherOne {{
        incomplete

    function stillVisible() {{{{
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
        f.write(very_broken_code)
        temp_path = f.name

    try:
        structures = scanner.scan_file(temp_path)

        assert structures is not None, "Should return structures even for very broken code"

        fallback_used = any(
            "\u26a0" in s.name and s.type not in ("parse-error", "error") for s in structures
        )
        if fallback_used:
            has_class = any("SomewhatRecognizable" in s.name for s in structures)
            has_interface = any("AnotherOne" in s.name for s in structures)
            assert has_class or has_interface, "Fallback should extract some structures"

    finally:
        os.unlink(temp_path)


def test_export_lists_and_default_exports_record_the_export_modifier(file_scanner):
    """`export { a, b as c }` and `export default a` export names defined
    elsewhere in the module; the handler records them as it records an
    inline `export function`. A `from` clause names another module's."""
    source = (
        "function a() {}\nfunction b() {}\nfunction d() {}\nfunction x() {}\nclass K {}\n"
        'export { a, b as c };\nexport default d;\nexport { x } from "./x";\n'
    )
    by_name = {s.name: s for s in file_scanner.scan_content(source, "m.ts")}
    assert "export" in by_name["a"].modifiers and "export" in by_name["b"].modifiers
    assert "export" in by_name["d"].modifiers
    assert "export" not in by_name["x"].modifiers and "export" not in by_name["K"].modifiers


def test_privacy_is_export_at_module_scope_and_private_members_in_a_class():
    from scantool.languages import get_language
    from scantool.languages.models import StructureNode

    ts = get_language(".ts")

    def node(name, modifiers, type="function"):
        return StructureNode(type=type, name=name, start_line=1, end_line=1, modifiers=modifiers)

    assert not ts.is_private(node("shown", ["export"]))
    assert not ts.is_private(node("_shown", ["async", "export"]))
    assert ts.is_private(node("hidden", []))
    assert ts.is_private(node("Hidden", ["abstract"], type="class"))
    assert not ts.is_private(node("run", [], type="method"))
    assert ts.is_private(node("run", ["private"], type="method"))
    assert ts.is_private(node("run", ["protected", "async"], type="method"))
    assert ts.is_private(node("#run", [], type="method"))


def test_surface_follows_the_facade(tmp_path):
    """index.ts is the facade: re-export lists with aliases, wildcards,
    namespaces, default exports, a chain through a module's own re-export,
    the facade's own exports, a dependency and a name nobody defines."""
    from scantool.surface import read_surface

    (tmp_path / "index.ts").write_text(
        'export { A, B as C } from "./a";\nexport * from "./b";\nexport * as ns from "./sub/c";\n'
        "export { local };\nexport default main;\nexport const MAX = 3;\n"
        "export function own(): void {}\nfunction local(): number {\n  return 1;\n}\n"
        "function main(): void {}\nfunction hidden(): void {}\n"
        'export { Deep } from "./a";\nexport { Missing } from "./a";\n'
        'export { thing } from "lodash";\n'
    )
    (tmp_path / "a.ts").write_text(
        "export class A {}\nexport function B(): void {}\n"
        'export { Deep } from "./sub/c";\nfunction priv() {}\n'
    )
    (tmp_path / "b.ts").write_text(
        "export interface Task {\n  name: string;\n}\n"
        "export const arrow = () => 1;\nfunction nope() {}\n"
    )
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.ts").write_text(
        "export class Deep {}\nexport function cfun(): void {}\n"
    )
    pkg = tmp_path.name
    surface = read_surface(str(tmp_path))
    rows = [(e.name, e.kind, e.via, e.module, e.path) for e in surface.exports]
    assert rows == [
        ("A", "class", "re-export", "a", f"{pkg}/a.ts"),
        ("C", "function", "re-export", "a", f"{pkg}/a.ts"),
        ("Task", "interface", "re-export", "b", f"{pkg}/b.ts"),
        ("arrow", "function", "re-export", "b", f"{pkg}/b.ts"),
        ("ns", "module", "re-export", "sub.c", f"{pkg}/sub/c.ts"),
        ("local", "function", "definition", "index", f"{pkg}/index.ts"),
        ("main", "function", "default export", "index", f"{pkg}/index.ts"),
        ("MAX", "variable", "definition", "index", f"{pkg}/index.ts"),
        ("own", "function", "definition", "index", f"{pkg}/index.ts"),
        ("Deep", "class", "re-export", "sub.c", f"{pkg}/sub/c.ts"),
        ("Missing", "unresolved", "re-export", "a", f"{pkg}/a.ts"),
        ("thing", "external", "re-export", "lodash", None),
    ]
    by_name = {e.name: e for e in surface.exports}
    assert by_name["MAX"].signature == "= 3" and by_name["MAX"].line == 6
    assert by_name["ns"].signature == "module (2 exported names)"
    assert by_name["local"].signature == "() : number" and by_name["local"].line == 8
    assert by_name["thing"].signature == "from lodash (outside the package)"


def test_surface_without_a_facade_is_each_files_exports(tmp_path):
    from scantool.surface import read_surface

    (tmp_path / "m.ts").write_text(
        "export class A {}\nclass B {}\nfunction c() {}\nfunction d() {}\nexport { d };\n"
    )
    assert [(e.name, e.via) for e in read_surface(str(tmp_path)).exports] == [
        ("A", "definition"),
        ("d", "definition"),
    ]


# ===========================================================================
# File-scope constants (the rule Python's module constants set)
# ===========================================================================

CONSTANTS_TS = (
    'import { x } from "./x";\n'
    "\n"
    "export const LIMIT: number = 3;\n"
    "/** Attempts before giving up. */\n"
    'let label = "y";\n'
    "const handler = () => 1;\n"
    "var legacy = function () {};\n"
    'const fs = require("fs");\n'
    'const lazy = await import("./lazy");\n'
    "const { a, b } = pair;\n"
    "function f() {\n"
    "  const inner = 1;\n"
    "  return inner;\n"
    "}\n"
)


def test_program_scope_bindings_become_variable_nodes(tmp_path, file_scanner):
    """A const/let/var at program scope is a variable node, `= value` as its
    signature, `export` recorded as on a function, the JSDoc above as its
    docstring (an inline-exported declaration hides its JSDoc behind the
    `export` keyword, for a constant as for a function)."""
    path = tmp_path / "consts.ts"
    path.write_text(CONSTANTS_TS)
    structures = file_scanner.scan_file(str(path), include_file_metadata=False)
    variables = {s.name: s for s in structures if s.type == "variable"}

    assert set(variables) == {"LIMIT", "label"}
    assert variables["LIMIT"].signature == "= 3"
    assert variables["LIMIT"].modifiers == ["export"]
    assert variables["label"].docstring == "Attempts before giving up."
    assert variables["LIMIT"].start_line == variables["LIMIT"].end_line == 3
    assert variables["label"].signature == '= "y"'
    assert variables["label"].modifiers == []
    assert all(not v.synthetic for v in variables.values())


def test_program_scope_bindings_skip_definitions_loads_and_inner_scopes(tmp_path, file_scanner):
    """An arrow is the function node alone (never also a variable), a
    function or class expression is no value, `require`/`import(...)` is an
    import, a destructured target names no single binding, and a binding
    inside a function is not the file's."""
    path = tmp_path / "consts.ts"
    path.write_text(CONSTANTS_TS)
    structures = file_scanner.scan_file(str(path), include_file_metadata=False)

    assert [s.type for s in structures if s.name == "handler"] == ["function"]
    names = {s.name for s in structures}
    assert not names & {"legacy", "fs", "lazy", "a", "b", "inner"}


def test_surface_lists_an_exported_constant_not_a_private_one(tmp_path):
    from scantool.surface import read_surface

    (tmp_path / "m.ts").write_text(
        "export const LIMIT = 3;\nconst hidden = 1;\nexport function f(): void {}\n"
    )
    rows = [(e.name, e.kind, e.signature) for e in read_surface(str(tmp_path)).exports]
    assert rows == [("LIMIT", "variable", "= 3"), ("f", "function", "() : void")]
