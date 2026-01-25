"""Tests for Python language."""

import pytest
from scantool.languages.python import PythonLanguage
from scantool.languages import ImportInfo, EntryPointInfo, DefinitionInfo, CallInfo


@pytest.fixture
def language():
    """Create language instance."""
    return PythonLanguage()


def test_extensions(language):
    """Test that Python analyzer supports correct extensions."""
    extensions = language.get_extensions()
    assert ".py" in extensions
    assert ".pyw" in extensions


def test_language_name(language):
    """Test language name."""
    assert language.get_language_name() == "Python"


def test_extract_imports_from_import(language):
    """Test extraction of 'from X import Y' statements."""
    content = """
from os import path
from collections import defaultdict, Counter
from pathlib import Path
"""
    imports = language.extract_imports("test.py", content)

    assert len(imports) == 3
    assert any(imp.target_module == "os" and "path" in imp.imported_names for imp in imports)
    assert any(imp.target_module == "collections" for imp in imports)
    assert any(imp.target_module == "pathlib" for imp in imports)


def test_extract_imports_simple_import(language):
    """Test extraction of 'import X' statements."""
    content = """
import os
import sys
import pathlib
"""
    imports = language.extract_imports("test.py", content)

    assert len(imports) == 3
    assert any(imp.target_module == "os" for imp in imports)
    assert any(imp.target_module == "sys" for imp in imports)
    assert any(imp.target_module == "pathlib" for imp in imports)


def test_extract_imports_relative(language):
    """Test extraction of relative imports."""
    content = """
from . import utils
from ..core import scanner
from ...base import config
"""
    imports = language.extract_imports("src/foo/bar.py", content)

    assert len(imports) == 3
    # All should be marked as relative
    assert all(imp.import_type == "relative" for imp in imports)


def test_find_entry_points_main_function(language):
    """Test detection of main() function."""
    content = """
def main():
    pass

def helper():
    pass
"""
    entry_points = language.find_entry_points("test.py", content)

    main_entries = [ep for ep in entry_points if ep.type == "main_function"]
    assert len(main_entries) == 1
    assert main_entries[0].name == "main"


def test_find_entry_points_if_main(language):
    """Test detection of if __name__ == '__main__' blocks."""
    content = """
if __name__ == "__main__":
    main()
"""
    entry_points = language.find_entry_points("test.py", content)

    if_main_entries = [ep for ep in entry_points if ep.type == "if_main"]
    assert len(if_main_entries) == 1
    assert if_main_entries[0].name == "__main__"


def test_find_entry_points_app_instances(language):
    """Test detection of Flask/FastAPI app instances."""
    content = """
from flask import Flask
app = Flask(__name__)

from fastapi import FastAPI
server = FastAPI()
"""
    entry_points = language.find_entry_points("test.py", content)

    app_entries = [ep for ep in entry_points if ep.type == "app_instance"]
    assert len(app_entries) == 2
    assert any(ep.framework == "Flask" and ep.name == "app" for ep in app_entries)
    assert any(ep.framework == "FastAPI" and ep.name == "server" for ep in app_entries)


def test_find_entry_points_exports(language):
    """Test detection of __all__ exports in __init__.py."""
    content = """
__all__ = ["Foo", "Bar", "Baz"]

from .module import Something
"""
    entry_points = language.find_entry_points("__init__.py", content)

    export_entries = [ep for ep in entry_points if ep.type == "export"]
    assert len(export_entries) == 2  # __all__ + re-export


def test_classify_file_entry_point(language):
    """Test file classification for entry points."""
    content = """
def main():
    pass

if __name__ == "__main__":
    main()
"""
    cluster = language.classify_file("server.py", content)
    assert cluster == "entry_points"


def test_classify_file_test(language):
    """Test file classification for tests."""
    content = """

def test_something():
    pass
"""
    cluster = language.classify_file("test_foo.py", content)
    assert cluster == "tests"


def test_classify_file_utility(language):
    """Test file classification for utilities."""
    content = """
def helper_function():
    pass

def util_process():
    pass
"""
    cluster = language.classify_file("utils.py", content)
    assert cluster == "utilities"


def test_extract_definitions_classes(language):
    """Test extraction of class definitions."""
    content = """
class Foo:
    pass

class Bar(BaseClass):
    pass
"""
    definitions = language.extract_definitions("test.py", content)

    classes = [d for d in definitions if d.type == "class"]
    assert len(classes) == 2
    assert any(d.name == "Foo" for d in classes)
    assert any(d.name == "Bar" for d in classes)


def test_extract_definitions_functions(language):
    """Test extraction of function definitions."""
    content = """
def foo():
    pass

def bar(x, y):
    return x + y
"""
    definitions = language.extract_definitions("test.py", content)

    functions = [d for d in definitions if d.type == "function"]
    assert len(functions) == 2
    assert any(d.name == "foo" for d in functions)
    assert any(d.name == "bar" for d in functions)


def test_extract_definitions_methods(language):
    """Test extraction of method definitions within classes."""
    content = """
class Foo:
    def method1(self):
        pass

    def method2(self, arg):
        pass
"""
    definitions = language.extract_definitions("test.py", content)

    # Should have 1 class + 2 methods
    classes = [d for d in definitions if d.type == "class"]
    methods = [d for d in definitions if d.type == "method"]

    assert len(classes) == 1
    assert len(methods) == 2
    assert all(m.parent == "Foo" for m in methods)


def test_extract_calls_simple(language):
    """Test extraction of simple function calls."""
    content = """
def caller():
    foo()
    bar()
    baz()
"""
    # First extract definitions
    definitions = language.extract_definitions("test.py", content)

    # Then extract calls
    calls = language.extract_calls("test.py", content, definitions)

    # Should find calls to foo, bar, baz
    assert len(calls) >= 3
    assert any(c.callee_name == "foo" for c in calls)
    assert any(c.callee_name == "bar" for c in calls)
    assert any(c.callee_name == "baz" for c in calls)


def test_extract_calls_cross_file(language):
    """Test marking of cross-file calls."""
    content = """
def local_func():
    pass

def caller():
    local_func()  # Same file
    external_func()  # Different file
"""
    definitions = language.extract_definitions("test.py", content)
    calls = language.extract_calls("test.py", content, definitions)

    # Find the two specific calls
    local_call = next((c for c in calls if c.callee_name == "local_func"), None)
    external_call = next((c for c in calls if c.callee_name == "external_func"), None)

    if local_call:
        assert local_call.is_cross_file == False
    if external_call:
        assert external_call.is_cross_file == True


def test_should_analyze_normal_file(language):
    """Test that normal files should be analyzed."""
    assert language.should_analyze("module.py") == True


def test_should_analyze_pycache(language):
    """Test that __pycache__ files should be skipped."""
    assert language.should_analyze("__pycache__/foo.pyc") == False
