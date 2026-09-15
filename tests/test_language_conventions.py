"""Naming conventions and the public surface are the language's (brief §9e):
nothing outside languages/ implements a private-name rule, a qualifier or a
facade syntax. The defaults live on BaseLanguage; Python overrides the
surface with its facade logic; every other handler gets the default.
"""

import re
from pathlib import Path

from scantool.callers import split_qualified
from scantool.languages import get_language, get_registry
from scantool.languages.base import BaseLanguage
from scantool.resolve import bare_name
from scantool.scanner import FileScanner
from scantool.structural_diff import records
from scantool.surface import read_surface

TESTS_DIR = Path(__file__).parent


def test_defaults_live_on_base_language():
    assert BaseLanguage.QUALIFIER == "."
    python = get_language(".py")
    assert python.is_private_name("_helper") and python.is_private_name("__init__")
    assert not python.is_private_name("public")


def test_records_carry_the_language_conventions():
    source = "class K:\n    def _hidden(self):\n        return 1\n\n    def shown(self):\n        return 2\n"
    scanner = FileScanner()
    table = records(scanner.scan_content(source, "m.py"), source.split("\n"), get_language(".py"))
    by_name = {r.name: r for r in table.values()}
    assert by_name["K._hidden"].private and not by_name["K.shown"].private
    assert by_name["K.shown"].qualifier == "." and by_name["K.shown"].bare == "shown"
    plain = records(scanner.scan_content(source, "m.py"), source.split("\n"))
    assert {r.name for r in plain.values()} == {r.name for r in table.values()}


def test_qualified_names_are_split_with_any_registered_qualifier():
    assert split_qualified("Class.method") == ("Class", "method")
    assert split_qualified("plain") == (None, "plain")
    assert bare_name("Class.method") == "method"
    qualifiers = {language.QUALIFIER for language in get_registry().languages()}
    assert "." in qualifiers


def test_default_surface_is_top_level_definitions_not_marked_private(tmp_path):
    (tmp_path / "lib.rb").write_text(
        "class Widget\n  def run\n  end\nend\n\ndef helper\nend\n\ndef _internal\nend\n"
    )
    surface = read_surface(str(tmp_path))
    names = [(e.name, e.kind, e.via) for e in surface.exports]
    assert ("Widget", "class", "definition") in names
    assert ("helper", "function", "definition") in names or (
        "helper",
        "method",
        "definition",
    ) in names
    assert not any(name == "_internal" for name, _, _ in names)
    assert all(e.path.endswith("lib.rb") and e.line for e in surface.exports)


def test_default_surface_looks_through_container_types(tmp_path):
    """SURFACE_CONTAINER_TYPES is empty on the base (a class's methods are
    the class's); a language that names its container type gets the
    members, qualified with the container chain and QUALIFIER, the
    container itself never listed, each member judged on its own. C++ is
    the language here because its namespace is such a type."""
    assert not BaseLanguage.SURFACE_CONTAINER_TYPES
    (tmp_path / "lib.cpp").write_text(
        "namespace outer {\nint one() { return 1; }\nnamespace inner { int two() { return 2; } }\n"
        "class K { public: int three() { return 3; } };\n}\n"
    )
    names = [(e.name, e.kind) for e in read_surface(str(tmp_path)).exports]
    assert names == [
        ("outer.one", "function"),
        ("outer.inner.two", "function"),
        ("outer.K", "class"),
    ]


def test_default_surface_skips_comment_blocks(tmp_path):
    """A comment block is a node so focus can print it, but it is prose, not
    a name the directory exports (reported by a #42 review on a config dir)."""
    (tmp_path / "runtimes.yaml").write_text(
        "# Runtime table for the launcher, kept for one release\n"
        "# so old installs can roll back; do not edit by hand\n\n"
        "promoted: 0.2.0\ndefault: 0.1.1\n"
    )
    names = [(e.name, e.kind) for e in read_surface(str(tmp_path)).exports]
    assert ("promoted", "key") in names or any(name == "promoted" for name, _ in names)
    assert not any(kind == "comment" for _, kind in names), names


def test_python_surface_is_the_python_handlers(tmp_path):
    (tmp_path / "__init__.py").write_text("from .core import Thing\n__all__ = ['Thing']\n")
    (tmp_path / "core.py").write_text("class Thing:\n    def go(self):\n        return 1\n")
    surface = read_surface(str(tmp_path))
    assert [(e.name, e.via, e.listed) for e in surface.exports] == [("Thing", "re-export", True)]
    assert surface.exports[0].path.endswith("core.py")


def _definition(name: str, **fields):
    """A DefinitionInfo as code_health hands the hook: name, modifiers, decorators."""
    from scantool.languages.models import DefinitionInfo

    return DefinitionInfo(file="f", type="function", name=name, line=1, **fields)


def test_default_privacy_reads_the_name_and_a_language_may_read_the_modifiers():
    """is_private(node) is the hook the generic commands ask; its default is
    the name rule, so a language with a visibility keyword overrides it and
    reads node.modifiers instead of inventing a second rule outside."""
    from scantool.languages import get_registry
    from scantool.languages.models import StructureNode

    ruby = get_registry().get(".rb")
    assert ruby.is_private(StructureNode(type="method", name="_helper", start_line=1, end_line=1))
    assert not ruby.is_private(StructureNode(type="method", name="run", start_line=1, end_line=1))
    assert ruby.is_private(_definition("_helper")) and not ruby.is_private(_definition("run"))


def test_qualifiers_never_collide_with_the_address_form():
    """Addresses are path::Qualified.name; a language qualifier containing a
    colon would make them ambiguous, so `::` belongs to the address, never
    to a language, whatever its own spelling is."""
    from scantool.languages import get_registry

    for language in get_registry().languages():
        assert ":" not in language.QUALIFIER, language.get_language_name()


def test_default_unreferenced_exemption_is_none(tmp_path):
    """CODE HEALTH's UNREFERENCED check must not assume any language's
    naming convention by default (brief §9e) — a leading-underscore or
    "test"-prefixed name is only exempt where a language says so. SQL has
    no test runner and no magic names, so it keeps the default."""
    sql = get_language(".sql")
    assert not sql.is_exempt_from_unreferenced(_definition("__init__"))
    assert not sql.is_exempt_from_unreferenced(_definition("test_something"))
    assert not sql.is_exempt_from_unreferenced(_definition("plain"))


def test_python_unreferenced_exemption_covers_dunders_and_pytest_names():
    """Python overrides the default for two reasons a name is invoked
    without a textual reference: dunder methods (object-model machinery)
    and pytest's discovery convention — two different mechanisms, so the
    hook checks both rather than reusing is_private_name (which would
    treat name-mangled-private helpers like __secret as exempt too, even
    though those are ordinary, possibly-dead code)."""
    python = get_language(".py")
    assert python.is_exempt_from_unreferenced(_definition("__init__"))
    assert python.is_exempt_from_unreferenced(_definition("__eq__"))
    assert python.is_exempt_from_unreferenced(_definition("test_compute_behaviour"))
    assert python.is_exempt_from_unreferenced(_definition("TestWidget"))
    assert not python.is_exempt_from_unreferenced(
        _definition("__secret")
    )  # mangled-private, not a dunder
    assert not python.is_exempt_from_unreferenced(_definition("plain_helper"))
    # Same name, non-Python file: the Python-shaped convention must not leak.
    ruby = get_language(".rb")
    assert not ruby.is_exempt_from_unreferenced(_definition("__secret"))


# Named exemptions, each with its reason. The boundary itself: the
# extension -> handler registry (scanner.py) and the ignore patterns
# (gitignore.py) must name file types. connectivity.py and reference_map.py
# hold corpus-scan policies (which file types can carry a handler name or a
# route literal); those tables include file types with no handler (.kt, .vue,
# .properties), so they cannot live behind a language.
BOUNDARY_ALLOWLIST = {
    "scanner.py",
    "gitignore.py",
    "connectivity.py",
    "reference_map.py",
}
BOUNDARY_RED_FLAGS = (
    ("import ast", re.compile(r"^\s*(import ast\b|from ast\b)", re.M)),
    ("tree-sitter", re.compile(r"tree_sitter")),
    (
        "file-extension test",
        re.compile(
            r"""(endswith|startswith)\(\s*\(?\s*['"]\.[A-Za-z0-9]+['"]|\.suffix\b[^\n]*(==|in\s)|['"]\.(py|ts|js|go|rs|rb|java|md)['"]"""
        ),
    ),
    ("language keyword", re.compile(r"""['"](def |class |export |pub |fn |func )['"]""")),
    (
        "naming rule",
        re.compile(r"""startswith\(\s*['"]__['"]\s*\)|rsplit\(\s*['"]\.['"]\s*,\s*1\s*\)"""),
    ),
)


def test_boundary_nothing_outside_languages_knows_a_syntax():
    """Brief §9e: walk src/scantool/ minus languages/ and fail on import ast,
    tree-sitter, file-extension tests, language keywords and naming rules.
    This would have stopped surface.py in #32."""
    package = TESTS_DIR.parent / "src" / "scantool"
    offenders = []
    for path in sorted(package.glob("*.py")):
        if path.name in BOUNDARY_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for label, flag in BOUNDARY_RED_FLAGS:
            match = flag.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.name}:{line}: {label}: {match.group(0).strip()}")
    assert not offenders, "\n".join(offenders)


def test_swift_privacy_reads_the_visibility_keyword():
    """Swift hides a name with `private`/`fileprivate` only: `internal`, the
    default, is API to every file of the module, and a setter restriction
    (`private(set)`) restricts writing, not the name. A leading underscore
    means nothing to the compiler."""
    from scantool.languages.models import StructureNode

    swift = get_language(".swift")

    def node(name, *modifiers):
        return StructureNode(
            type="function", name=name, start_line=1, end_line=1, modifiers=list(modifiers)
        )

    assert swift.is_private(node("retry", "private"))
    assert swift.is_private(node("helper", "fileprivate"))
    assert not swift.is_private(node("validateEmail"))
    assert not swift.is_private(node("connect", "public"))
    assert not swift.is_private(node("isConnected", "private(set)"))
    assert not swift.is_private(node("_underscored"))
    assert swift.is_private(_definition("retry", modifiers=["private"]))


def test_swift_unreferenced_exemption_is_xctest_discovery():
    """XCTest runs `test…` methods of XCTestCase subclasses by name. The hook
    cannot see the superclass, so the enclosing class's conventional name
    is the proxy; the same method name elsewhere is a normal definition."""
    swift = get_language(".swift")

    def method(name, parent, kind="class"):
        return _definition(name, parent=parent, enclosing_kind=kind)

    assert swift.is_exempt_from_unreferenced(method("testConnect", "DatabaseManagerTests"))
    assert swift.is_exempt_from_unreferenced(method("testRetry", "RetryTest"))
    assert not swift.is_exempt_from_unreferenced(method("testConnect", "DatabaseManager"))
    assert not swift.is_exempt_from_unreferenced(method("connect", "DatabaseManagerTests"))
    assert not swift.is_exempt_from_unreferenced(method("testConnect", "LoggerTests", "protocol"))
    assert not swift.is_exempt_from_unreferenced(_definition("testConnect"))


def test_java_privacy_is_public_only():
    """A package's surface is what other packages can name: `public` only.
    No keyword is package-private, `protected` is subclass API, `private`
    hides; a name's spelling means nothing to the compiler."""
    from scantool.languages.models import StructureNode

    java = get_language(".java")

    def node(name, *modifiers):
        return StructureNode(
            type="method", name=name, start_line=1, end_line=1, modifiers=list(modifiers)
        )

    assert not java.is_private(node("connect", "public"))
    assert not java.is_private(node("validateEmail", "public", "static"))
    assert java.is_private(node("tryConnect", "private", "static"))
    assert java.is_private(node("onLoad", "protected"))
    assert java.is_private(node("helper"))  # package-private
    assert not java.is_private(node("_odd", "public"))
    assert java.is_private(_definition("helper"))


def test_java_surface_is_the_public_types_without_the_package_line(tmp_path):
    (tmp_path / "Lib.java").write_text(
        "package com.example;\n\n"
        "public interface Api {\n    String name();\n}\n\n"
        'class Impl implements Api {\n    public String name() { return "x"; }\n}\n\n'
        "public class Widget {\n    private static int count;\n}\n"
    )
    names = [(e.name, e.kind, e.via) for e in read_surface(str(tmp_path)).exports]
    assert names == [("Api", "interface", "definition"), ("Widget", "class", "definition")]


def test_csharp_privacy_is_public_only():
    """An assembly's surface is what other assemblies can name: `public`
    only. `internal` (a type's default) stays in the assembly, `private`
    (a member's default) in the type, `protected` is subclass API."""
    from scantool.languages.models import StructureNode

    csharp = get_language(".cs")

    def node(name, *modifiers):
        return StructureNode(
            type="method", name=name, start_line=1, end_line=1, modifiers=list(modifiers)
        )

    assert not csharp.is_private(node("Connect", "public"))
    assert not csharp.is_private(node("ValidateEmail", "public", "static"))
    assert csharp.is_private(node("TryConnect", "private", "static"))
    assert csharp.is_private(node("Helper", "internal"))
    assert csharp.is_private(node("OnLoad", "protected"))
    assert csharp.is_private(node("Plain"))
    assert not csharp.is_private(node("_odd", "public"))
    assert csharp.is_private(_definition("Plain"))


def test_csharp_surface_is_the_public_types_inside_the_namespace(tmp_path):
    """A file's types sit inside a namespace node; the namespace is a
    grouping, not an export, and the default walk looks through it
    (SURFACE_CONTAINER_TYPES). Block-scoped and file-scoped alike."""
    (tmp_path / "Lib.cs").write_text(
        "namespace MyApp.Core\n{\n"
        "    public interface IApi { string Name(); }\n"
        '    internal class Impl : IApi { public string Name() => "x"; }\n'
        "    public class Widget { private int _count; }\n"
        "}\n"
    )
    (tmp_path / "Scoped.cs").write_text(
        "namespace MyApp.Core;\n\npublic record Token(string Value);\nclass Hidden {}\n"
    )
    names = [(e.name, e.kind, e.module) for e in read_surface(str(tmp_path)).exports]
    assert names == [
        ("MyApp.Core.IApi", "interface", "Lib"),
        ("MyApp.Core.Widget", "class", "Lib"),
        # a file-scoped `namespace X;` has no block, so the handler yields the
        # declarations as siblings, not members: bare here (handler candidate)
        ("Token", "record", "Scoped"),
    ]
    assert not BaseLanguage.SURFACE_CONTAINER_TYPES
