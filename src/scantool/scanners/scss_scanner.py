"""SCSS/SASS language scanner with structure and metadata extraction."""

import re
from pathlib import Path
from typing import Optional

import tree_sitter_scss
from tree_sitter import Language, Node, Parser

from .base import BaseScanner, StructureNode


class SCSSScanner(BaseScanner):
    """Scanner for SCSS/SASS files with mixin, function, and variable extraction."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_scss.language())

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".scss", ".sass"]

    @classmethod
    def get_language_name(cls) -> str:
        return "SCSS"

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
        # Track if this is a partial file
        filename = ""  # Will be set by caller if needed

        for node in root.children:
            if node.type == "ERROR":
                # Extract valid structures from within ERROR nodes
                # Tree-sitter often wraps valid SCSS in ERROR when there's a syntax issue
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
                import_node = self._extract_import(node, source_code)
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
                import_node = self._extract_import(child, source_code)
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
        var_value = None

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

    def _extract_import(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract @import/@use/@forward statement."""
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
