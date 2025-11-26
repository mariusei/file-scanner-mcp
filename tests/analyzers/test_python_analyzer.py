"""Tests for Python analyzer."""

import pytest
from scantool.analyzers.python_analyzer import PythonAnalyzer
from scantool.analyzers.models import ImportInfo, EntryPointInfo, DefinitionInfo, CallInfo


@pytest.fixture
def analyzer():
    """Create Python analyzer instance."""
    return PythonAnalyzer()


def test_extensions(analyzer):
    """Test that Python analyzer supports correct extensions."""
    extensions = analyzer.get_extensions()
    assert ".py" in extensions
    assert ".pyw" in extensions


def test_language_name(analyzer):
    """Test language name."""
    assert analyzer.get_language_name() == "Python"


def test_extract_imports_from_import(analyzer):
    """Test extraction of 'from X import Y' statements."""
    content = """
from os import path
from collections import defaultdict, Counter
from pathlib import Path
"""
    imports = analyzer.extract_imports("test.py", content)

    assert len(imports) == 3
    assert any(imp.target_module == "os" and "path" in imp.imported_names for imp in imports)
    assert any(imp.target_module == "collections" for imp in imports)
    assert any(imp.target_module == "pathlib" for imp in imports)


def test_extract_imports_simple_import(analyzer):
    """Test extraction of 'import X' statements."""
    content = """
import os
import sys
import pathlib
"""
    imports = analyzer.extract_imports("test.py", content)

    assert len(imports) == 3
    assert any(imp.target_module == "os" for imp in imports)
    assert any(imp.target_module == "sys" for imp in imports)
    assert any(imp.target_module == "pathlib" for imp in imports)


def test_extract_imports_relative(analyzer):
    """Test extraction of relative imports."""
    content = """
from . import utils
from ..core import scanner
from ...base import config
"""
    imports = analyzer.extract_imports("src/foo/bar.py", content)

    assert len(imports) == 3
    # All should be marked as relative
    assert all(imp.import_type == "relative" for imp in imports)


def test_find_entry_points_main_function(analyzer):
    """Test detection of main() function."""
    content = """
def main():
    pass

def helper():
    pass
"""
    entry_points = analyzer.find_entry_points("test.py", content)

    main_entries = [ep for ep in entry_points if ep.type == "main_function"]
    assert len(main_entries) == 1
    assert main_entries[0].name == "main"


def test_find_entry_points_if_main(analyzer):
    """Test detection of if __name__ == '__main__' blocks."""
    content = """
if __name__ == "__main__":
    main()
"""
    entry_points = analyzer.find_entry_points("test.py", content)

    if_main_entries = [ep for ep in entry_points if ep.type == "if_main"]
    assert len(if_main_entries) == 1
    assert if_main_entries[0].name == "__main__"


def test_find_entry_points_app_instances(analyzer):
    """Test detection of Flask/FastAPI app instances."""
    content = """
from flask import Flask
app = Flask(__name__)

from fastapi import FastAPI
server = FastAPI()
"""
    entry_points = analyzer.find_entry_points("test.py", content)

    app_entries = [ep for ep in entry_points if ep.type == "app_instance"]
    assert len(app_entries) == 2
    assert any(ep.framework == "Flask" and ep.name == "app" for ep in app_entries)
    assert any(ep.framework == "FastAPI" and ep.name == "server" for ep in app_entries)


def test_find_entry_points_exports(analyzer):
    """Test detection of __all__ exports in __init__.py."""
    content = """
__all__ = ["Foo", "Bar", "Baz"]

from .module import Something
"""
    entry_points = analyzer.find_entry_points("__init__.py", content)

    export_entries = [ep for ep in entry_points if ep.type == "export"]
    assert len(export_entries) == 2  # __all__ + re-export


def test_classify_file_entry_point(analyzer):
    """Test file classification for entry points."""
    content = """
def main():
    pass

if __name__ == "__main__":
    main()
"""
    cluster = analyzer.classify_file("server.py", content)
    assert cluster == "entry_points"


def test_classify_file_test(analyzer):
    """Test file classification for tests."""
    content = """
import pytest

def test_something():
    pass
"""
    cluster = analyzer.classify_file("test_foo.py", content)
    assert cluster == "tests"


def test_classify_file_utility(analyzer):
    """Test file classification for utilities."""
    content = """
def helper_function():
    pass

def util_process():
    pass
"""
    cluster = analyzer.classify_file("utils.py", content)
    assert cluster == "utilities"


def test_extract_definitions_classes(analyzer):
    """Test extraction of class definitions."""
    content = """
class Foo:
    pass

class Bar(BaseClass):
    pass
"""
    definitions = analyzer.extract_definitions("test.py", content)

    classes = [d for d in definitions if d.type == "class"]
    assert len(classes) == 2
    assert any(d.name == "Foo" for d in classes)
    assert any(d.name == "Bar" for d in classes)


def test_extract_definitions_functions(analyzer):
    """Test extraction of function definitions."""
    content = """
def foo():
    pass

def bar(x, y):
    return x + y
"""
    definitions = analyzer.extract_definitions("test.py", content)

    functions = [d for d in definitions if d.type == "function"]
    assert len(functions) == 2
    assert any(d.name == "foo" for d in functions)
    assert any(d.name == "bar" for d in functions)


def test_extract_definitions_methods(analyzer):
    """Test extraction of method definitions within classes."""
    content = """
class Foo:
    def method1(self):
        pass

    def method2(self, arg):
        pass
"""
    definitions = analyzer.extract_definitions("test.py", content)

    # Should have 1 class + 2 methods
    classes = [d for d in definitions if d.type == "class"]
    methods = [d for d in definitions if d.type == "method"]

    assert len(classes) == 1
    assert len(methods) == 2
    assert all(m.parent == "Foo" for m in methods)


def test_extract_calls_simple(analyzer):
    """Test extraction of simple function calls."""
    content = """
def caller():
    foo()
    bar()
    baz()
"""
    # First extract definitions
    definitions = analyzer.extract_definitions("test.py", content)

    # Then extract calls
    calls = analyzer.extract_calls("test.py", content, definitions)

    # Should find calls to foo, bar, baz
    assert len(calls) >= 3
    assert any(c.callee_name == "foo" for c in calls)
    assert any(c.callee_name == "bar" for c in calls)
    assert any(c.callee_name == "baz" for c in calls)


def test_extract_calls_cross_file(analyzer):
    """Test marking of cross-file calls."""
    content = """
def local_func():
    pass

def caller():
    local_func()  # Same file
    external_func()  # Different file
"""
    definitions = analyzer.extract_definitions("test.py", content)
    calls = analyzer.extract_calls("test.py", content, definitions)

    # Find the two specific calls
    local_call = next((c for c in calls if c.callee_name == "local_func"), None)
    external_call = next((c for c in calls if c.callee_name == "external_func"), None)

    if local_call:
        assert local_call.is_cross_file == False
    if external_call:
        assert external_call.is_cross_file == True


def test_should_analyze_normal_file(analyzer):
    """Test that normal files should be analyzed."""
    assert analyzer.should_analyze("module.py") == True


def test_should_analyze_pycache(analyzer):
    """Test that __pycache__ files should be skipped."""
    assert analyzer.should_analyze("__pycache__/foo.pyc") == False
