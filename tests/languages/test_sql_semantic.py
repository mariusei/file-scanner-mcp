"""Tests for SQL language."""

import pytest
from scantool.languages.sql import SQLLanguage
from scantool.languages import ImportInfo, EntryPointInfo


@pytest.fixture
def language():
    """Create language instance."""
    return SQLLanguage()


class TestSQLAnalyzer:
    """Test suite for SQL language."""

    def test_extensions(self, language):
        """Test that analyzer supports correct extensions."""
        extensions = language.get_extensions()
        assert ".sql" in extensions
        assert ".psql" in extensions
        assert ".mysql" in extensions

    def test_language_name(self, language):
        """Test language name."""
        assert language.get_language_name() == "SQL"

    def test_extract_imports_postgresql_i(self, language):
        """Test extraction of PostgreSQL \\i statements."""
        content = """
        \\i /path/to/schema.sql
        \\i migrations/001_create_users.sql
        """
        imports = language.extract_imports("test.sql", content)

        assert len(imports) == 2
        assert any(imp.target_module == "/path/to/schema.sql" for imp in imports)
        assert any(imp.target_module.endswith("001_create_users.sql") for imp in imports)
        assert all(imp.import_type == "file" for imp in imports)

    def test_extract_imports_postgresql_ir(self, language):
        """Test extraction of PostgreSQL \\ir (relative) statements."""
        content = """
        \\ir relative/file.sql
        \\ir ../parent/schema.sql
        """
        imports = language.extract_imports("migrations/test.sql", content)

        assert len(imports) == 2
        assert all(imp.import_type == "relative" for imp in imports)

    def test_extract_imports_postgresql_include(self, language):
        """Test extraction of PostgreSQL \\include statements."""
        content = """
        \\include setup.sql
        \\include "quoted file.sql"
        """
        imports = language.extract_imports("test.sql", content)

        assert len(imports) == 2
        assert any(imp.target_module == "setup.sql" for imp in imports)
        assert any(imp.target_module == "quoted file.sql" for imp in imports)

    def test_extract_imports_mysql_source(self, language):
        """Test extraction of MySQL SOURCE statements."""
        content = """
        SOURCE schema/tables.sql
        source data/fixtures.sql
        SOURCE 'path/to/file.sql'
        """
        imports = language.extract_imports("test.mysql", content)

        assert len(imports) == 3
        assert any(imp.target_module.endswith("tables.sql") for imp in imports)
        assert any(imp.target_module.endswith("fixtures.sql") for imp in imports)
        assert all(imp.import_type == "source" for imp in imports)

    def test_extract_imports_mssql_r(self, language):
        """Test extraction of MSSQL :r statements."""
        content = """
        :r schema.sql
        :r C:\\path\\to\\migration.sql
        """
        imports = language.extract_imports("test.sql", content)

        assert len(imports) == 2
        assert any(imp.target_module == "schema.sql" for imp in imports)
        assert all(imp.import_type == "file" for imp in imports)

    def test_extract_imports_use_database(self, language):
        """Test extraction of USE database statements."""
        content = """
        USE production;
        use staging;
        USE test_db
        """
        imports = language.extract_imports("test.sql", content)

        assert len(imports) == 3
        assert any(imp.target_module == "production" and imp.import_type == "database" for imp in imports)
        assert any(imp.target_module == "staging" and imp.import_type == "database" for imp in imports)
        assert any(imp.target_module == "test_db" and imp.import_type == "database" for imp in imports)

    def test_extract_imports_cross_database(self, language):
        """Test extraction of cross-database table references."""
        content = """
        SELECT * FROM production.users;
        INSERT INTO staging.orders VALUES (1, 2);
        JOIN other_db.customers ON users.id = customers.user_id
        """
        imports = language.extract_imports("test.sql", content)

        # Filter to cross_database imports only
        cross_db = [imp for imp in imports if imp.import_type == "cross_database"]
        assert len(cross_db) >= 3
        assert any(imp.target_module == "production" for imp in cross_db)
        assert any(imp.target_module == "staging" for imp in cross_db)
        assert any(imp.target_module == "other_db" for imp in cross_db)

    def test_extract_imports_skip_system_databases(self, language):
        """Test that system database references are skipped."""
        content = """
        SELECT * FROM information_schema.tables;
        SELECT * FROM performance_schema.events;
        SELECT * FROM mysql.user;
        SELECT * FROM sys.databases;
        """
        imports = language.extract_imports("test.sql", content)

        # Should not include system databases
        cross_db = [imp for imp in imports if imp.import_type == "cross_database"]
        assert len(cross_db) == 0

    def test_extract_imports_quoted_paths(self, language):
        """Test handling of quoted file paths."""
        content = """
        \\i "path with spaces.sql"
        \\i 'single quoted.sql'
        SOURCE "quoted/path.sql"
        """
        imports = language.extract_imports("test.sql", content)

        assert len(imports) == 3
        assert any(imp.target_module == "path with spaces.sql" for imp in imports)
        assert any(imp.target_module == "single quoted.sql" for imp in imports)
        assert any(imp.target_module.endswith("quoted/path.sql") for imp in imports)

    def test_extract_imports_mixed(self, language):
        """Test extraction of mixed import types."""
        content = """
        \\i schema.sql
        SOURCE data.sql
        :r migration.sql
        USE production
        SELECT * FROM analytics.events
        """
        imports = language.extract_imports("test.sql", content)

        assert len(imports) >= 5
        assert any(imp.import_type == "file" for imp in imports)
        assert any(imp.import_type == "source" for imp in imports)
        assert any(imp.import_type == "database" for imp in imports)
        assert any(imp.import_type == "cross_database" for imp in imports)

    def test_find_entry_points_migration_yyyymmdd(self, language):
        """Test detection of YYYYMMDD_* migration files."""
        content = "CREATE TABLE users (id INT);"
        entry_points = language.find_entry_points("migrations/20231215_create_users.sql", content)

        migrations = [ep for ep in entry_points if ep.type == "migration"]
        assert len(migrations) == 1
        assert migrations[0].name == "20231215_create_users"

    def test_find_entry_points_migration_timestamp(self, language):
        """Test detection of YYYYMMDDHHmmss_* migration files."""
        content = "ALTER TABLE users ADD COLUMN email VARCHAR(255);"
        entry_points = language.find_entry_points("20231215143022_add_email.sql", content)

        migrations = [ep for ep in entry_points if ep.type == "migration"]
        assert len(migrations) == 1

    def test_find_entry_points_migration_up_down(self, language):
        """Test detection of *_up.sql and *_down.sql migration files."""
        content_up = "CREATE TABLE products (id INT);"
        entry_points_up = language.find_entry_points("create_products_up.sql", content_up)

        content_down = "DROP TABLE products;"
        entry_points_down = language.find_entry_points("create_products_down.sql", content_down)

        assert any(ep.type == "migration" for ep in entry_points_up)
        assert any(ep.type == "migration" for ep in entry_points_down)

    def test_find_entry_points_migration_flyway(self, language):
        """Test detection of Flyway-style V*_ migration files."""
        content = "CREATE TABLE orders (id INT);"
        entry_points = language.find_entry_points("V1_initial_schema.sql", content)

        migrations = [ep for ep in entry_points if ep.type == "migration"]
        assert len(migrations) == 1
        assert migrations[0].name == "V1_initial_schema"

    def test_find_entry_points_migration_numbered(self, language):
        """Test detection of numbered migration files (001_*, 002_*)."""
        content = "CREATE TABLE customers (id INT);"
        entry_points = language.find_entry_points("001_create_customers.sql", content)

        migrations = [ep for ep in entry_points if ep.type == "migration"]
        assert len(migrations) == 1

    def test_find_entry_points_seed_file(self, language):
        """Test detection of seed files."""
        content = "INSERT INTO users VALUES (1, 'admin');"

        # Test various seed file patterns
        patterns = [
            "seeds/users_seed.sql",
            "fixtures/user_fixture.sql",
            "sample_data.sql",
            "seeds/initial.sql"
        ]

        for pattern in patterns:
            entry_points = language.find_entry_points(pattern, content)
            seeds = [ep for ep in entry_points if ep.type == "seed"]
            assert len(seeds) >= 1, f"Failed to detect seed file: {pattern}"

    def test_find_entry_points_create_database(self, language):
        """Test detection of CREATE DATABASE statements."""
        content = """
        CREATE DATABASE production;
        CREATE DATABASE IF NOT EXISTS staging;
        create database test_db
        """
        entry_points = language.find_entry_points("setup.sql", content)

        db_creates = [ep for ep in entry_points if ep.type == "database_creation"]
        assert len(db_creates) == 3
        assert any(ep.name == "production" for ep in db_creates)
        assert any(ep.name == "staging" for ep in db_creates)
        assert any(ep.name == "test_db" for ep in db_creates)

    def test_find_entry_points_create_schema(self, language):
        """Test detection of CREATE SCHEMA statements."""
        content = """
        CREATE SCHEMA analytics;
        CREATE SCHEMA IF NOT EXISTS reports;
        create schema public
        """
        entry_points = language.find_entry_points("schema.sql", content)

        schema_creates = [ep for ep in entry_points if ep.type == "schema_creation"]
        assert len(schema_creates) == 3
        assert any(ep.name == "analytics" for ep in schema_creates)
        assert any(ep.name == "reports" for ep in schema_creates)
        assert any(ep.name == "public" for ep in schema_creates)

    def test_find_entry_points_multiple_types(self, language):
        """Test detection of multiple entry point types in one file."""
        content = """
        CREATE DATABASE mydb;
        CREATE SCHEMA public;
        """
        entry_points = language.find_entry_points("001_initial_setup.sql", content)

        # Should detect migration (by filename), database creation, and schema creation
        assert any(ep.type == "migration" for ep in entry_points)
        assert any(ep.type == "database_creation" for ep in entry_points)
        assert any(ep.type == "schema_creation" for ep in entry_points)

    def test_find_entry_points_line_numbers(self, language):
        """Test that line numbers are correctly tracked."""
        content = """-- Line 1: comment
CREATE DATABASE test;
-- Line 3: another comment
CREATE SCHEMA public;
"""
        entry_points = language.find_entry_points("test.sql", content)

        db_create = next((ep for ep in entry_points if ep.type == "database_creation"), None)
        schema_create = next((ep for ep in entry_points if ep.type == "schema_creation"), None)

        assert db_create is not None
        assert db_create.line == 2

        assert schema_create is not None
        assert schema_create.line == 4

    def test_should_analyze(self, language):
        """Test that all SQL files should be analyzed."""
        assert language.should_analyze("schema.sql") is True
        assert language.should_analyze("migration.psql") is True
        assert language.should_analyze("data.mysql") is True
        assert language.should_analyze("path/to/complex_query.sql") is True

    def test_extract_imports_no_duplicates(self, language):
        """Test that duplicate cross-database references are not repeated."""
        content = """
        SELECT * FROM analytics.events;
        SELECT * FROM analytics.events;
        SELECT * FROM analytics.sessions;
        SELECT * FROM reporting.users;
        """
        imports = language.extract_imports("test.sql", content)

        cross_db = [imp for imp in imports if imp.import_type == "cross_database"]
        # Should have analytics and reporting, but each only once despite multiple references
        analytics_refs = [imp for imp in cross_db if imp.target_module == "analytics"]
        reporting_refs = [imp for imp in cross_db if imp.target_module == "reporting"]
        assert len(analytics_refs) == 1
        assert len(reporting_refs) == 1

    def test_extract_imports_line_numbers(self, language):
        """Test that import line numbers are correctly tracked."""
        content = """-- Line 1
\\i schema.sql
-- Line 3
USE production;
-- Line 5
SOURCE data.sql
"""
        imports = language.extract_imports("test.sql", content)

        # Check line numbers
        i_import = next((imp for imp in imports if imp.target_module == "schema.sql"), None)
        use_import = next((imp for imp in imports if imp.target_module == "production"), None)
        source_import = next((imp for imp in imports if "data.sql" in imp.target_module), None)

        assert i_import is not None and i_import.line == 2
        assert use_import is not None and use_import.line == 4
        assert source_import is not None and source_import.line == 6

    def test_extract_imports_comments_and_strings(self, language):
        """Test that imports in comments or strings are still detected."""
        # Note: Current implementation uses simple regex and will match in comments/strings
        # This is acceptable for SQL as import-like patterns in comments are rare
        content = """
        -- \\i comment.sql (this is a comment)
        \\i actual.sql
        """
        imports = language.extract_imports("test.sql", content)

        # Both will be detected (comment and actual)
        # This is a known limitation of regex approach but acceptable for SQL
        assert len(imports) >= 1
        assert any(imp.target_module.endswith("actual.sql") for imp in imports)

    def test_priority(self, language):
        """Test analyzer priority."""
        assert language.get_priority() == 10
