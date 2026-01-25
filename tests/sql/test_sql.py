"""Tests for SQL scanner."""

from scantool.scanner import FileScanner
from conftest import validate_line_range_invariants


def test_basic_parsing(file_scanner):
    """Test basic SQL file parsing."""
    structures = file_scanner.scan_file("tests/sql/samples/basic.sql")
    assert structures is not None, "Should parse SQL file"
    assert len(structures) > 0, "Should find structures"

    # Verify expected structures
    assert any(s.type == "table" and s.name == "users" for s in structures)
    assert any(s.type == "table" and s.name == "products" for s in structures)
    assert any(s.type == "view" and s.name == "active_users" for s in structures)
    assert any(s.type == "function" and s.name == "calculate_discount" for s in structures)
    assert any(s.type == "index" and s.name == "idx_username" for s in structures)


def test_table_columns(file_scanner):
    """Test that table columns are extracted correctly."""
    structures = file_scanner.scan_file("tests/sql/samples/basic.sql")

    # Find users table
    users_table = next((s for s in structures if s.type == "table" and s.name == "users"), None)
    assert users_table is not None, "Should find users table"
    assert len(users_table.children) > 0, "Should have columns"

    # Check for specific columns
    column_names = [col.name for col in users_table.children]
    assert "id" in column_names, "Should have id column"
    assert "username" in column_names, "Should have username column"
    assert "email" in column_names, "Should have email column"

    # Check column types are in signature
    id_col = next((col for col in users_table.children if col.name == "id"), None)
    assert id_col is not None, "Should find id column"
    assert id_col.signature is not None, "Should have signature"
    assert "INT" in id_col.signature.upper(), f"Should have INT type, got: {id_col.signature}"


def test_view_signature(file_scanner):
    """Test that view queries are captured in signature."""
    structures = file_scanner.scan_file("tests/sql/samples/basic.sql")

    # Find active_users view
    view = next((s for s in structures if s.type == "view" and s.name == "active_users"), None)
    assert view is not None, "Should find active_users view"
    assert view.signature is not None, "Should have signature"
    assert "SELECT" in view.signature.upper(), f"Signature should contain SELECT, got: {view.signature}"


def test_function_signature(file_scanner):
    """Test that function signatures are extracted correctly."""
    structures = file_scanner.scan_file("tests/sql/samples/basic.sql")

    # Find calculate_discount function
    func = next((s for s in structures if s.type == "function" and s.name == "calculate_discount"), None)
    assert func is not None, "Should find calculate_discount function"
    assert func.signature is not None, "Should have signature"
    # Check for parameters and return type
    sig_upper = func.signature.upper()
    assert "DECIMAL" in sig_upper or "INT" in sig_upper, f"Should have parameter types, got: {func.signature}"
    assert "->" in func.signature, f"Should have return type indicator, got: {func.signature}"


def test_index_signature(file_scanner):
    """Test that index information is captured."""
    structures = file_scanner.scan_file("tests/sql/samples/basic.sql")

    # Find idx_username index
    index = next((s for s in structures if s.type == "index" and s.name == "idx_username"), None)
    assert index is not None, "Should find idx_username index"
    assert index.signature is not None, "Should have signature"
    assert "users" in index.signature.lower(), f"Should reference table, got: {index.signature}"


def test_comments_as_docstrings(file_scanner):
    """Test that comments are extracted as docstrings."""
    structures = file_scanner.scan_file("tests/sql/samples/basic.sql")

    # Find users table
    users_table = next((s for s in structures if s.type == "table" and s.name == "users"), None)
    assert users_table is not None, "Should find users table"
    assert users_table.docstring is not None, "Should have docstring from comment"
    assert "user" in users_table.docstring.lower(), f"Docstring should mention users, got: {users_table.docstring}"


def test_edge_cases(file_scanner):
    """Test edge cases like multi-line comments, complex types, etc."""
    structures = file_scanner.scan_file("tests/sql/samples/edge_cases.sql")

    assert structures is not None, "Should parse edge cases file"
    assert len(structures) > 0, "Should find structures"

    # Test multi-line comment as docstring
    orders_table = next((s for s in structures if s.type == "table" and s.name == "orders"), None)
    assert orders_table is not None, "Should find orders table"
    # Multi-line comments should be captured
    assert orders_table.docstring is not None, "Should have docstring from multi-line comment"

    # Test table with many data types
    data_types_table = next((s for s in structures if s.type == "table" and s.name == "data_types_test"), None)
    assert data_types_table is not None, "Should find data_types_test table"
    assert len(data_types_table.children) > 10, "Should have many columns with different types"

    # Test complex view
    order_summary = next((s for s in structures if s.type == "view" and s.name == "order_summary"), None)
    assert order_summary is not None, "Should find order_summary view"

    # Test function with multiple parameters
    get_user_total = next((s for s in structures if s.type == "function" and s.name == "get_user_total"), None)
    assert get_user_total is not None, "Should find get_user_total function"
    assert get_user_total.signature is not None, "Should have signature"


def test_error_handling():
    """Test that malformed SQL is handled without crashing."""
    scanner = FileScanner(show_errors=True)

    # Should not crash
    structures = scanner.scan_file("tests/sql/samples/broken.sql")

    assert structures is not None, "Should return structures even for broken code"

    # Should show parse errors or valid structures (fallback mode)
    has_error = any(s.type in ("parse-error", "error") for s in structures)
    has_valid = any(s.type in ("table", "view", "function") for s in structures)

    assert has_error or has_valid, "Should have either errors or valid structures"


def test_data_types(file_scanner):
    """Test various SQL data types in columns."""
    structures = file_scanner.scan_file("tests/sql/samples/edge_cases.sql")

    # Find data_types_test table
    table = next((s for s in structures if s.type == "table" and s.name == "data_types_test"), None)
    assert table is not None, "Should find data_types_test table"

    # Check various column types
    columns = {col.name: col for col in table.children}

    # INT types
    assert "col_int" in columns
    assert "col_bigint" in columns
    assert "col_smallint" in columns

    # Decimal/Float types
    assert "col_decimal" in columns
    assert "col_float" in columns
    assert "col_double" in columns

    # String types
    assert "col_char" in columns
    assert "col_varchar" in columns
    assert "col_text" in columns

    # Other types
    assert "col_blob" in columns
    assert "col_date" in columns
    assert "col_timestamp" in columns
    assert "col_boolean" in columns
    assert "col_json" in columns


def test_indexes(file_scanner):
    """Test different types of indexes."""
    structures = file_scanner.scan_file("tests/sql/samples/edge_cases.sql")

    # Should find multiple indexes
    indexes = [s for s in structures if s.type == "index"]
    assert len(indexes) >= 2, "Should find multiple indexes"

    # Find unique index
    unique_idx = next((idx for idx in indexes if "order_ref" in idx.name), None)
    assert unique_idx is not None, "Should find unique index"

    # Find composite index
    composite_idx = next((idx for idx in indexes if "status_date" in idx.name), None)
    assert composite_idx is not None, "Should find composite index"


def test_multiline_signatures(file_scanner):
    """Test that multi-line signatures are normalized."""
    structures = file_scanner.scan_file("tests/sql/samples/edge_cases.sql")

    # Find order_summary view (has multi-line query)
    view = next((s for s in structures if s.type == "view" and s.name == "order_summary"), None)
    assert view is not None, "Should find order_summary view"

    if view.signature:
        # Signature should be normalized (no internal newlines for display)
        # The actual query might be truncated or simplified
        assert "SELECT" in view.signature.upper(), "Should contain SELECT"


def test_function_return_types(file_scanner):
    """Test function return types are captured."""
    structures = file_scanner.scan_file("tests/sql/samples/edge_cases.sql")

    # Find get_user_total function
    func = next((s for s in structures if s.type == "function" and s.name == "get_user_total"), None)
    assert func is not None, "Should find get_user_total"
    assert func.signature is not None, "Should have signature"

    # Should have return type
    sig_upper = func.signature.upper()
    assert "->" in func.signature, f"Should indicate return type, got: {func.signature}"
    assert "DECIMAL" in sig_upper or "INT" in sig_upper, f"Should show return type, got: {func.signature}"


def test_line_range_invariants(file_scanner):
    """Test universal line range invariants for SQL scanner."""
    structures = file_scanner.scan_file("tests/sql/samples/basic.sql")
    validate_line_range_invariants(structures)

    # Also test edge cases file
    structures = file_scanner.scan_file("tests/sql/samples/edge_cases.sql")
    validate_line_range_invariants(structures)


def test_table_with_foreign_keys(file_scanner):
    """Test tables with foreign key constraints."""
    structures = file_scanner.scan_file("tests/sql/samples/edge_cases.sql")

    # Find orders table which has FOREIGN KEY
    orders = next((s for s in structures if s.type == "table" and s.name == "orders"), None)
    assert orders is not None, "Should find orders table"
    assert len(orders.children) > 0, "Should have columns"

    # Check that foreign key column is captured
    user_id_col = next((col for col in orders.children if col.name == "user_id"), None)
    assert user_id_col is not None, "Should find user_id column"


def test_postgresql_dialect_detection(file_scanner):
    """Test that PostgreSQL dialect is detected correctly."""
    from scantool.languages.sql import SQLLanguage

    scanner = SQLLanguage()

    # Test PostgreSQL file
    with open("tests/sql/samples/postgresql.sql", "rb") as f:
        pg_content = f.read()

    dialect = scanner._detect_dialect(pg_content)
    assert dialect == "postgresql", f"Should detect PostgreSQL, got: {dialect}"

    # Test generic SQL file
    with open("tests/sql/samples/basic.sql", "rb") as f:
        basic_content = f.read()

    dialect = scanner._detect_dialect(basic_content)
    assert dialect in ("mysql", "generic"), f"Should detect MySQL or generic, got: {dialect}"


def test_postgresql_do_blocks(file_scanner):
    """Test that PostgreSQL DO blocks are parsed correctly."""
    structures = file_scanner.scan_file("tests/sql/samples/postgresql.sql")

    # Should find DO blocks
    do_blocks = [s for s in structures if s.type == "do-block"]
    assert len(do_blocks) > 0, "Should find DO blocks"

    # Check that DO blocks have proper line ranges
    for block in do_blocks:
        assert block.start_line > 0, "DO block should have valid start line"
        assert block.end_line >= block.start_line, "DO block should have valid end line"


def test_postgresql_structures(file_scanner):
    """Test that PostgreSQL-specific structures are parsed."""
    structures = file_scanner.scan_file("tests/sql/samples/postgresql.sql")

    # Should find tables
    tables = [s for s in structures if s.type == "table"]
    assert len(tables) >= 2, "Should find at least 2 tables"

    # Check for partitioned table
    measurements = next((s for s in structures if s.type == "table" and s.name == "measurements"), None)
    assert measurements is not None, "Should find partitioned table 'measurements'"

    # Should find functions
    functions = [s for s in structures if s.type == "function"]
    assert len(functions) >= 1, "Should find at least 1 function"

    # Should find views
    views = [s for s in structures if s.type == "view"]
    assert len(views) >= 1, "Should find at least 1 view"

    # Should find indexes
    indexes = [s for s in structures if s.type == "index"]
    assert len(indexes) >= 1, "Should find at least 1 index"


def test_postgresql_no_parse_errors(file_scanner):
    """Test that PostgreSQL file parses without errors."""
    structures = file_scanner.scan_file("tests/sql/samples/postgresql.sql")

    # Should have no parse errors
    parse_errors = [s for s in structures if s.type in ("parse-error", "error")]
    assert len(parse_errors) == 0, f"Should have no parse errors, found: {parse_errors}"


def test_postgresql_line_range_invariants(file_scanner):
    """Test universal line range invariants for PostgreSQL scanner."""
    structures = file_scanner.scan_file("tests/sql/samples/postgresql.sql")
    validate_line_range_invariants(structures)
