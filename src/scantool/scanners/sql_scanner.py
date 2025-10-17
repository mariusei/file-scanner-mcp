"""Scanner for SQL files with multi-dialect support."""

import re
from typing import Optional

import tree_sitter_sql
from tree_sitter import Language, Parser, Node

from .base import BaseScanner, StructureNode

# Optional PostgreSQL-specific parser
try:
    import pglast
    from pglast import parse_sql
    HAS_PGLAST = True
except ImportError:
    HAS_PGLAST = False


class SQLScanner(BaseScanner):
    """Scanner for SQL files with support for tables, views, functions, and indexes.

    Supports multiple SQL dialects with automatic detection:
    - PostgreSQL (via pglast for PL/pgSQL support)
    - MySQL (via tree-sitter-sql)
    - SQLite (via tree-sitter-sql)
    - Generic SQL (via tree-sitter-sql)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_sql.language())
        self.detected_dialect = None

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".sql"]

    @classmethod
    def get_language_name(cls) -> str:
        return "SQL"

    def _detect_dialect(self, source_code: bytes) -> str:
        """Detect SQL dialect by examining file content.

        Returns:
            'postgresql', 'mysql', 'sqlite', or 'generic'
        """
        try:
            text = source_code.decode('utf-8', errors='replace').upper()
        except Exception:
            return 'generic'

        # PostgreSQL markers (DO blocks, PL/pgSQL, system catalogs)
        postgres_markers = [
            'DO $$', 'DO $', '$$;',  # DO blocks
            'PLPGSQL', 'PL/PGSQL',  # PL/pgSQL
            'RAISE NOTICE', 'RAISE EXCEPTION', 'RAISE WARNING',  # PL/pgSQL raise
            'PARTITION BY LIST', 'PARTITION BY RANGE',  # PostgreSQL partitioning
            'PG_CLASS', 'PG_NAMESPACE', 'PG_CATALOG',  # PostgreSQL system catalogs
            'UNLOGGED TABLE', 'DEFERRABLE INITIALLY',  # PostgreSQL-specific syntax
            'EXECUTE FORMAT(',  # Dynamic SQL in PL/pgSQL
        ]

        # MySQL markers
        mysql_markers = [
            'ENGINE=INNODB', 'ENGINE=MYISAM',  # MySQL storage engines
            'AUTO_INCREMENT',  # MySQL auto increment (different from PostgreSQL SERIAL)
            'UNSIGNED',  # MySQL unsigned types
            '`',  # Backtick identifiers (very common in MySQL)
            'TINYINT', 'MEDIUMINT',  # MySQL-specific types
        ]

        # SQLite markers
        sqlite_markers = [
            'AUTOINCREMENT',  # SQLite (vs AUTO_INCREMENT)
            'WITHOUT ROWID',  # SQLite-specific
            'PRAGMA',  # SQLite pragma statements
        ]

        # Count markers
        postgres_count = sum(1 for marker in postgres_markers if marker in text)
        mysql_count = sum(1 for marker in mysql_markers if marker in text)
        sqlite_count = sum(1 for marker in sqlite_markers if marker in text)

        # Determine dialect based on markers
        if postgres_count > 0 and postgres_count >= mysql_count and postgres_count >= sqlite_count:
            return 'postgresql'
        elif mysql_count > 0 and mysql_count > sqlite_count:
            return 'mysql'
        elif sqlite_count > 0:
            return 'sqlite'
        else:
            return 'generic'

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan SQL source code and extract structure."""
        try:
            # Detect SQL dialect
            self.detected_dialect = self._detect_dialect(source_code)

            # Use PostgreSQL-specific parser if available and dialect is PostgreSQL
            if self.detected_dialect == 'postgresql' and HAS_PGLAST:
                return self._scan_postgresql(source_code)

            # Use tree-sitter for other dialects
            tree = self.parser.parse(source_code)

            # Check if we should use fallback due to too many errors
            if self._should_use_fallback(tree.root_node):
                return self._fallback_extract(source_code)

            return self._extract_structure(tree.root_node, source_code)

        except Exception as e:
            # Return error node instead of crashing
            return [StructureNode(
                type="error",
                name=f"Failed to parse: {str(e)}",
                start_line=1,
                end_line=1
            )]

    def _extract_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract structure using tree-sitter."""
        structures = []

        def traverse(node: Node, parent_structures: list, parent_node: Optional[Node] = None):
            # Handle parse errors
            if node.type == "ERROR":
                if self.show_errors:
                    error_node = StructureNode(
                        type="parse-error",
                        name="⚠ invalid syntax",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1
                    )
                    parent_structures.append(error_node)
                return

            # CREATE TABLE
            if node.type == "create_table":
                table_node = self._extract_table(node, source_code, parent_node)
                parent_structures.append(table_node)

            # CREATE VIEW
            elif node.type == "create_view":
                view_node = self._extract_view(node, source_code, parent_node)
                parent_structures.append(view_node)

            # CREATE FUNCTION
            elif node.type == "create_function":
                function_node = self._extract_function(node, source_code, parent_node)
                parent_structures.append(function_node)

            # CREATE INDEX
            elif node.type == "create_index":
                index_node = self._extract_index(node, source_code, parent_node)
                parent_structures.append(index_node)

            # CREATE PROCEDURE (may have errors in tree-sitter-sql)
            elif node.type == "create_procedure":
                procedure_node = self._extract_procedure(node, source_code, parent_node)
                parent_structures.append(procedure_node)

            # CREATE TRIGGER (may have errors in tree-sitter-sql)
            elif node.type == "create_trigger":
                trigger_node = self._extract_trigger(node, source_code, parent_node)
                parent_structures.append(trigger_node)

            # Comments (single-line and block)
            elif node.type == "comment":
                self._handle_comment(node, parent_structures, source_code)

            else:
                for child in node.children:
                    traverse(child, parent_structures, node)

        traverse(root, structures)
        return structures

    def _extract_table(self, node: Node, source_code: bytes, parent_node: Optional[Node] = None) -> StructureNode:
        """Extract CREATE TABLE with columns."""
        # Get table name
        name_node = self._find_object_reference(node)
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Extract columns
        columns = []
        column_defs = self._find_node_by_type(node, "column_definitions")
        if column_defs:
            for child in column_defs.children:
                if child.type == "column_definition":
                    col_info = self._extract_column(child, source_code)
                    if col_info:
                        columns.append(col_info)

        # Get doc comment (preceding comment) - check parent's sibling first
        docstring = self._extract_preceding_comment(parent_node if parent_node else node, source_code)

        return StructureNode(
            type="table",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=docstring,
            children=columns
        )

    def _extract_column(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract column definition."""
        # Get column name (first identifier)
        col_name = None
        col_type = None
        constraints = []

        for child in node.children:
            if child.type == "identifier" and col_name is None:
                col_name = self._get_node_text(child, source_code)
            elif child.type in ("int", "varchar", "text", "decimal", "timestamp",
                               "date", "boolean", "bigint", "smallint", "float",
                               "double", "char", "blob", "json"):
                col_type = self._get_node_text(child, source_code).upper()
            elif child.type.startswith("keyword_"):
                keyword = self._get_node_text(child, source_code).upper()
                if keyword in ("PRIMARY", "NOT", "NULL", "UNIQUE", "AUTO_INCREMENT",
                              "DEFAULT", "KEY", "REFERENCES", "FOREIGN"):
                    constraints.append(keyword)

        if not col_name:
            return None

        # Build signature with type and constraints
        signature_parts = []
        if col_type:
            signature_parts.append(col_type)
        if constraints:
            signature_parts.append(" ".join(constraints))

        signature = " ".join(signature_parts) if signature_parts else None

        return StructureNode(
            type="column",
            name=col_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature
        )

    def _extract_view(self, node: Node, source_code: bytes, parent_node: Optional[Node] = None) -> StructureNode:
        """Extract CREATE VIEW."""
        # Get view name
        name_node = self._find_object_reference(node)
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get query (after AS)
        query_node = self._find_node_by_type(node, "create_query")
        signature = None
        if query_node:
            query_text = self._get_node_text(query_node, source_code).strip()
            # Simplify for signature (just first part)
            if len(query_text) > 50:
                signature = query_text[:50] + "..."
            else:
                signature = query_text

        # Get doc comment
        docstring = self._extract_preceding_comment(parent_node if parent_node else node, source_code)

        return StructureNode(
            type="view",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring
        )

    def _extract_function(self, node: Node, source_code: bytes, parent_node: Optional[Node] = None) -> StructureNode:
        """Extract CREATE FUNCTION."""
        # Get function name
        name_node = self._find_object_reference(node)
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get parameters
        params_node = self._find_node_by_type(node, "function_arguments")
        params = None
        if params_node:
            params = self._get_node_text(params_node, source_code)

        # Get return type
        return_type = None
        for child in node.children:
            if child.type == "keyword_returns":
                # Next sibling should be the type
                next_idx = node.children.index(child) + 1
                if next_idx < len(node.children):
                    next_node = node.children[next_idx]
                    if next_node.type not in ("keyword_table", "keyword_as", "keyword_begin"):
                        return_type = self._get_node_text(next_node, source_code).strip()
                break

        # Build signature
        signature_parts = []
        if params:
            signature_parts.append(params)
        if return_type:
            signature_parts.append(f"-> {return_type}")

        signature = " ".join(signature_parts) if signature_parts else None
        signature = self._normalize_signature(signature) if signature else None

        # Get doc comment
        docstring = self._extract_preceding_comment(parent_node if parent_node else node, source_code)

        return StructureNode(
            type="function",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring
        )

    def _extract_procedure(self, node: Node, source_code: bytes, parent_node: Optional[Node] = None) -> StructureNode:
        """Extract CREATE PROCEDURE."""
        # Get procedure name
        name_node = self._find_object_reference(node)
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get parameters
        params_node = self._find_node_by_type(node, "function_arguments")
        signature = None
        if params_node:
            signature = self._get_node_text(params_node, source_code)
            signature = self._normalize_signature(signature) if signature else None

        # Get doc comment
        docstring = self._extract_preceding_comment(parent_node if parent_node else node, source_code)

        return StructureNode(
            type="procedure",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring
        )

    def _extract_trigger(self, node: Node, source_code: bytes, parent_node: Optional[Node] = None) -> StructureNode:
        """Extract CREATE TRIGGER."""
        # Get trigger name
        name_node = self._find_object_reference(node)
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Try to extract timing and event
        timing = None
        event = None
        table = None

        for child in node.children:
            if child.type in ("keyword_before", "keyword_after"):
                timing = self._get_node_text(child, source_code).upper()
            elif child.type in ("keyword_insert", "keyword_update", "keyword_delete"):
                event = self._get_node_text(child, source_code).upper()
            elif child.type == "keyword_on":
                # Next sibling is the table
                idx = node.children.index(child) + 1
                if idx < len(node.children):
                    table_node = node.children[idx]
                    if table_node.type == "identifier":
                        table = self._get_node_text(table_node, source_code)

        # Build signature
        signature_parts = []
        if timing:
            signature_parts.append(timing)
        if event:
            signature_parts.append(event)
        if table:
            signature_parts.append(f"ON {table}")

        signature = " ".join(signature_parts) if signature_parts else None

        # Get doc comment
        docstring = self._extract_preceding_comment(parent_node if parent_node else node, source_code)

        return StructureNode(
            type="trigger",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring
        )

    def _extract_index(self, node: Node, source_code: bytes, parent_node: Optional[Node] = None) -> StructureNode:
        """Extract CREATE INDEX."""
        # Get index name
        index_name = None
        table_name = None
        columns = None

        for child in node.children:
            if child.type == "identifier" and index_name is None:
                index_name = self._get_node_text(child, source_code)
            elif child.type == "object_reference" and table_name is None:
                table_name = self._get_node_text(child, source_code)
            elif child.type == "index_fields":
                columns = self._get_node_text(child, source_code)

        name = index_name or "unnamed"

        # Build signature
        signature_parts = []
        if table_name:
            signature_parts.append(f"ON {table_name}")
        if columns:
            signature_parts.append(columns)

        signature = " ".join(signature_parts) if signature_parts else None

        # Get doc comment
        docstring = self._extract_preceding_comment(parent_node if parent_node else node, source_code)

        return StructureNode(
            type="index",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring
        )

    def _find_object_reference(self, node: Node) -> Optional[Node]:
        """Find object_reference node (used for names)."""
        for child in node.children:
            if child.type == "object_reference":
                # Get the identifier within
                for subchild in child.children:
                    if subchild.type == "identifier":
                        return subchild
                return child
        return None

    def _find_node_by_type(self, node: Node, node_type: str) -> Optional[Node]:
        """Find first child node of given type."""
        for child in node.children:
            if child.type == node_type:
                return child
        return None

    def _extract_preceding_comment(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract preceding comment (-- or /* */)."""
        prev = node.prev_sibling

        # Look for comment immediately before this node
        while prev:
            if prev.type == "comment":
                comment_text = self._get_node_text(prev, source_code).strip()

                # Handle single-line comments (--)
                if comment_text.startswith("--"):
                    doc_text = comment_text[2:].strip()
                    return doc_text if doc_text else None

                # Handle block comments (/* */)
                elif comment_text.startswith("/*") and comment_text.endswith("*/"):
                    doc_text = comment_text[2:-2].strip()
                    # Get first non-empty line
                    lines = [line.strip().lstrip('*').strip() for line in doc_text.split('\n')]
                    for line in lines:
                        if line:
                            return line
                    return None

                break
            elif prev.type in ("statement", ";"):
                # Stop at statement boundaries
                break
            else:
                prev = prev.prev_sibling

        return None

    def _handle_comment(self, node: Node, parent_structures: list, source_code: bytes):
        """Handle standalone comments."""
        # Only include if show_errors is enabled (comments shown as metadata otherwise)
        # We don't need to show standalone comments as structures
        pass

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for severely malformed files."""
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find CREATE TABLE
        for match in re.finditer(r'CREATE\s+TABLE\s+(\w+)', text, re.IGNORECASE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="table",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find CREATE VIEW
        for match in re.finditer(r'CREATE\s+VIEW\s+(\w+)', text, re.IGNORECASE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="view",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find CREATE FUNCTION
        for match in re.finditer(r'CREATE\s+FUNCTION\s+(\w+)', text, re.IGNORECASE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="function",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find CREATE PROCEDURE
        for match in re.finditer(r'CREATE\s+PROCEDURE\s+(\w+)', text, re.IGNORECASE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="procedure",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find CREATE INDEX
        for match in re.finditer(r'CREATE\s+INDEX\s+(\w+)', text, re.IGNORECASE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="index",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        # Find CREATE TRIGGER
        for match in re.finditer(r'CREATE\s+TRIGGER\s+(\w+)', text, re.IGNORECASE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="trigger",
                name=match.group(1) + " ⚠",
                start_line=line_num,
                end_line=line_num
            ))

        return structures

    def _scan_postgresql(self, source_code: bytes) -> list[StructureNode]:
        """Scan PostgreSQL-specific SQL using pglast parser."""
        if not HAS_PGLAST:
            # Fallback to tree-sitter if pglast not available
            tree = self.parser.parse(source_code)
            return self._extract_structure(tree.root_node, source_code)

        try:
            text = source_code.decode('utf-8', errors='replace')
            structures = []

            # Parse with pglast
            statements = parse_sql(text)

            # Track line numbers for proper ranges
            lines = text.split('\n')

            for stmt in statements:
                if not hasattr(stmt, 'stmt'):
                    continue

                stmt_obj = stmt.stmt
                stmt_type = type(stmt_obj).__name__

                # Get statement location from byte offset
                start_line = 1
                if hasattr(stmt, 'stmt_location') and stmt.stmt_location >= 0:
                    start_line = text[:stmt.stmt_location].count('\n') + 1
                end_line = start_line

                # Extract different PostgreSQL statement types
                if stmt_type == 'CreateStmt':  # CREATE TABLE
                    node = self._extract_pgsql_table(stmt_obj, text, start_line)
                    if node:
                        structures.append(node)

                elif stmt_type == 'ViewStmt':  # CREATE VIEW
                    node = self._extract_pgsql_view(stmt_obj, text, start_line)
                    if node:
                        structures.append(node)

                elif stmt_type == 'CreateFunctionStmt':  # CREATE FUNCTION
                    node = self._extract_pgsql_function(stmt_obj, text, start_line)
                    if node:
                        structures.append(node)

                elif stmt_type == 'IndexStmt':  # CREATE INDEX
                    node = self._extract_pgsql_index(stmt_obj, text, start_line)
                    if node:
                        structures.append(node)

                elif stmt_type == 'DoStmt':  # DO blocks (PL/pgSQL)
                    node = self._extract_pgsql_do_block(stmt_obj, text, start_line)
                    if node:
                        structures.append(node)

                elif stmt_type in ('AlterTableStmt', 'RenameStmt'):
                    # ALTER TABLE, RENAME - show as metadata
                    node = self._extract_pgsql_alter(stmt_obj, stmt_type, text, start_line)
                    if node:
                        structures.append(node)

            return structures

        except Exception as e:
            # If pglast fails, fallback to tree-sitter
            if self.show_errors:
                return [StructureNode(
                    type="error",
                    name=f"PostgreSQL parse error: {str(e)}",
                    start_line=1,
                    end_line=1
                )]
            tree = self.parser.parse(source_code)
            return self._extract_structure(tree.root_node, source_code)

    def _extract_pgsql_table(self, stmt, text: str, approx_line: int) -> Optional[StructureNode]:
        """Extract CREATE TABLE from pglast AST."""
        if not hasattr(stmt, 'relation') or not stmt.relation:
            return None

        table_name = stmt.relation.relname if hasattr(stmt.relation, 'relname') else 'unnamed'

        # Find actual line number
        start_line, end_line = self._find_statement_lines(text, f'CREATE.*TABLE.*{table_name}', approx_line)

        # Extract columns if present
        children = []
        if hasattr(stmt, 'tableElts') and stmt.tableElts:
            for elt in stmt.tableElts:
                if hasattr(elt, 'ColumnDef'):
                    col_def = elt.ColumnDef
                    col_name = col_def.colname if hasattr(col_def, 'colname') else 'unknown'
                    col_type = None
                    if hasattr(col_def, 'typeName') and col_def.typeName:
                        type_names = col_def.typeName.names if hasattr(col_def.typeName, 'names') else []
                        if type_names:
                            col_type = str(type_names[-1].sval if hasattr(type_names[-1], 'sval') else '')

                    children.append(StructureNode(
                        type="column",
                        name=col_name,
                        start_line=start_line,
                        end_line=start_line,
                        signature=col_type
                    ))

        return StructureNode(
            type="table",
            name=table_name,
            start_line=start_line,
            end_line=end_line,
            children=children
        )

    def _extract_pgsql_view(self, stmt, text: str, approx_line: int) -> Optional[StructureNode]:
        """Extract CREATE VIEW from pglast AST."""
        if not hasattr(stmt, 'view') or not stmt.view:
            return None

        view_name = stmt.view.relname if hasattr(stmt.view, 'relname') else 'unnamed'
        start_line, end_line = self._find_statement_lines(text, f'CREATE.*VIEW.*{view_name}', approx_line)

        return StructureNode(
            type="view",
            name=view_name,
            start_line=start_line,
            end_line=end_line
        )

    def _extract_pgsql_function(self, stmt, text: str, approx_line: int) -> Optional[StructureNode]:
        """Extract CREATE FUNCTION from pglast AST."""
        if not hasattr(stmt, 'funcname') or not stmt.funcname:
            return None

        # Get function name from list of identifiers
        func_name = stmt.funcname[-1].sval if hasattr(stmt.funcname[-1], 'sval') else 'unnamed'
        start_line, end_line = self._find_statement_lines(text, f'CREATE.*FUNCTION.*{func_name}', approx_line)

        return StructureNode(
            type="function",
            name=func_name,
            start_line=start_line,
            end_line=end_line
        )

    def _extract_pgsql_index(self, stmt, text: str, approx_line: int) -> Optional[StructureNode]:
        """Extract CREATE INDEX from pglast AST."""
        if not hasattr(stmt, 'idxname'):
            return None

        index_name = stmt.idxname if stmt.idxname else 'unnamed'
        start_line, end_line = self._find_statement_lines(text, f'CREATE.*INDEX.*{index_name}', approx_line)

        return StructureNode(
            type="index",
            name=index_name,
            start_line=start_line,
            end_line=end_line
        )

    def _extract_pgsql_do_block(self, stmt, text: str, approx_line: int) -> Optional[StructureNode]:
        """Extract DO block (PL/pgSQL anonymous block) from pglast AST."""
        # Find the actual DO $$ start from the approximate line
        lines = text.split('\n')
        start_line = approx_line

        # Search forward from approx_line for "DO $$" or "DO $"
        for i in range(max(0, approx_line - 1), min(len(lines), approx_line + 10)):
            if re.search(r'\bDO\s+\$', lines[i], re.IGNORECASE):
                start_line = i + 1
                break

        end_line = self._find_do_block_end(text, start_line)

        # Try to extract a meaningful name from the block
        name = "anonymous block"
        if hasattr(stmt, 'args') and stmt.args:
            # Look for comments or identifiers in the DO block
            block_text = text[text.find('DO', (start_line-1) * 80):text.find('$$;', (start_line-1) * 80) + 3]
            if 'DECLARE' in block_text.upper():
                name = "DO block (with declarations)"
            elif 'RAISE NOTICE' in block_text.upper():
                # Extract the notice message as the name
                notice_match = re.search(r"RAISE NOTICE\s+'([^']+)'", block_text, re.IGNORECASE)
                if notice_match:
                    notice_text = notice_match.group(1)[:50]
                    name = f"DO: {notice_text}"

        return StructureNode(
            type="do-block",
            name=name,
            start_line=start_line,
            end_line=end_line
        )

    def _extract_pgsql_alter(self, stmt, stmt_type: str, text: str, approx_line: int) -> Optional[StructureNode]:
        """Extract ALTER/RENAME statements from pglast AST."""
        start_line = approx_line
        end_line = approx_line

        name = stmt_type.replace('Stmt', '').lower()

        # Try to get more specific info
        if stmt_type == 'AlterTableStmt' and hasattr(stmt, 'relation'):
            table_name = stmt.relation.relname if hasattr(stmt.relation, 'relname') else 'unknown'
            name = f"ALTER TABLE {table_name}"
            start_line, end_line = self._find_statement_lines(text, f'ALTER.*TABLE.*{table_name}', approx_line)
        elif stmt_type == 'RenameStmt':
            name = "RENAME statement"
            start_line, end_line = self._find_statement_lines(text, r'ALTER.*RENAME', approx_line)

        return StructureNode(
            type="alter",
            name=name,
            start_line=start_line,
            end_line=end_line
        )

    def _find_do_block_end(self, text: str, start_line: int) -> int:
        """Find the end line of a DO block starting at start_line."""
        lines = text.split('\n')

        # Look for $$; which ends a DO block
        for i in range(start_line - 1, min(len(lines), start_line + 100)):
            if '$$;' in lines[i]:
                return i + 1

        # Fallback: look for just semicolon
        for i in range(start_line - 1, min(len(lines), start_line + 100)):
            if lines[i].strip().endswith(';'):
                return i + 1

        return start_line

    def _find_statement_lines(self, text: str, pattern: str, approx_line: int) -> tuple[int, int]:
        """Find the actual start and end line of a statement using regex."""
        lines = text.split('\n')

        # Search around the approximate line (prefer looking forward slightly)
        search_start = max(0, approx_line - 2)
        search_end = min(len(lines), approx_line + 20)

        for i in range(search_start, search_end):
            if re.search(pattern, lines[i], re.IGNORECASE):
                start_line = i + 1
                # Find end line (look for semicolon or $$;)
                end_line = start_line
                for j in range(i, min(len(lines), i + 50)):
                    if ';' in lines[j] or '$$;' in lines[j]:
                        end_line = j + 1
                        break
                return start_line, end_line

        # Fallback to approximate line
        return approx_line, approx_line
