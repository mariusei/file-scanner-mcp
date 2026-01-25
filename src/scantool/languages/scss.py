"""SCSS/SASS language support - unified scanner and analyzer.

This module combines SCSSScanner and SCSSAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_scss
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class SCSSLanguage(BaseLanguage):
    """Unified language handler for SCSS/SASS files (.scss, .sass).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract mixins, functions, variables, rule sets with metadata
    - extract_imports(): Find @import, @use, @forward statements
    - find_entry_points(): Identify main stylesheets (non-partials)
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - classify_file(): Categorize SCSS files by purpose
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_scss.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".scss", ".sass"]

    @classmethod
    def get_language_name(cls) -> str:
        return "SCSS"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip minified and generated SCSS files."""
        if filename.endswith(".min.scss"):
            return True
        if any(pattern in filename.lower() for pattern in [
            ".generated.", ".compiled."
        ]):
            return True
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Skip SCSS files that should not be analyzed.

        - Skip minified files
        - Skip compiled output
        """
        filename = Path(file_path).name.lower()

        # Skip minified files
        if ".min." in filename:
            return False

        # Skip common generated patterns
        if any(pattern in filename for pattern in [
            ".compiled.", ".generated.", "bundle."
        ]):
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value SCSS files for inventory listing.

        Low-value files (unless central):
        - Very small partial files
        """
        filename = Path(file_path).name

        # Very small partials are low value
        if filename.startswith("_") and size < 100:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from SCSSScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan SCSS source code and extract structure with metadata."""
        try:
            tree = self.parser.parse(source_code)

            # Check for excessive errors
            if self._should_use_fallback(tree.root_node):
                if self.fallback_on_errors:
                    return self._fallback_extract(source_code)
                return None

            return self._extract_structure(tree.root_node, source_code)

        except Exception as e:
            if self.show_errors:
                print(f"SCSS parsing error: {e}")
            if self.fallback_on_errors:
                return self._fallback_extract(source_code)
            return None

    def _extract_structure(
        self, root: Node, source_code: bytes
    ) -> list[StructureNode]:
        """Extract structure from SCSS stylesheet."""
        structures = []

        for node in root.children:
            if node.type == "ERROR":
                # Extract valid structures from within ERROR nodes
                error_structures = self._extract_from_error_node(node, source_code)
                structures.extend(error_structures)
                continue

            # SCSS variables ($variable: value)
            if node.type == "declaration":
                var_node = self._extract_variable(node, source_code)
                if var_node:
                    structures.append(var_node)

            # @mixin statements
            elif node.type == "mixin_statement":
                mixin_node = self._extract_mixin(node, source_code)
                if mixin_node:
                    structures.append(mixin_node)

            # @function statements
            elif node.type == "function_statement":
                func_node = self._extract_function(node, source_code)
                if func_node:
                    structures.append(func_node)

            # @import/@use/@forward statements
            elif node.type in ("import_statement", "use_statement", "forward_statement"):
                import_node = self._extract_import_structure(node, source_code)
                if import_node:
                    structures.append(import_node)

            # @media statements
            elif node.type == "media_statement":
                media_node = self._extract_media(node, source_code)
                if media_node:
                    structures.append(media_node)

            # @keyframes statements
            elif node.type == "keyframes_statement":
                keyframes_node = self._extract_keyframes(node, source_code)
                if keyframes_node:
                    structures.append(keyframes_node)

            # Rule sets (selector { ... })
            elif node.type == "rule_set":
                rule_node = self._extract_rule_set(node, source_code)
                if rule_node:
                    structures.append(rule_node)

            # Comments (only important ones with //! or /*!)
            elif node.type == "comment":
                comment_text = self._get_node_text(node, source_code)
                if comment_text.startswith("/*!") or comment_text.startswith("//!"):
                    structures.append(StructureNode(
                        type="comment",
                        name=self._extract_comment_title(comment_text),
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        docstring=comment_text[:100]
                    ))

        return structures

    def _extract_from_error_node(
        self, error_node: Node, source_code: bytes
    ) -> list[StructureNode]:
        """Extract valid SCSS structures from within an ERROR node.

        Tree-sitter often wraps valid SCSS in ERROR nodes when there's a syntax
        issue earlier in the file. This method recursively searches for valid
        structures within ERROR nodes so we can still show useful information.
        """
        structures = []

        for child in error_node.children:
            # Recurse into nested ERROR nodes
            if child.type == "ERROR":
                structures.extend(self._extract_from_error_node(child, source_code))
                continue

            # Try to extract the same structures we would at the top level
            if child.type == "declaration":
                var_node = self._extract_variable(child, source_code)
                if var_node:
                    structures.append(var_node)

            elif child.type == "mixin_statement":
                mixin_node = self._extract_mixin(child, source_code)
                if mixin_node:
                    structures.append(mixin_node)

            elif child.type == "function_statement":
                func_node = self._extract_function(child, source_code)
                if func_node:
                    structures.append(func_node)

            elif child.type in ("import_statement", "use_statement", "forward_statement"):
                import_node = self._extract_import_structure(child, source_code)
                if import_node:
                    structures.append(import_node)

            elif child.type == "media_statement":
                media_node = self._extract_media(child, source_code)
                if media_node:
                    structures.append(media_node)

            elif child.type == "keyframes_statement":
                keyframes_node = self._extract_keyframes(child, source_code)
                if keyframes_node:
                    structures.append(keyframes_node)

            elif child.type == "rule_set":
                rule_node = self._extract_rule_set(child, source_code)
                if rule_node:
                    structures.append(rule_node)

            elif child.type == "comment":
                comment_text = self._get_node_text(child, source_code)
                if comment_text.startswith("/*!") or comment_text.startswith("//!"):
                    structures.append(StructureNode(
                        type="comment",
                        name=self._extract_comment_title(comment_text),
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        docstring=comment_text[:100]
                    ))

        return structures

    def _extract_variable(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract SCSS variable ($name: value)."""
        var_name = None

        for child in node.children:
            if child.type == "property_name":
                var_name = self._get_node_text(child, source_code)

        # Only extract SCSS variables (starting with $)
        if not var_name or not var_name.startswith("$"):
            return None

        # Get the value (everything after the colon)
        value_start = None
        for child in node.children:
            if child.type == ":":
                value_start = child.end_byte
                break

        var_value = None
        if value_start:
            # Find the end (before semicolon)
            value_text = source_code[value_start:node.end_byte].decode("utf-8", errors="replace")
            var_value = value_text.strip().rstrip(";").strip()
            if len(var_value) > 50:
                var_value = var_value[:47] + "..."

        return StructureNode(
            type="variable",
            name=var_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=var_value,
            modifiers=["scss-variable"]
        )

    def _extract_mixin(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract @mixin definition."""
        name = None
        params = None

        for child in node.children:
            if child.type == "identifier":
                name = self._get_node_text(child, source_code)
            elif child.type == "parameters":
                params = self._get_node_text(child, source_code)

        if not name:
            return None

        signature = params if params else "()"

        return StructureNode(
            type="mixin",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            modifiers=["mixin"]
        )

    def _extract_function(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract @function definition."""
        name = None
        params = None

        for child in node.children:
            if child.type == "identifier":
                name = self._get_node_text(child, source_code)
            elif child.type == "parameters":
                params = self._get_node_text(child, source_code)

        if not name:
            return None

        signature = params if params else "()"

        return StructureNode(
            type="function",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            modifiers=["scss-function"]
        )

    def _extract_import_structure(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract @import/@use/@forward statement as structure node."""
        import_type = "import"
        if node.type == "use_statement":
            import_type = "use"
        elif node.type == "forward_statement":
            import_type = "forward"

        url = None
        for child in node.children:
            if child.type in ("string_value", "call_expression"):
                url = self._get_node_text(child, source_code).strip('"\'')
                break

        if not url:
            return None

        return StructureNode(
            type="import",
            name=url,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"@{import_type}",
            modifiers=[import_type]
        )

    def _extract_media(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract @media statement."""
        query = None
        children = []

        for child in node.children:
            if child.type in ("keyword_query", "feature_query", "binary_query",
                              "unary_query", "parenthesized_query"):
                query = self._normalize_signature(
                    self._get_node_text(child, source_code)
                )
            elif child.type == "block":
                children = self._extract_nested_rules(child, source_code)

        return StructureNode(
            type="media_query",
            name=query or "@media",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=query,
            modifiers=["media"],
            children=children
        )

    def _extract_keyframes(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract @keyframes statement."""
        name = None
        for child in node.children:
            if child.type == "keyframes_name":
                name = self._get_node_text(child, source_code)
                break

        return StructureNode(
            type="keyframes",
            name=name or "animation",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            modifiers=["keyframes"]
        )

    def _extract_rule_set(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract a SCSS rule set with possible nested rules."""
        selectors = []
        children = []
        declaration_count = 0
        has_include = False
        has_extend = False

        for child in node.children:
            if child.type == "selectors":
                selectors = self._extract_selectors(child, source_code)
            elif child.type == "block":
                declaration_count, children, has_include, has_extend = \
                    self._process_scss_block(child, source_code)

        if not selectors:
            return None

        selector_text = ", ".join(selectors)
        if len(selector_text) > 60:
            selector_text = selector_text[:57] + "..."

        modifiers = []
        if any(":root" in s for s in selectors):
            modifiers.append("root")
        if any(s.startswith(".") for s in selectors):
            modifiers.append("class")
        if any(s.startswith("#") for s in selectors):
            modifiers.append("id")
        if any("&" in s for s in selectors):
            modifiers.append("nested")
        if has_include:
            modifiers.append("uses-mixin")
        if has_extend:
            modifiers.append("uses-extend")

        name = selectors[0] if len(selectors) == 1 else f"{selectors[0]} (+{len(selectors) - 1})"
        if len(name) > 50:
            name = name[:47] + "..."

        return StructureNode(
            type="rule_set",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"{len(selectors)} sel, {declaration_count} decl",
            modifiers=modifiers,
            children=children if children else None,
            complexity={"selectors": len(selectors), "declarations": declaration_count}
        )

    def _extract_selectors(
        self, selectors_node: Node, source_code: bytes
    ) -> list[str]:
        """Extract individual selectors."""
        selectors = []
        current = []

        for child in selectors_node.children:
            if child.type == ",":
                if current:
                    selectors.append(self._normalize_signature(" ".join(current)))
                    current = []
            else:
                text = self._get_node_text(child, source_code).strip()
                if text:
                    current.append(text)

        if current:
            selectors.append(self._normalize_signature(" ".join(current)))

        return selectors

    def _process_scss_block(
        self, block_node: Node, source_code: bytes
    ) -> tuple[int, list[StructureNode], bool, bool]:
        """Process SCSS block and extract nested rules."""
        declaration_count = 0
        children = []
        has_include = False
        has_extend = False

        for child in block_node.children:
            if child.type == "declaration":
                declaration_count += 1
            elif child.type == "rule_set":
                nested = self._extract_rule_set(child, source_code)
                if nested:
                    children.append(nested)
            elif child.type == "include_statement":
                has_include = True
            elif child.type == "extend_statement":
                has_extend = True

        return declaration_count, children, has_include, has_extend

    def _extract_nested_rules(
        self, block_node: Node, source_code: bytes
    ) -> list[StructureNode]:
        """Extract rules nested inside a block."""
        rules = []
        for child in block_node.children:
            if child.type == "rule_set":
                rule = self._extract_rule_set(child, source_code)
                if rule:
                    rules.append(rule)
        return rules

    def _extract_comment_title(self, comment: str) -> str:
        """Extract a title from a comment."""
        text = comment.strip("/*! \n\r\t*/").lstrip("/!")
        first_line = text.split("\n")[0].strip()
        if len(first_line) > 50:
            first_line = first_line[:47] + "..."
        return first_line or "comment"

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for malformed SCSS files."""
        text = source_code.decode("utf-8", errors="replace")
        structures = []

        # Find SCSS variables
        var_pattern = r'^\s*(\$[\w-]+)\s*:\s*([^;]+);'
        for match in re.finditer(var_pattern, text, re.MULTILINE):
            var_name = match.group(1)
            var_value = match.group(2).strip()
            line_num = text[:match.start()].count("\n") + 1
            if len(var_value) > 50:
                var_value = var_value[:47] + "..."
            structures.append(StructureNode(
                type="variable",
                name=var_name,
                start_line=line_num,
                end_line=line_num,
                signature=var_value,
                modifiers=["scss-variable"]
            ))

        # Find @mixin definitions
        mixin_pattern = r'@mixin\s+([\w-]+)\s*(\([^)]*\))?'
        for match in re.finditer(mixin_pattern, text):
            name = match.group(1)
            params = match.group(2) or "()"
            line_num = text[:match.start()].count("\n") + 1
            structures.append(StructureNode(
                type="mixin",
                name=name,
                start_line=line_num,
                end_line=line_num,
                signature=params,
                modifiers=["mixin"]
            ))

        # Find @function definitions
        func_pattern = r'@function\s+([\w-]+)\s*(\([^)]*\))?'
        for match in re.finditer(func_pattern, text):
            name = match.group(1)
            params = match.group(2) or "()"
            line_num = text[:match.start()].count("\n") + 1
            structures.append(StructureNode(
                type="function",
                name=name,
                start_line=line_num,
                end_line=line_num,
                signature=params,
                modifiers=["scss-function"]
            ))

        # Find @import/@use/@forward statements
        import_pattern = r'@(import|use|forward)\s+["\']([^"\']+)["\']'
        for match in re.finditer(import_pattern, text):
            import_type = match.group(1)
            url = match.group(2)
            line_num = text[:match.start()].count("\n") + 1
            structures.append(StructureNode(
                type="import",
                name=url,
                start_line=line_num,
                end_line=line_num,
                signature=f"@{import_type}",
                modifiers=[import_type]
            ))

        # Find @media queries
        media_pattern = r'@media\s+([^{]+)\s*\{'
        for match in re.finditer(media_pattern, text):
            query = match.group(1).strip()
            line_num = text[:match.start()].count("\n") + 1
            if len(query) > 50:
                query = query[:47] + "..."
            structures.append(StructureNode(
                type="media_query",
                name=query,
                start_line=line_num,
                end_line=line_num,
                signature=query,
                modifiers=["media"]
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from SCSSAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract import statements from SCSS file.

        Patterns supported:
        - @import "file";
        - @import "file1", "file2";
        - @use "module";
        - @use "module" as alias;
        - @forward "module";
        """
        imports = []

        # Pattern 1: @import "file" or @import "file1", "file2"
        import_pattern = r'@import\s+([^;]+);'
        for match in re.finditer(import_pattern, content):
            files_str = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Parse multiple imports
            for file_match in re.finditer(r'"([^"]+)"|\'([^\']+)\'', files_str):
                module = file_match.group(1) or file_match.group(2)

                # Skip URLs
                if module.startswith(("http://", "https://", "//")):
                    continue

                imports.append(
                    ImportInfo(
                        source_file=file_path,
                        target_module=module,
                        line=line_num,
                        import_type="import",
                    )
                )

        # Pattern 2: @use "module"
        use_pattern = r'@use\s+"([^"]+)"'
        for match in re.finditer(use_pattern, content):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type="use",
                )
            )

        # Pattern 3: @forward "module"
        forward_pattern = r'@forward\s+"([^"]+)"'
        for match in re.finditer(forward_pattern, content):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type="forward",
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in SCSS file.

        SCSS files don't have traditional entry points, but main stylesheets
        (non-partials) could be considered entry points.
        """
        entry_points = []

        filename = Path(file_path).name

        # Non-partial files (not starting with _) are entry points
        if not filename.startswith("_"):
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="stylesheet",
                    name=filename,
                    line=1,
                )
            )

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract mixin/function definitions by reusing scan() output.

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

        For SCSS, we consider mixin and function types as definitions.
        """
        definitions = []

        for node in structures:
            if node.type in ("mixin", "function"):
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

            # Recurse into children (e.g., nested rules)
            if node.children:
                definitions.extend(
                    self._structures_to_definitions(file_path, node.children, node.name)
                )

        return definitions

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        # Find @mixin definitions
        for match in re.finditer(r"@mixin\s+([\w-]+)", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="mixin",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        # Find @function definitions
        for match in re.finditer(r"@function\s+([\w-]+)", content, re.MULTILINE):
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

        return definitions

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Extract mixin includes and function calls from SCSS file.

        Patterns:
        - @include mixin-name;
        - @include mixin-name(...);
        - function-name(...)
        """
        calls = []

        # Find @include statements (mixin calls)
        include_pattern = r'@include\s+([\w-]+)'
        for match in re.finditer(include_pattern, content):
            callee_name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            calls.append(
                CallInfo(
                    caller_file=file_path,
                    caller_name=None,
                    callee_name=callee_name,
                    line=line,
                    is_cross_file=False,
                )
            )

        # Find SCSS function calls (excluding CSS functions like url(), rgb(), etc.)
        css_functions = {
            'url', 'rgb', 'rgba', 'hsl', 'hsla', 'calc', 'var', 'min', 'max',
            'clamp', 'linear-gradient', 'radial-gradient', 'conic-gradient',
            'repeat', 'minmax', 'fit-content', 'attr', 'counter', 'counters',
            'env', 'format', 'local', 'rotate', 'scale', 'translate', 'skew',
            'matrix', 'perspective', 'blur', 'brightness', 'contrast', 'drop-shadow',
            'grayscale', 'hue-rotate', 'invert', 'opacity', 'saturate', 'sepia'
        }

        # Look for function calls that are likely SCSS functions
        func_pattern = r'\b([\w-]+)\s*\('
        for match in re.finditer(func_pattern, content):
            func_name = match.group(1)
            if func_name.lower() not in css_functions:
                line = content[:match.start()].count('\n') + 1
                calls.append(
                    CallInfo(
                        caller_file=file_path,
                        caller_name=None,
                        callee_name=func_name,
                        line=line,
                        is_cross_file=False,
                    )
                )

        # Mark cross-file calls
        local_defs = {d.name for d in definitions}
        for call in calls:
            if call.callee_name not in local_defs:
                call.is_cross_file = True

        return calls

    # ===========================================================================
    # Classification
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify SCSS file into architectural cluster."""
        filename = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # Partials are utilities
        if filename.startswith("_"):
            return "utilities"

        # Main stylesheets are entry points
        if filename in ("main.scss", "styles.scss", "app.scss", "index.scss"):
            return "entry_points"

        # Variables/mixins are config
        if any(pattern in filename for pattern in ["variables", "mixins", "config", "settings"]):
            return "config"

        # Components
        if "/components/" in path_lower:
            return "core_logic"

        return "other"

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
        """Resolve SCSS @import/@use to file path.

        SCSS imports:
        - @import "file" -> _file.scss, file.scss
        - @use "module" -> _module.scss, module.scss
        """
        # Direct match
        if module in all_files:
            return module

        # Try with underscore prefix (partial)
        base = Path(module)
        partial = f"{base.parent}/_{base.name}" if base.parent != Path(".") else f"_{module}"

        # Try various extensions
        for candidate_base in [module, partial]:
            for ext in [".scss", ".sass", ""]:
                candidate = f"{candidate_base}{ext}" if not candidate_base.endswith((".scss", ".sass")) else candidate_base
                if candidate in all_files:
                    return candidate

        # Try relative to source file
        source_dir = str(Path(source_file).parent)
        if source_dir != ".":
            for candidate_base in [module, partial]:
                for ext in [".scss", ".sass", ""]:
                    candidate = f"{source_dir}/{candidate_base}{ext}" if not candidate_base.endswith((".scss", ".sass")) else f"{source_dir}/{candidate_base}"
                    if candidate in all_files:
                        return candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format SCSS entry point for display."""
        if ep.type == "stylesheet":
            return f"  {ep.file}:{ep.name} (main stylesheet)"
        return super().format_entry_point(ep)
