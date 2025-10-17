"""Tests for Ruby scanner."""

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner):
    """Test basic Ruby file parsing."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")
    assert structures is not None, "Should parse Ruby file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected structures
    assert any(s.type == "module" and s.name == "DataAccess" for s in structures)
    assert any(s.type == "class" and s.name == "UserService" for s in structures)
    assert any(s.type == "method" and s.name == "validate_email" for s in structures)


def test_modules(file_scanner):
    """Test that modules are extracted correctly."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")

    # Find DataAccess module
    module = next((s for s in structures if s.type == "module" and s.name == "DataAccess"), None)
    assert module is not None, "Should find DataAccess module"
    assert module.docstring is not None, "Should have docstring"

    # Check for nested class
    assert len(module.children) > 0, "Module should have children"
    db_class = next((c for c in module.children if c.type == "class" and c.name == "DatabaseManager"), None)
    assert db_class is not None, "Should find DatabaseManager class inside module"


def test_classes(file_scanner):
    """Test class extraction with inheritance."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")

    # Find DataAccess module first
    module = next((s for s in structures if s.type == "module" and s.name == "DataAccess"), None)
    assert module is not None, "Should find DataAccess module"

    # Find DatabaseManager class inside module
    db_class = next((c for c in module.children if c.type == "class" and c.name == "DatabaseManager"), None)
    assert db_class is not None, "Should find DatabaseManager class"
    assert db_class.docstring is not None, "Should have docstring"
    assert "database" in db_class.docstring.lower(), f"Docstring should mention database, got: {db_class.docstring}"


def test_class_methods(file_scanner):
    """Test that class methods (singleton methods) are extracted."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")

    # Find DataAccess module
    module = next((s for s in structures if s.type == "module" and s.name == "DataAccess"), None)
    assert module is not None, "Should find DataAccess module"

    # Find DatabaseManager class
    db_class = next((c for c in module.children if c.type == "class" and c.name == "DatabaseManager"), None)
    assert db_class is not None, "Should find DatabaseManager class"

    # Find class method
    class_method = next((m for m in db_class.children if "self.create_default" in m.name), None)
    assert class_method is not None, "Should find self.create_default class method"
    assert class_method.modifiers and "class" in class_method.modifiers, "Should have 'class' modifier"


def test_instance_methods(file_scanner):
    """Test instance method extraction."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")

    # Find UserService class
    user_class = next((s for s in structures if s.type == "class" and s.name == "UserService"), None)
    assert user_class is not None, "Should find UserService class"

    # Check for instance methods
    assert len(user_class.children) > 0, "Class should have methods"

    # Find create_user method
    create_method = next((m for m in user_class.children if m.name == "create_user"), None)
    assert create_method is not None, "Should find create_user method"
    assert create_method.type == "method", "Should be a method"


def test_signatures(file_scanner):
    """Test that method signatures are extracted correctly."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")

    # Find validate_email function
    func = next((s for s in structures if s.type == "method" and s.name == "validate_email"), None)
    assert func is not None, "Should find validate_email"
    assert func.signature is not None, "Should have signature"
    assert "(email)" in func.signature, f"Signature should include parameter, got: {func.signature}"


def test_comments(file_scanner):
    """Test that comments above declarations are extracted as docstrings."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")

    # Find validate_email function
    func = next((s for s in structures if s.type == "method" and s.name == "validate_email"), None)
    assert func is not None, "Should find validate_email"
    assert func.docstring is not None, "Should have docstring from comment"
    assert "email" in func.docstring.lower(), f"Docstring should mention email, got: {func.docstring}"


def test_requires(file_scanner):
    """Test that require statements are grouped."""
    structures = file_scanner.scan_file("tests/ruby/samples/basic.rb")

    # Find require group
    requires = next((s for s in structures if s.type == "requires"), None)
    assert requires is not None, "Should find require statements group"


def test_edge_cases(file_scanner):
    """Test edge cases like nested classes, singleton methods, etc."""
    structures = file_scanner.scan_file("tests/ruby/samples/edge_cases.rb")

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    # Test nested classes in modules
    outer_module = next((s for s in structures if s.type == "module" and s.name == "OuterModule"), None)
    assert outer_module is not None, "Should find OuterModule"
    assert len(outer_module.children) > 0, "Module should have nested structures"

    outer_class = next((c for c in outer_module.children if c.type == "class" and c.name == "OuterClass"), None)
    assert outer_class is not None, "Should find OuterClass"
    assert len(outer_class.children) > 0, "Should have nested classes"

    inner_class = next((c for c in outer_class.children if c.type == "class" and c.name == "InnerClass"), None)
    assert inner_class is not None, "Should find InnerClass"


def test_inheritance(file_scanner):
    """Test class inheritance detection."""
    structures = file_scanner.scan_file("tests/ruby/samples/edge_cases.rb")

    # Find ChildService class
    child = next((s for s in structures if s.type == "class" and s.name == "ChildService"), None)
    assert child is not None, "Should find ChildService class"
    assert child.signature is not None, "Should have signature showing inheritance"
    assert "BaseService" in child.signature, f"Signature should show parent class, got: {child.signature}"


def test_singleton_methods(file_scanner):
    """Test various singleton method patterns."""
    structures = file_scanner.scan_file("tests/ruby/samples/edge_cases.rb")

    # Find MultiSingleton class
    multi_singleton = next((s for s in structures if s.type == "class" and s.name == "MultiSingleton"), None)
    assert multi_singleton is not None, "Should find MultiSingleton class"

    # Check for singleton methods
    singleton_methods = [m for m in multi_singleton.children if m.modifiers and "class" in m.modifiers]
    assert len(singleton_methods) >= 2, "Should find multiple singleton methods"

    # Verify method names
    method_names = [m.name for m in singleton_methods]
    assert any("method_one" in name for name in method_names), "Should find method_one"
    assert any("method_two" in name for name in method_names), "Should find method_two"


def test_attr_accessor(file_scanner):
    """Test that classes with attr_accessor are parsed correctly."""
    structures = file_scanner.scan_file("tests/ruby/samples/edge_cases.rb")

    # Find MethodShowcase class
    showcase = next((s for s in structures if s.type == "class" and s.name == "MethodShowcase"), None)
    assert showcase is not None, "Should find MethodShowcase class"

    # The class should parse successfully even with attr_accessor
    assert showcase.type == "class", "Should be recognized as a class"


def test_complex_parameters(file_scanner):
    """Test methods with complex parameter lists."""
    structures = file_scanner.scan_file("tests/ruby/samples/edge_cases.rb")

    # Find complex_params method
    complex_method = next((s for s in structures if s.type == "method" and s.name == "complex_params"), None)
    assert complex_method is not None, "Should find complex_params method"
    assert complex_method.signature is not None, "Should have signature"


def test_deeply_nested_modules(file_scanner):
    """Test deeply nested module structures."""
    structures = file_scanner.scan_file("tests/ruby/samples/edge_cases.rb")

    # Find module A
    module_a = next((s for s in structures if s.type == "module" and s.name == "A"), None)
    assert module_a is not None, "Should find module A"

    # Should have nested module B
    module_b = next((c for c in module_a.children if c.type == "module" and c.name == "B"), None)
    assert module_b is not None, "Should find nested module B"

    # Should have nested module C
    module_c = next((c for c in module_b.children if c.type == "module" and c.name == "C"), None)
    assert module_c is not None, "Should find deeply nested module C"

    # Should have DeepClass inside module C
    deep_class = next((c for c in module_c.children if c.type == "class" and c.name == "DeepClass"), None)
    assert deep_class is not None, "Should find DeepClass in nested module"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)

    # Should not crash
    structures = scanner.scan_file("tests/ruby/samples/broken.rb")

    assert structures is not None, "Should return structures even for broken code"

    # Should show parse errors or valid structures
    has_error = any(s.type in ("parse-error", "error") for s in structures)
    has_valid = any(s.type in ("class", "method", "module") for s in structures)

    assert has_error or has_valid, "Should have either errors or valid structures"


def test_no_docstring_methods(file_scanner):
    """Test methods without docstrings."""
    structures = file_scanner.scan_file("tests/ruby/samples/edge_cases.rb")

    # Find methods without docstrings
    no_doc_1 = next((s for s in structures if s.type == "method" and s.name == "no_doc_1"), None)
    assert no_doc_1 is not None, "Should find no_doc_1 method"
    # Docstring can be None for methods without comments


def test_multi_line_comments(file_scanner):
    """Test multi-line comment extraction."""
    structures = file_scanner.scan_file("tests/ruby/samples/edge_cases.rb")

    # Find multi_line_comment function
    func = next((s for s in structures if s.type == "method" and s.name == "multi_line_comment"), None)
    assert func is not None, "Should find multi_line_comment method"
    # Scanner should extract at least one comment line


def test_method_visibility(file_scanner):
    """Test that private/protected methods are still extracted."""
    structures = file_scanner.scan_file("tests/ruby/samples/edge_cases.rb")

    # Find MethodShowcase class
    showcase = next((s for s in structures if s.type == "class" and s.name == "MethodShowcase"), None)
    assert showcase is not None, "Should find MethodShowcase class"

    # Should find private_method
    private_method = next((m for m in showcase.children if m.name == "private_method"), None)
    assert private_method is not None, "Should find private_method"

    # Should find protected_method
    protected_method = next((m for m in showcase.children if m.name == "protected_method"), None)
    assert protected_method is not None, "Should find protected_method"
