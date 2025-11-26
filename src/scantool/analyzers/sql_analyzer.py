"""Analyzer for SQL source files (.sql, .psql, .mysql)."""

import re
from pathlib import Path
from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class SQLAnalyzer(BaseAnalyzer):
    r"""Analyzer for SQL source files (.sql, .psql, .mysql)."""

    # ===================================================================
    # REQUIRED: Metadata
    # ===================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        """File extensions for SQL."""
        return [".sql", ".psql", ".mysql"]

    @classmethod
    def get_language_name(cls) -> str:
        """Language name."""
        return "SQL"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority (0 = default, higher = preferred)."""
        return 10

    # ===================================================================
    # OPTIONAL: Skip patterns (Tier 2)
    # ===================================================================

    def should_analyze(self, file_path: str) -> bool:
        """
        SQL files don't have common generated/minified patterns to skip.
        All .sql files should be analyzed.
        """
        return True

    # ===================================================================
    # REQUIRED: Layer 1 - File-level analysis
    # ===================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        r"""
        Extract imports from SQL file.

        Supports:
        - PostgreSQL: \i file.sql, \ir relative/file.sql, \include file.sql
        - MySQL: SOURCE file.sql, source file.sql
        - MSSQL: :r file.sql
        - Cross-database: USE database_name, database.table references
        """
        imports = []

        # PostgreSQL: \i and \ir (relative) and \include
        # \i /path/to/file.sql
        # \ir relative/file.sql
        # \include file.sql
        # Support quoted paths: \i "path with spaces.sql" or \i 'path.sql'
        pg_pattern = r'^\s*\\(i|ir|include)\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s;]+))'
        for match in re.finditer(pg_pattern, content, re.MULTILINE):
            command = match.group(1)
            # Try to get the path from any of the three capture groups
            target_file = match.group(2) or match.group(3) or match.group(4)
            if not target_file:
                continue

            line = content[:match.start()].count('\n') + 1

            # \ir is relative, others can be absolute or relative
            import_type = "relative" if command == "ir" else "file"

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=target_file,
                import_type=import_type,
                line=line
            ))

        # MySQL: SOURCE file.sql (case-insensitive)
        # Support quoted paths: SOURCE "path with spaces.sql" or SOURCE 'path.sql'
        mysql_pattern = r'^\s*source\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s;]+))'
        for match in re.finditer(mysql_pattern, content, re.MULTILINE | re.IGNORECASE):
            # Try to get the path from any of the three capture groups
            target_file = match.group(1) or match.group(2) or match.group(3)
            if not target_file:
                continue

            line = content[:match.start()].count('\n') + 1

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=target_file,
                import_type="source",
                line=line
            ))

        # MSSQL: :r file.sql
        # Support quoted paths: :r "path with spaces.sql" or :r 'path.sql'
        mssql_pattern = r'^\s*:r\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s;]+))'
        for match in re.finditer(mssql_pattern, content, re.MULTILINE):
            # Try to get the path from any of the three capture groups
            target_file = match.group(1) or match.group(2) or match.group(3)
            if not target_file:
                continue

            line = content[:match.start()].count('\n') + 1

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=target_file,
                import_type="file",
                line=line
            ))

        # Database switching: USE database_name
        use_pattern = r'^\s*USE\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        for match in re.finditer(use_pattern, content, re.MULTILINE | re.IGNORECASE):
            database_name = match.group(1).strip()
            line = content[:match.start()].count('\n') + 1

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=database_name,
                import_type="database",
                line=line
            ))

        # Cross-database references: database.table or database.schema.table
        # Match database.table but only in SQL contexts (SELECT, FROM, JOIN, INSERT, UPDATE, etc.)
        # Use lookahead/lookbehind to ensure we're in a SQL statement context
        cross_db_pattern = r'(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)'
        seen_refs = set()  # Avoid duplicates (per database name)
        for match in re.finditer(cross_db_pattern, content, re.IGNORECASE):
            database = match.group(1)

            # Skip common SQL keywords that might match (e.g., information_schema.tables)
            skip_keywords = {'information_schema', 'performance_schema', 'mysql', 'sys'}
            if database.lower() in skip_keywords:
                continue

            # Avoid duplicate database references (not full match, just database name)
            if database not in seen_refs:
                seen_refs.add(database)
                line = content[:match.start()].count('\n') + 1

                imports.append(ImportInfo(
                    source_file=file_path,
                    target_module=database,
                    import_type="cross_database",
                    line=line
                ))

        # Handle relative imports for file-based imports
        for imp in imports:
            if imp.import_type in ("relative", "file", "source"):
                # Only resolve if it looks like a file path
                if '/' in imp.target_module or '\\' in imp.target_module or imp.target_module.endswith('.sql'):
                    resolved = self._resolve_relative_import(file_path, imp.target_module)
                    if resolved:
                        imp.target_module = resolved

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in SQL file.

        Entry points include:
        - Migration files (detected by filename patterns)
        - Schema files (CREATE DATABASE, CREATE SCHEMA)
        - Seed files (detected by filename patterns)
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        # Migration file detection by filename pattern
        # Patterns: YYYYMMDD_*.sql, *_up.sql, *_down.sql, V1_*.sql (Flyway), etc.
        migration_patterns = [
            r'^\d{8}_',           # YYYYMMDD_
            r'^\d{14}_',          # YYYYMMDDHHmmss_
            r'_up\.sql$',         # *_up.sql
            r'_down\.sql$',       # *_down.sql
            r'^[Vv]\d+_',         # V1_*, v1_*, V2_* (Flyway)
            r'^[0-9]+_',          # 001_*, 002_* (numbered migrations)
        ]

        for pattern in migration_patterns:
            if re.search(pattern, filename):
                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="migration",
                    name=Path(file_path).stem,
                    line=1
                ))
                break  # Only mark once as migration

        # Seed file detection by filename or directory
        seed_patterns = [
            r'seed',              # *seed*.sql, seeds/*.sql
            r'fixture',           # *fixture*.sql
            r'sample',            # *sample*.sql
        ]

        for pattern in seed_patterns:
            if re.search(pattern, filename, re.IGNORECASE) or re.search(pattern, file_path, re.IGNORECASE):
                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="seed",
                    name=Path(file_path).stem,
                    line=1
                ))
                break  # Only mark once as seed

        # CREATE DATABASE statements
        create_db_pattern = r'^\s*CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)'
        for match in re.finditer(create_db_pattern, content, re.MULTILINE | re.IGNORECASE):
            db_name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            entry_points.append(EntryPointInfo(
                file=file_path,
                type="database_creation",
                name=db_name,
                line=line
            ))

        # CREATE SCHEMA statements
        create_schema_pattern = r'^\s*CREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)'
        for match in re.finditer(create_schema_pattern, content, re.MULTILINE | re.IGNORECASE):
            schema_name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            entry_points.append(EntryPointInfo(
                file=file_path,
                type="schema_creation",
                name=schema_name,
                line=line
            ))

        return entry_points
