"""Go language support - unified scanner and analyzer.

This module combines GoScanner and GoAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_go
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class GoLanguage(BaseLanguage):
    """Unified language handler for Go files (.go).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract structs, interfaces, functions, methods with signatures
    - extract_imports(): Find import statements
    - find_entry_points(): Find main functions, init functions, HTTP handlers
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Find function/method calls (not yet implemented)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_go.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".go"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Go"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip generated Go files."""
        filename_lower = filename.lower()
        # Skip generated protobuf files
        if filename_lower.endswith('.pb.go'):
            return True
        # Skip other generated files
        if filename_lower.endswith('.gen.go') or 'generated' in filename_lower:
            return True
        return False

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip Go files that should not be analyzed.

        Go-specific skip patterns:
        - Skip generated files (*.pb.go, *.gen.go)
        - vendor/ and testdata/ are already filtered by COMMON_SKIP_DIRS
        """
        filename = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # Skip generated protobuf files
        if filename.endswith('.pb.go'):
            return False

        # Skip other generated files
        if filename.endswith('.gen.go') or 'generated' in filename:
            return False

        # Skip vendor (should be caught by COMMON_SKIP_DIRS, but double-check)
        if '/vendor/' in path_lower:
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value Go files for inventory listing.

        Low-value files:
        - Generated files (caught by should_analyze)
        - Very small files (likely stubs)
        """
        filename = Path(file_path).name.lower()

        # Generated files (double-check)
        if filename.endswith('.pb.go') or filename.endswith('.gen.go'):
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from GoScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Go source code and extract structure with metadata."""
        try:
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

        def traverse(node: Node, parent_structures: list):
            # Handle parse errors
            if node.type == "ERROR":
                if self.show_errors:
                    error_node = StructureNode(
                        type="parse-error",
                        name="invalid syntax",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1
                    )
                    parent_structures.append(error_node)
                return

            # Type declarations (struct, interface)
            if node.type == "type_declaration":
                type_node = self._extract_type(node, source_code)
                if type_node:
                    parent_structures.append(type_node)

            # Function declarations (standalone functions)
            elif node.type == "function_declaration":
                func_node = self._extract_function(node, source_code)
                parent_structures.append(func_node)

            # Method declarations (functions with receivers)
            elif node.type == "method_declaration":
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Import declarations
            elif node.type == "import_declaration":
                self._handle_import(node, parent_structures)

            else:
                # Keep traversing
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_type(self, node: Node, source_code: bytes) -> Optional[StructureNode]:
        """Extract type declaration (struct, interface, etc.)."""
        # type_declaration has a type_spec child
        type_spec = None
        for child in node.children:
            if child.type == "type_spec":
                type_spec = child
                break

        if not type_spec:
            return None

        # Get type name
        name_node = type_spec.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get type definition (struct, interface, etc.)
        type_node = type_spec.child_by_field_name("type")
        if not type_node:
            return None

        type_kind = type_node.type

        # Map Go type kinds to our structure types
        if type_kind == "struct_type":
            struct_type = "struct"
        elif type_kind == "interface_type":
            struct_type = "interface"
        else:
            # For other types (aliases, etc.), use generic "type"
            struct_type = "type"

        # Extract comments
        docstring = self._extract_comment(node, source_code)

        # Check for exported (public) types
        modifiers = self._extract_type_modifiers(name)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type=struct_type,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_function(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract standalone function declaration."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get signature
        signature = self._extract_signature(node, source_code)

        # Extract comments
        docstring = self._extract_comment(node, source_code)

        # Check for exported (public) functions
        modifiers = self._extract_function_modifiers(name, node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="function",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_method(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract method declaration (function with receiver)."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get receiver
        receiver_node = node.child_by_field_name("receiver")
        receiver_text = None
        if receiver_node:
            receiver_text = self._get_node_text(receiver_node, source_code).strip()

        # Get signature
        signature = self._extract_signature(node, source_code, receiver_text)

        # Extract comments
        docstring = self._extract_comment(node, source_code)

        # Check for exported (public) methods
        modifiers = self._extract_function_modifiers(name, node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_signature(
        self, node: Node, source_code: bytes, receiver: Optional[str] = None
    ) -> Optional[str]:
        """Extract function/method signature with parameters and return types."""
        parts = []

        # Add receiver for methods
        if receiver:
            parts.append(receiver)
            parts.append(" ")

        # Get parameters
        params_node = node.child_by_field_name("parameters")
        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            parts.append(params_text)

        # Get return type/result
        result_node = node.child_by_field_name("result")
        if result_node:
            result_text = self._get_node_text(result_node, source_code).strip()
            # Go can have named or unnamed return values
            # If it's a parameter_list (multiple returns), keep parentheses
            # If it's a single type, just show the type
            if result_node.type == "parameter_list" or " " in result_text:
                parts.append(f" {result_text}")
            else:
                parts.append(f" {result_text}")

        signature = "".join(parts) if parts else None
        return self._normalize_signature(signature) if signature else None

    def _extract_comment(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract comment immediately preceding a declaration."""
        # In Go, comments are typically previous siblings
        prev = node.prev_sibling

        comments = []
        while prev and prev.type == "comment":
            comment_text = self._get_node_text(prev, source_code).strip()
            # Remove comment markers
            if comment_text.startswith("//"):
                comment_text = comment_text[2:].strip()
            elif comment_text.startswith("/*"):
                comment_text = comment_text[2:].strip()
                if comment_text.endswith("*/"):
                    comment_text = comment_text[:-2].strip()
            if comment_text:
                comments.insert(0, comment_text)
            prev = prev.prev_sibling

        if comments:
            # Return first line
            return comments[0]
        return None

    def _extract_type_modifiers(self, name: str) -> list[str]:
        """Extract modifiers for types (public/private based on capitalization)."""
        modifiers = []
        if name and name[0].isupper():
            modifiers.append("public")
        return modifiers

    def _extract_function_modifiers(
        self, name: str, node: Node, source_code: bytes
    ) -> list[str]:
        """Extract modifiers for functions/methods."""
        modifiers = []

        # Public if capitalized
        if name and name[0].isupper():
            modifiers.append("public")

        return modifiers

    def _handle_import(self, node: Node, parent_structures: list):
        """Group import statements together."""
        if not parent_structures or parent_structures[-1].type != "imports":
            import_node = StructureNode(
                type="imports",
                name="import statements",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(import_node)
        else:
            # Extend the end line of the existing import group
            parent_structures[-1].end_line = node.end_point[0] + 1

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for severely malformed files."""
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find type declarations
        for match in re.finditer(r'^type\s+(\w+)\s+(struct|interface)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            type_kind = match.group(2)
            structures.append(StructureNode(
                type=type_kind,
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find function declarations
        for match in re.finditer(r'^func\s+(\w+)\s*\((.*?)\)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            name = match.group(1)
            params = match.group(2)

            structures.append(StructureNode(
                type="function",
                name=name + " (fallback)",
                start_line=line_num,
                end_line=line_num,
                signature=f"({params})"
            ))

        # Find method declarations (with receivers)
        for match in re.finditer(
            r'^func\s+\((\w+\s+\*?\w+)\)\s+(\w+)\s*\((.*?)\)', text, re.MULTILINE
        ):
            line_num = text[:match.start()].count('\n') + 1
            receiver = match.group(1)
            name = match.group(2)
            params = match.group(3)

            structures.append(StructureNode(
                type="method",
                name=name + " (fallback)",
                start_line=line_num,
                end_line=line_num,
                signature=f"({receiver}) ({params})"
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from GoAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract import statements from Go file.

        Patterns supported:
        - import "package"
        - import alias "package"
        - import ( ... ) (grouped imports)
        """
        imports = []

        # Pattern 1: Single import
        single_import_pattern = r'^\s*import\s+(?:(\w+)\s+)?"([^"]+)"'
        for match in re.finditer(single_import_pattern, content, re.MULTILINE):
            alias = match.group(1)  # Optional alias
            package = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=package,
                    line=line_num,
                    import_type="import",
                    imported_names=[alias] if alias else [],
                )
            )

        # Pattern 2: Grouped imports
        # import (
        #     "fmt"
        #     alias "package"
        # )
        grouped_pattern = r'import\s*\(\s*((?:[^)]+))\s*\)'
        for match in re.finditer(grouped_pattern, content, re.DOTALL):
            import_block = match.group(1)
            block_start_line = content[:match.start()].count('\n') + 1

            # Parse each line in the import block
            for line in import_block.split('\n'):
                line = line.strip()
                if not line or line.startswith('//'):
                    continue

                # Match: alias "package" OR "package"
                import_line_pattern = r'(?:(\w+)\s+)?"([^"]+)"'
                line_match = re.search(import_line_pattern, line)
                if line_match:
                    alias = line_match.group(1)
                    package = line_match.group(2)

                    imports.append(
                        ImportInfo(
                            source_file=file_path,
                            target_module=package,
                            line=block_start_line,
                            import_type="import",
                            imported_names=[alias] if alias else [],
                        )
                    )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in Go file.

        Entry points:
        - func main() in package main
        - init() functions (special Go initialization)
        - HTTP handlers
        """
        entry_points = []

        # Check if this is package main
        is_main_package = bool(re.search(r'^\s*package\s+main', content, re.MULTILINE))

        # Pattern 1: func main()
        main_func_pattern = r'^\s*func\s+main\s*\(\s*\)'
        for match in re.finditer(main_func_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            if is_main_package:
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="main_function",
                        line=line_num,
                        name="main",
                    )
                )

        # Pattern 2: init() functions (run before main)
        init_func_pattern = r'^\s*func\s+init\s*\(\s*\)'
        for match in re.finditer(init_func_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="init_function",
                    line=line_num,
                    name="init",
                )
            )

        # Pattern 3: HTTP handlers (common pattern)
        # func (s *Server) HandleXyz(w http.ResponseWriter, r *http.Request)
        handler_pattern = r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\([^)]*http\.ResponseWriter[^)]*\)'
        for match in re.finditer(handler_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            handler_name = match.group(1)
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="http_handler",
                    line=line_num,
                    name=handler_name,
                )
            )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract function/class definitions by reusing scan() output.

        This is the key optimization: instead of re-parsing with tree-sitter,
        we convert the StructureNode output from scan() to DefinitionInfo.
        """
        try:
            structures = self.scan(content.encode("utf-8"))
            if not structures:
                return []
            return self._structures_to_definitions(file_path, structures)
        except Exception:
            # Fallback to regex-based extraction
            return self._extract_definitions_regex(file_path, content)

    def _structures_to_definitions(
        self, file_path: str, structures: list[StructureNode], parent: str = None
    ) -> list[DefinitionInfo]:
        """Convert StructureNode list to DefinitionInfo list.

        Override to handle Go-specific types (struct, interface).
        """
        definitions = []

        for node in structures:
            # Handle Go-specific types: struct, interface, plus standard ones
            if node.type in ("struct", "interface", "type", "function", "method"):
                definitions.append(
                    DefinitionInfo(
                        file=file_path,
                        type=node.type,
                        name=node.name,
                        line=node.start_line,
                        signature=node.signature,
                        parent=parent,
                    )
                )

            # Recurse into children
            if node.children:
                # For structs, set them as parent for nested methods
                child_parent = node.name if node.type in ("struct", "interface") else parent
                definitions.extend(
                    self._structures_to_definitions(file_path, node.children, child_parent)
                )

        return definitions

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        # Find type declarations
        for match in re.finditer(r'^type\s+(\w+)\s+(struct|interface)', content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            type_kind = match.group(2)
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type=type_kind,
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        # Find functions
        for match in re.finditer(r'^func\s+(\w+)\s*\(', content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="function",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        # Find methods (with receivers)
        for match in re.finditer(
            r'^func\s+\(\w+\s+\*?(\w+)\)\s+(\w+)\s*\(', content, re.MULTILINE
        ):
            line = content[: match.start()].count("\n") + 1
            receiver_type = match.group(1)
            method_name = match.group(2)
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="method",
                    name=method_name,
                    line=line,
                    signature=None,
                    parent=receiver_type,
                )
            )

        return definitions

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Extract function/method calls.

        Note: Not yet implemented with tree-sitter.
        Returns empty list (uses base class default behavior).
        """
        # TODO: Implement call extraction using tree-sitter
        return []

    # ===========================================================================
    # Classification (enhanced for Go)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify Go file into architectural cluster.

        Uses base class heuristics plus Go-specific patterns.
        """
        # Use base class classification (handles common patterns like test_)
        base_cluster = super().classify_file(file_path, content)

        # Go-specific patterns
        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points (main package)
            if name == "main.go":
                return "entry_points"

            # Check package declaration
            is_main_package = bool(re.search(r'^\s*package\s+main', content, re.MULTILINE))
            if is_main_package:
                return "entry_points"

            # Config files
            if name in ["config.go", "settings.go", "env.go"]:
                return "config"

            # Handlers/Controllers (check both middle and start of path)
            if "/handlers/" in path_lower or path_lower.startswith("handlers/"):
                return "core_logic"
            if "/controllers/" in path_lower or path_lower.startswith("controllers/"):
                return "core_logic"

            # Models
            if "/models/" in path_lower or path_lower.startswith("models/"):
                return "core_logic"
            if name.endswith("_model.go"):
                return "core_logic"

            # Internal packages (Go convention for private code)
            if "/internal/" in path_lower or path_lower.startswith("internal/"):
                return "core_logic"

            # Test files
            if name.endswith("_test.go"):
                return "tests"

        return base_cluster

    # ===========================================================================
    # CodeMap Integration
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> Optional[str]:
        """
        Resolve Go import path to file path.

        Go imports are package paths like:
        - "fmt" (stdlib)
        - "github.com/user/pkg" (external)
        - "./internal/utils" (relative, rare)

        For internal packages, we try to match against project files.
        """
        # Skip stdlib and common external packages
        stdlib_prefixes = (
            "fmt", "os", "io", "net", "http", "time", "sync", "context",
            "strings", "bytes", "encoding", "crypto", "runtime", "reflect",
            "database", "log", "testing", "path", "regexp", "sort",
        )
        if module.split("/")[0] in stdlib_prefixes:
            return None

        # Try to match package path to local files
        # github.com/user/project/pkg/foo -> pkg/foo/*.go
        parts = module.split("/")

        # Try finding a matching directory
        for i in range(len(parts)):
            subpath = "/".join(parts[i:])
            for f in all_files:
                if f.startswith(subpath + "/") and f.endswith(".go"):
                    return f

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """
        Format Go entry point for display.

        Formats:
        - main_function: "func main() @line"
        - init_function: "func init() @line"
        - http_handler: "HandlerName @line"
        """
        if ep.type == "main_function":
            return f"  {ep.file}:func main() @{ep.line}"
        elif ep.type == "init_function":
            return f"  {ep.file}:func init() @{ep.line}"
        elif ep.type == "http_handler":
            return f"  {ep.file}:{ep.name} @{ep.line}"
        else:
            return super().format_entry_point(ep)
