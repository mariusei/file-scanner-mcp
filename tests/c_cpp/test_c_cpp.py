"""Tests for C/C++ scanner."""

from scantool.scanner import FileScanner


def test_c_parsing(file_scanner):
    """Test basic C file parsing."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/basic.c")
    assert structures is not None, "Should parse C file"
    assert len(structures) > 0, "Should find structures"

    # Verify includes
    assert any(s.type == "includes" for s in structures), "Should find includes"

    # Verify structs
    assert any(s.type == "struct" and s.name == "User" for s in structures), "Should find User struct"
    assert any(s.type == "struct" and s.name == "DatabaseConfig" for s in structures), "Should find DatabaseConfig struct"

    # Verify functions
    assert any(s.type == "function" and s.name == "init_user" for s in structures), "Should find init_user"
    assert any(s.type == "function" and s.name == "validate_email" for s in structures), "Should find validate_email"
    assert any(s.type == "function" and s.name == "main" for s in structures), "Should find main"

    # Verify enum
    assert any(s.type == "enum" and s.name == "Status" for s in structures), "Should find Status enum"


def test_cpp_parsing(file_scanner):
    """Test basic C++ file parsing."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/basic.cpp")
    assert structures is not None, "Should parse C++ file"
    assert len(structures) > 0, "Should find structures"

    # Verify includes
    assert any(s.type == "includes" for s in structures), "Should find includes"

    # Verify namespaces
    assert any(s.type == "namespace" and s.name == "utils" for s in structures), "Should find utils namespace"
    assert any(s.type == "namespace" and s.name == "database" for s in structures), "Should find database namespace"

    # Helper to find recursively
    def find_recursive(structures, type_name, name):
        for s in structures:
            if s.type == type_name and s.name == name:
                return True
            if find_recursive(s.children, type_name, name):
                return True
        return False

    # Verify classes (may be inside namespaces)
    assert find_recursive(structures, "class", "DatabaseManager"), "Should find DatabaseManager class"
    assert any(s.type == "class" and s.name == "UserService" for s in structures), "Should find UserService class"

    # Verify enum
    assert any(s.type == "enum" and s.name == "Status" for s in structures), "Should find Status enum"

    # Verify functions
    assert any(s.type == "function" and s.name == "main" for s in structures), "Should find main"


def test_classes(file_scanner):
    """Test C++ class detection and structure."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/basic.cpp")

    # Helper to find recursively
    def find_node_recursive(structures, type_name, name):
        for s in structures:
            if s.type == type_name and s.name == name:
                return s
            result = find_node_recursive(s.children, type_name, name)
            if result:
                return result
        return None

    # Find DatabaseManager class (inside namespace)
    db_class = find_node_recursive(structures, "class", "DatabaseManager")
    assert db_class is not None, "Should find DatabaseManager class"
    assert len(db_class.children) > 0, "Should have methods"

    # Find UserService class (top-level)
    user_class = next((s for s in structures if s.type == "class" and s.name == "UserService"), None)
    assert user_class is not None, "Should find UserService class"
    assert len(user_class.children) > 0, "Should have methods"


def test_namespaces(file_scanner):
    """Test C++ namespace detection."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/basic.cpp")

    # Find utils namespace
    utils_ns = next((s for s in structures if s.type == "namespace" and s.name == "utils"), None)
    assert utils_ns is not None, "Should find utils namespace"
    assert len(utils_ns.children) > 0, "Should have content in namespace"

    # Find database namespace
    db_ns = next((s for s in structures if s.type == "namespace" and s.name == "database"), None)
    assert db_ns is not None, "Should find database namespace"
    assert len(db_ns.children) > 0, "Should have content in namespace"

    # Check that DatabaseManager is inside database namespace
    db_manager = next((c for c in db_ns.children if c.type == "class" and c.name == "DatabaseManager"), None)
    assert db_manager is not None, "Should find DatabaseManager inside database namespace"


def test_signatures(file_scanner):
    """Test function signature extraction."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/basic.c")

    # Find validate_email function
    func = next((s for s in structures if s.type == "function" and s.name == "validate_email"), None)
    assert func is not None, "Should find validate_email"
    assert func.signature is not None, "Should have signature"
    assert "(const char *email)" in func.signature, f"Signature should include parameters, got: {func.signature}"


def test_cpp_signatures(file_scanner):
    """Test C++ signature extraction with types."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/basic.cpp")

    # Find database namespace
    db_ns = next((s for s in structures if s.type == "namespace" and s.name == "database"), None)
    assert db_ns is not None, "Should find database namespace"

    # Find DatabaseManager class
    db_class = next((c for c in db_ns.children if c.type == "class" and c.name == "DatabaseManager"), None)
    assert db_class is not None, "Should find DatabaseManager class"

    # Find connect method
    connect_method = next((c for c in db_class.children if c.name == "connect"), None)
    assert connect_method is not None, "Should find connect method"
    assert connect_method.signature is not None, "Should have signature"


def test_header_parsing(file_scanner):
    """Test header file parsing."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/basic.h")
    assert structures is not None, "Should parse header file"
    assert len(structures) > 0, "Should find structures"

    # Helper to find recursively
    def find_recursive(structures, type_name, name):
        for s in structures:
            if s.type == type_name and s.name == name:
                return True
            if find_recursive(s.children, type_name, name):
                return True
        return False

    # Verify namespaces
    assert any(s.type == "namespace" and s.name == "utils" for s in structures), "Should find utils namespace"
    assert any(s.type == "namespace" and s.name == "database" for s in structures), "Should find database namespace"

    # Verify classes (may be inside namespaces)
    assert find_recursive(structures, "class", "IConnection"), "Should find IConnection interface"
    assert find_recursive(structures, "class", "DatabaseManager"), "Should find DatabaseManager class"
    assert any(s.type == "class" and s.name == "UserService" for s in structures), "Should find UserService class"

    # Verify structs
    assert any(s.type == "struct" and s.name == "UserData" for s in structures), "Should find UserData struct"

    # Verify enums
    assert any(s.type == "enum" and s.name == "Status" for s in structures), "Should find Status enum"
    assert any(s.type == "enum" and s.name == "Permission" for s in structures), "Should find Permission enum"


def test_edge_cases(file_scanner):
    """Test edge cases like templates, operator overloading, etc."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/edge_cases.cpp")
    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    # Test template classes
    kv_store = next((s for s in structures if s.type == "class" and s.name == "KeyValueStore"), None)
    assert kv_store is not None, "Should find KeyValueStore template class"
    assert "template" in kv_store.modifiers if kv_store.modifiers else False, "Should have template modifier"

    # Test operator overloading class
    complex_class = next((s for s in structures if s.type == "class" and s.name == "Complex"), None)
    assert complex_class is not None, "Should find Complex class"
    assert len(complex_class.children) > 0, "Should have methods including operators"

    # Test const methods class
    cache_class = next((s for s in structures if s.type == "class" and s.name == "DataCache"), None)
    assert cache_class is not None, "Should find DataCache class"
    # Check for const methods
    const_methods = [m for m in cache_class.children if m.modifiers and "const" in m.modifiers]
    assert len(const_methods) > 0, "Should have const methods"

    # Test virtual methods (abstract class)
    shape_class = next((s for s in structures if s.type == "class" and s.name == "Shape"), None)
    assert shape_class is not None, "Should find Shape class"
    # Check for virtual methods
    virtual_methods = [m for m in shape_class.children if m.modifiers and "virtual" in m.modifiers]
    assert len(virtual_methods) > 0, "Should have virtual methods"

    # Test derived class
    circle_class = next((s for s in structures if s.type == "class" and s.name == "Circle"), None)
    assert circle_class is not None, "Should find Circle class"
    assert circle_class.signature is not None, "Should have base class info"
    assert "Shape" in circle_class.signature, "Should show inheritance from Shape"

    # Test static methods
    counter_class = next((s for s in structures if s.type == "class" and s.name == "Counter"), None)
    assert counter_class is not None, "Should find Counter class"
    static_methods = [m for m in counter_class.children if m.modifiers and "static" in m.modifiers]
    assert len(static_methods) > 0, "Should have static methods"

    # Test nested namespaces
    outer_ns = next((s for s in structures if s.type == "namespace" and s.name == "outer"), None)
    assert outer_ns is not None, "Should find outer namespace"
    inner_ns = next((c for c in outer_ns.children if c.type == "namespace" and c.name == "inner"), None)
    assert inner_ns is not None, "Should find inner namespace inside outer"

    # Test anonymous namespace
    anon_ns = next((s for s in structures if s.type == "namespace" and s.name == "<anonymous>"), None)
    assert anon_ns is not None, "Should find anonymous namespace"


def test_comments(file_scanner):
    """Test comment extraction."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/basic.c")

    # Find User struct
    user_struct = next((s for s in structures if s.type == "struct" and s.name == "User"), None)
    assert user_struct is not None, "Should find User struct"
    assert user_struct.docstring is not None, "Should have docstring from comment"
    assert "User" in user_struct.docstring, f"Comment should mention User, got: {user_struct.docstring}"


def test_error_handling():
    """Test that malformed code is handled without crashing."""
    scanner = FileScanner(show_errors=True)

    # Create a test file with broken syntax
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
        f.write("""
        class BrokenClass {
            // Missing semicolon, broken syntax
            void method(
        """)
        temp_file = f.name

    try:
        # Should not crash
        structures = scanner.scan_file(temp_file)
        assert structures is not None, "Should return structures even for broken code"
    finally:
        os.unlink(temp_file)


def test_modifiers(file_scanner):
    """Test modifier extraction (static, const, virtual, etc.)."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/edge_cases.cpp")

    # Find Counter class for static methods
    counter_class = next((s for s in structures if s.type == "class" and s.name == "Counter"), None)
    assert counter_class is not None, "Should find Counter class"

    # Find static method
    static_method = next((m for m in counter_class.children
                         if m.modifiers and "static" in m.modifiers), None)
    assert static_method is not None, "Should find static method"

    # Find DataCache class for const methods
    cache_class = next((s for s in structures if s.type == "class" and s.name == "DataCache"), None)
    assert cache_class is not None, "Should find DataCache class"

    # Find const method
    const_method = next((m for m in cache_class.children
                        if m.modifiers and "const" in m.modifiers), None)
    assert const_method is not None, "Should find const method"


def test_includes(file_scanner):
    """Test include directive grouping."""
    structures = file_scanner.scan_file("tests/c_cpp/samples/basic.cpp")

    # Should have an includes group
    includes = next((s for s in structures if s.type == "includes"), None)
    assert includes is not None, "Should find includes group"
    assert includes.start_line > 0, "Should have valid start line"
    assert includes.end_line >= includes.start_line, "End line should be >= start line"
