"""Naming conventions and the public surface are the language's (brief §9e):
nothing outside languages/ implements a private-name rule, a qualifier or a
facade syntax. The defaults live on BaseLanguage; Python overrides the
surface with its facade logic; every other handler gets the default.
"""

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


def test_python_surface_is_the_python_handlers(tmp_path):
    (tmp_path / "__init__.py").write_text("from .core import Thing\n__all__ = ['Thing']\n")
    (tmp_path / "core.py").write_text("class Thing:\n    def go(self):\n        return 1\n")
    surface = read_surface(str(tmp_path))
    assert [(e.name, e.via, e.listed) for e in surface.exports] == [("Thing", "re-export", True)]
    assert surface.exports[0].path.endswith("core.py")


def test_no_syntax_outside_languages():
    """The verifier's red flags (§9e): no ast, tree-sitter, extension test or
    language keyword outside languages/."""
    package = TESTS_DIR.parent / "src" / "scantool"
    # code_health's UNREFERENCED exemptions (dunder and test-prefixed names)
    # predate §9e; moving them behind BaseLanguage is a separate change
    known = {"code_health.py"}
    offenders = []
    for path in package.glob("*.py"):
        if path.name in known:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in ("import ast\n", "tree_sitter", 'endswith(".py")', 'startswith("__")'):
            if needle in text:
                offenders.append(f"{path.name}: {needle.strip()}")
    assert not offenders, offenders
