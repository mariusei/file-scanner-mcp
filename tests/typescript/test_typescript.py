"""Tests for TypeScript and TSX scanner."""

import tempfile
import os
from pathlib import Path

from scantool.scanner import FileScanner


def test_basic_parsing(file_scanner, tree_formatter):
    """Test that TypeScript scanner can parse a basic .ts file."""
    file_path = Path(__file__).parent / "samples" / "basic.ts"

    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, f"Should parse {file_path}"
    assert len(structures) > 0, "Should find at least one structure"

    assert any(s.type == "interface" and s.name == "Config" for s in structures), \
        "Should find Config interface"

    assert any(s.type == "class" and s.name == "AuthService" for s in structures), \
        "Should find AuthService class"

    assert any(s.type == "class" and s.name == "UserManager" for s in structures), \
        "Should find UserManager class"

    assert any(s.type == "function" and s.name == "generateId" for s in structures), \
        "Should find generateId function"

    assert any(s.type == "function" and s.name == "validateEmail" for s in structures), \
        "Should find validateEmail function"


def test_tsx_parsing(file_scanner, tree_formatter):
    """Test that TypeScript scanner can parse TSX files with React components."""
    file_path = Path(__file__).parent / "samples" / "jsx.tsx"

    structures = file_scanner.scan_file(str(file_path))

    assert structures is not None, f"Should parse {file_path}"
    assert len(structures) > 0, "Should find at least one structure"

    assert any(s.type == "interface" and s.name == "UserCardProps" for s in structures), \
        "Should find UserCardProps interface"

    assert any(s.type == "interface" and s.name == "User" for s in structures), \
        "Should find User interface"

    has_user_card = any(s.type == "function" and "UserCard" in s.name for s in structures)
    assert has_user_card, "Should find UserCard component"

    assert any(s.type == "class" and s.name == "UserList" for s in structures), \
        "Should find UserList class component"

    assert any(s.type == "function" and s.name == "useUserData" for s in structures), \
        "Should find useUserData hook"


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

    auth_service = next((s for s in structures if s.type == "class" and s.name == "AuthService"), None)
    assert auth_service is not None, "Should find AuthService class"

    assert auth_service.docstring is not None, "Should have JSDoc comment"


def test_nested_structures(file_scanner):
    """Test that nested structures (methods in classes) work correctly."""
    file_path = Path(__file__).parent / "samples" / "basic.ts"
    structures = file_scanner.scan_file(str(file_path))

    auth_service = next((s for s in structures if s.type == "class" and s.name == "AuthService"), None)
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

    auth_service = next((s for s in structures if s.type == "class" and s.name == "AuthService"), None)
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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False) as f:
        f.write(malformed_code)
        temp_path = f.name

    try:
        structures = scanner.scan_file(temp_path)

        assert structures is not None, "Should return structures even for broken code"

        has_error = any(s.type in ("parse-error", "error") or "\u26a0" in s.name for s in structures)

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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False) as f:
        f.write(very_broken_code)
        temp_path = f.name

    try:
        structures = scanner.scan_file(temp_path)

        assert structures is not None, "Should return structures even for very broken code"

        fallback_used = any(
            "\u26a0" in s.name and s.type not in ("parse-error", "error")
            for s in structures
        )
        if fallback_used:
            has_class = any("SomewhatRecognizable" in s.name for s in structures)
            has_interface = any("AnotherOne" in s.name for s in structures)
            assert has_class or has_interface, "Fallback should extract some structures"

    finally:
        os.unlink(temp_path)
