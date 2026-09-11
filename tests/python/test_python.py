"""Tests for Python scanner."""

from conftest import validate_line_range_invariants

from scantool.languages.python import PythonLanguage
from scantool.scanner import FileScanner


def test_nested_closure_call_attribution():
    """A call inside a nested closure attributes to the enclosing EXTRACTED
    definition, not the (un-extracted) closure.

    Regression: the language handlers use `def traverse(): ... self._helper()`.
    Attributing the call to `traverse` (not a definition, so not a graph node)
    made resolve(caller) empty and dropped the edge — every helper call vanished
    from the call graph, producing false "dead" functions.
    """
    src = (
        "class C:\n"
        "    def outer(self):\n"
        "        def inner(node):\n"
        "            self.helper(node)\n"
        "        inner(0)\n"
        "    def helper(self, n):\n"
        "        pass\n"
    )
    lang = PythonLanguage()
    defs = lang.extract_definitions("c.py", src)
    calls = lang.extract_calls("c.py", src, defs)

    helper_calls = [c for c in calls if c.callee_name == "helper"]
    assert helper_calls, "self.helper(...) call was not captured at all"
    # attributed to the method, not the closure
    assert all(c.caller_name == "outer" for c in helper_calls), [
        c.caller_name for c in helper_calls
    ]


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
    func = next(
        (s for s in structures if s.type == "function" and s.name == "validate_email"), None
    )
    assert func is not None, "Should find validate_email"
    assert func.signature is not None, "Should have signature"
    assert "(email: str) -> bool" in func.signature, (
        f"Signature should match, got: {func.signature}"
    )


def test_docstrings(file_scanner):
    """Test that docstrings are extracted."""
    structures = file_scanner.scan_file("tests/python/samples/basic.py")

    # Find DatabaseManager class
    db_class = next(
        (s for s in structures if s.type == "class" and s.name == "DatabaseManager"), None
    )
    assert db_class is not None, "Should find DatabaseManager"
    assert db_class.docstring is not None, "Should have docstring"
    assert "database" in db_class.docstring.lower(), (
        f"Docstring should mention database, got: {db_class.docstring}"
    )


def test_edge_cases(file_scanner):
    """Test edge cases like nested classes, decorators, etc."""
    structures = file_scanner.scan_file("tests/python/samples/edge_cases.py")

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    # Test nested classes
    outer = next((s for s in structures if s.type == "class" and s.name == "OuterClass"), None)
    assert outer is not None, "Should find OuterClass"
    assert len(outer.children) > 0, "Should have nested classes"
    assert any(c.type == "class" and c.name == "InnerClass" for c in outer.children), (
        "Should find InnerClass"
    )

    # Test decorators
    showcase = next(
        (s for s in structures if s.type == "class" and s.name == "DecoratorShowcase"), None
    )
    assert showcase is not None, "Should find DecoratorShowcase"

    # Find property method
    prop_method = next((c for c in showcase.children if c.name == "prop"), None)
    assert prop_method is not None, "Should find prop method"
    assert "@property" in prop_method.decorators, "Should have @property decorator"
    assert "property" in prop_method.modifiers, "Should have property modifier"

    # Test async functions
    async_service = next(
        (s for s in structures if s.type == "class" and s.name == "AsyncService"), None
    )
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
    func = next(
        (s for s in structures if s.type == "function" and s.name == "multi_line_doc"), None
    )
    assert func is not None, "Should find multi_line_doc"


def test_complex_signatures(file_scanner):
    """Test complex type hint signatures."""
    structures = file_scanner.scan_file("tests/python/samples/edge_cases.py")

    # Find GenericContainer class
    generic = next(
        (s for s in structures if s.type == "class" and s.name == "GenericContainer"), None
    )
    assert generic is not None, "Should find GenericContainer"

    # Find process method with complex signature
    process = next((c for c in generic.children if c.name == "process"), None)
    assert process is not None, "Should find process method"
    assert process.signature is not None, "Should have signature"

    # Check that complex types are preserved
    sig = process.signature
    assert "List" in sig or "Dict" in sig or "Union" in sig, (
        f"Should preserve complex types in: {sig}"
    )


def test_line_range_invariants(file_scanner):
    """Test universal line range invariants for Python scanner."""
    structures = file_scanner.scan_file("tests/python/samples/basic.py")
    validate_line_range_invariants(structures)

    # Also test edge cases file
    structures = file_scanner.scan_file("tests/python/samples/edge_cases.py")
    validate_line_range_invariants(structures)


# ===========================================================================
# Module-level structure: the docstring and named module-level bindings
# ===========================================================================
# Inline sources on purpose: tests/python/samples/basic.py is frozen input for
# the golden output contract, so the cases below bring their own.

MODULE_LEVEL_SRC = '''"""Policy for the widget pipeline.

Second paragraph, not the summary.
"""

from typing import TYPE_CHECKING

MAX_RETRIES = 3
TIMEOUT: float = 2.5
LIMITS = {"soft": 10, "hard": 20}
FIRST, SECOND = 1, 2
MAX_RETRIES += 1
config.debug = True
LATER: int

if TYPE_CHECKING:
    GUARDED = 1

try:
    BACKEND = "fast"
except ImportError:
    BACKEND = "slow"


def handler():
    local_only = 1
    return local_only


class Widget:
    class_attr = 5
'''


def _write(tmp_path, source: str, name: str = "mod.py"):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_module_docstring_is_a_synthetic_node(tmp_path, file_scanner):
    path = _write(tmp_path, MODULE_LEVEL_SRC)
    structures = file_scanner.scan_file(str(path), include_file_metadata=False)

    doc = structures[0]
    assert doc.type == "docstring"
    assert doc.name == "module docstring"
    # the name is scantool's label, not a name on line 1
    assert doc.synthetic is True
    assert doc.docstring == "Policy for the widget pipeline."
    assert (doc.start_line, doc.end_line) == (1, 4)


def test_module_docstring_absent_when_the_module_has_none(tmp_path, file_scanner):
    path = _write(tmp_path, "import os\n\n\ndef f():\n    return os\n")
    structures = file_scanner.scan_file(str(path), include_file_metadata=False)

    assert not [s for s in structures if s.type == "docstring"]


def test_module_level_bindings_become_variable_nodes(tmp_path, file_scanner):
    path = _write(tmp_path, MODULE_LEVEL_SRC)
    structures = file_scanner.scan_file(str(path), include_file_metadata=False)
    variables = {s.name: s for s in structures if s.type == "variable"}

    # plain, annotated, container, and a name bound under a module-level `if`
    assert set(variables) == {"MAX_RETRIES", "TIMEOUT", "LIMITS", "GUARDED"}
    assert variables["MAX_RETRIES"].signature == "= 3"
    assert variables["TIMEOUT"].signature == "= 2.5"
    assert variables["LIMITS"].signature == "= {'soft': 10, 'hard': 20}"

    # a real name from the source: never synthetic
    assert all(not v.synthetic for v in variables.values())


def test_module_level_bindings_skip_what_names_no_single_value(tmp_path, file_scanner):
    """Tuple unpacking, augmented assignment, attribute targets and bare
    annotations are out; so is anything bound deeper than module scope."""
    path = _write(tmp_path, MODULE_LEVEL_SRC)
    structures = file_scanner.scan_file(str(path), include_file_metadata=False)
    names = {s.name for s in structures if s.type == "variable"}

    assert not names & {"FIRST", "SECOND", "config", "debug", "LATER"}
    assert "local_only" not in names, "a function-local binding is not module level"
    assert "class_attr" not in names, "class attributes are out of scope"
    assert "BACKEND" not in names, "a try/except fallback binds one name twice - two nodes, one key"


def test_long_values_are_elided_not_dumped(tmp_path, file_scanner):
    src = "NAMES = [\n" + "".join(f'    "entry_number_{i}",\n' for i in range(40)) + "]\n"
    path = _write(tmp_path, src)
    node = file_scanner.scan_file(str(path), include_file_metadata=False)[0]

    assert node.type == "variable" and node.name == "NAMES"
    assert node.signature.endswith("…"), node.signature
    assert len(node.signature) < 200, "the value is a signature, not a dump"


def test_a_module_of_constants_stays_header_only(tmp_path, file_scanner):
    """A constant node's header already carries its value, so it never earns a
    skeleton - 40 constants must not become 40 skeleton blocks."""
    src = "".join(f'C{i} = {{\n    "a": {i},\n    "b": {i + 1},\n}}\n' for i in range(40))
    path = _write(tmp_path, src)
    structures = file_scanner.scan_file(str(path), include_file_metadata=False, budget=300)

    assert len(structures) == 40
    assert not [s for s in structures if s.code_skeleton or s.code_excerpt]


def test_module_level_values_are_not_call_graph_definitions():
    """Hot functions and dead-code detection read DefinitionInfo. A constant is
    not a definition, so it can neither be called nor be reported dead."""
    lang = PythonLanguage()
    definitions = lang.extract_definitions("mod.py", MODULE_LEVEL_SRC)

    assert {d.name for d in definitions} == {"handler", "Widget"}


def test_a_changed_constant_is_reported_as_changed(tmp_path, file_scanner):
    from scantool.delta import diff_nodes, node_hashes

    before = "TIMEOUT = 2.5\n\n\ndef f():\n    return TIMEOUT\n"
    after = "TIMEOUT = 9.5\n\n\ndef f():\n    return TIMEOUT\n"

    path = _write(tmp_path, before)
    old = node_hashes(
        file_scanner.scan_file(str(path), include_file_metadata=False), before.split("\n")
    )
    path = _write(tmp_path, after, name="mod2.py")
    new = node_hashes(
        file_scanner.scan_file(str(path), include_file_metadata=False), after.split("\n")
    )

    diff = diff_nodes(old, new)
    assert "/variable:TIMEOUT" in diff.changed
    assert "/function:f" in diff.unchanged


def test_focus_prints_a_constant_verbatim(tmp_path, file_scanner):
    from scantool.focus import format_focus

    src = 'LIMITS = {\n    "soft": 10,\n    "hard": 20,\n}\n'
    path = _write(tmp_path, src)
    structures = file_scanner.scan_file(str(path), include_file_metadata=False)

    out = format_focus(str(path), structures, src.split("\n"), "LIMITS")

    assert out.startswith("focus: LIMITS @1-4")
    assert "1 | LIMITS = {" in out
    assert '2 |     "soft": 10,' in out
