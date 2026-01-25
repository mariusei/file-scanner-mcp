"""CSS language support - unified scanner and analyzer.

This module combines CSSScanner and CSSAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output via _structures_to_definitions()
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_css
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class CSSLanguage(BaseLanguage):
    """Unified language handler for CSS files (.css).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract rules, at-rules, media queries, keyframes
    - extract_imports(): Find @import statements and url() references
    - find_entry_points(): Find main stylesheets and :root CSS variables
    - extract_definitions(): Convert scan() output to DefinitionInfo
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_css.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".css"]

    @classmethod
    def get_language_name(cls) -> str:
        return "CSS"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip minified and generated CSS files."""
        if filename.endswith(".min.css"):
            return True
        if filename.endswith(".css.map"):
            return True
        # Skip common generated patterns
        if any(pattern in filename.lower() for pattern in [
            ".generated.", ".compiled.", "bundle.", "chunk."
        ]):
            return True
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Skip CSS files that should not be analyzed.

        - Skip minified CSS files
        - Skip source maps
        - Skip generated/compiled files
        """
        filename = Path(file_path).name.lower()

        # Skip minified files
        if ".min." in filename:
            return False

        # Skip source maps
        if filename.endswith(".map"):
            return False

        # Skip common generated patterns
        if any(pattern in filename for pattern in [
            ".generated.", ".compiled.", "bundle.", "chunk."
        ]):
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value CSS files for inventory listing.

        Low-value files:
        - Very small files (likely stubs)
        - Vendor files
        """
        filename = Path(file_path).name.lower()

        # Very small CSS files
        if size < 50:
            return True

        # Vendor/third-party files
        if any(pattern in filename for pattern in [
            "vendor", "normalize", "reset", "bootstrap.min"
        ]):
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from CSSScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan CSS source code and extract structure with metadata."""
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
                print(f"CSS parsing error: {e}")
            if self.fallback_on_errors:
                return self._fallback_extract(source_code)
            return None

    def _extract_structure(
        self, root: Node, source_code: bytes
    ) -> list[StructureNode]:
        """Extract structure from CSS stylesheet."""
        structures = []

        for node in root.children:
            if node.type == "ERROR":
                # Extract valid structures from within ERROR nodes
                error_structures = self._extract_from_error_node(node, source_code)
                structures.extend(error_structures)
                continue

            # @import statements
            if node.type == "import_statement":
                import_node = self._extract_import_node(node, source_code)
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

            # @supports statements
            elif node.type == "supports_statement":
                supports_node = self._extract_supports(node, source_code)
                if supports_node:
                    structures.append(supports_node)

            # @font-face, @charset, @namespace, @layer, etc.
            elif node.type in ("at_rule", "font_face_statement", "charset_statement",
                               "namespace_statement", "layer_statement"):
                at_rule_node = self._extract_at_rule(node, source_code)
                if at_rule_node:
                    structures.append(at_rule_node)

            # Rule sets (selector { declarations })
            elif node.type == "rule_set":
                rule_node = self._extract_rule_set(node, source_code)
                if rule_node:
                    structures.append(rule_node)

            # Comments (only important ones with /*! */)
            elif node.type == "comment":
                comment_text = self._get_node_text(node, source_code)
                if comment_text.startswith("/*!"):
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
        """Extract valid CSS structures from within an ERROR node."""
        structures = []

        for child in error_node.children:
            if child.type == "ERROR":
                structures.extend(self._extract_from_error_node(child, source_code))
                continue

            if child.type == "import_statement":
                import_node = self._extract_import_node(child, source_code)
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

            elif child.type == "supports_statement":
                supports_node = self._extract_supports(child, source_code)
                if supports_node:
                    structures.append(supports_node)

            elif child.type in ("at_rule", "font_face_statement", "charset_statement",
                               "namespace_statement", "layer_statement"):
                at_rule_node = self._extract_at_rule(child, source_code)
                if at_rule_node:
                    structures.append(at_rule_node)

            elif child.type == "rule_set":
                rule_node = self._extract_rule_set(child, source_code)
                if rule_node:
                    structures.append(rule_node)

            elif child.type == "comment":
                comment_text = self._get_node_text(child, source_code)
                if comment_text.startswith("/*!"):
                    structures.append(StructureNode(
                        type="comment",
                        name=self._extract_comment_title(comment_text),
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        docstring=comment_text[:100]
                    ))

        return structures

    def _extract_import_node(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract @import statement as StructureNode."""
        url = None
        for child in node.children:
            if child.type == "call_expression":
                # url("...")
                for arg in child.children:
                    if arg.type == "arguments":
                        for string_node in arg.children:
                            if string_node.type == "string_value":
                                url = self._get_node_text(string_node, source_code).strip('"\'')
                                break
            elif child.type == "string_value":
                url = self._get_node_text(child, source_code).strip('"\'')

        if not url:
            return None

        return StructureNode(
            type="import",
            name=url,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=url,
            modifiers=["import"]
        )

    def _extract_media(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract @media statement."""
        query = None
        children = []

        for child in node.children:
            if child.type in ("keyword_query", "feature_query", "media_query_list",
                              "binary_query", "unary_query", "parenthesized_query"):
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
            children=children,
            complexity={"rules": len(children)} if children else None
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

    def _extract_supports(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract @supports statement."""
        query = None
        children = []

        for child in node.children:
            if child.type in ("feature_query", "parenthesized_query"):
                query = self._normalize_signature(
                    self._get_node_text(child, source_code)
                )
            elif child.type == "block":
                children = self._extract_nested_rules(child, source_code)

        return StructureNode(
            type="at_supports",
            name=query or "@supports",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=query,
            modifiers=["supports"],
            children=children
        )

    def _extract_at_rule(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract at-rule (@media, @keyframes, @import, etc.)."""
        keyword = None
        query = None
        children = []

        for child in node.children:
            if child.type == "at_keyword":
                keyword = self._get_node_text(child, source_code)
            elif child.type in ("keyword_query", "feature_query", "media_query"):
                query = self._normalize_signature(
                    self._get_node_text(child, source_code)
                )
            elif child.type == "keyframes_name":
                query = self._get_node_text(child, source_code)
            elif child.type == "block":
                children = self._extract_nested_rules(child, source_code)
            elif child.type in ("string_value", "call_expression"):
                query = self._get_node_text(child, source_code).strip('"\'')

        if not keyword:
            return None

        at_type = keyword.lstrip("@")

        # Determine node type based on at-rule type
        if at_type == "media":
            node_type = "media_query"
            name = query or "@media"
        elif at_type == "keyframes":
            node_type = "keyframes"
            name = query or "animation"
        elif at_type == "import":
            node_type = "import"
            name = query or "import"
        elif at_type == "font-face":
            node_type = "font_face"
            name = "@font-face"
        elif at_type in ("supports", "layer", "container"):
            node_type = f"at_{at_type}"
            name = query or f"@{at_type}"
        else:
            node_type = "at_rule"
            name = f"@{at_type}"

        return StructureNode(
            type=node_type,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=query,
            modifiers=[at_type],
            children=children,
            complexity={"rules": len(children)} if children else None
        )

    def _extract_nested_rules(
        self, block_node: Node, source_code: bytes
    ) -> list[StructureNode]:
        """Extract rules nested inside a block (e.g., @media)."""
        rules = []
        for child in block_node.children:
            if child.type == "rule_set":
                rule = self._extract_rule_set(child, source_code)
                if rule:
                    rules.append(rule)
            elif child.type == "at_rule":
                at_rule = self._extract_at_rule(child, source_code)
                if at_rule:
                    rules.append(at_rule)
        return rules

    def _extract_rule_set(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract a CSS rule set (selector + declarations)."""
        selectors = []
        declaration_count = 0
        has_variables = False
        modifiers = []

        for child in node.children:
            if child.type == "selectors":
                selectors = self._extract_selectors(child, source_code)
            elif child.type == "block":
                declaration_count, has_variables = self._count_declarations(
                    child, source_code
                )

        if not selectors:
            return None

        # Analyze selector complexity
        selector_text = ", ".join(selectors)
        if len(selector_text) > 60:
            selector_text = selector_text[:57] + "..."

        # Detect selector patterns
        if any(":root" in s for s in selectors):
            modifiers.append("root")
        if any(s.startswith(".") for s in selectors):
            modifiers.append("class")
        if any(s.startswith("#") for s in selectors):
            modifiers.append("id")
        if any(":" in s for s in selectors):
            modifiers.append("has-pseudo")
        if has_variables:
            modifiers.append("has-variables")

        # Use first selector as name, or combine if multiple
        if len(selectors) == 1:
            name = selectors[0]
        else:
            name = f"{selectors[0]} (+{len(selectors) - 1})"

        if len(name) > 50:
            name = name[:47] + "..."

        return StructureNode(
            type="rule_set",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"{len(selectors)} sel, {declaration_count} decl",
            modifiers=modifiers,
            complexity={"selectors": len(selectors), "declarations": declaration_count}
        )

    def _extract_selectors(
        self, selectors_node: Node, source_code: bytes
    ) -> list[str]:
        """Extract individual selectors from a selectors node."""
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

    def _count_declarations(
        self, block_node: Node, source_code: bytes
    ) -> tuple[int, bool]:
        """Count declarations and check for CSS variables."""
        count = 0
        has_variables = False

        for child in block_node.children:
            if child.type == "declaration":
                count += 1
                # Check for CSS custom properties (--var-name)
                for prop in child.children:
                    if prop.type == "property_name":
                        prop_name = self._get_node_text(prop, source_code)
                        if prop_name.startswith("--"):
                            has_variables = True

        return count, has_variables

    def _extract_comment_title(self, comment: str) -> str:
        """Extract a title from a comment."""
        text = comment.strip("/*! \n\r\t*/")
        first_line = text.split("\n")[0].strip()
        if len(first_line) > 50:
            first_line = first_line[:47] + "..."
        return first_line or "comment"

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for malformed CSS files."""
        text = source_code.decode("utf-8", errors="replace")
        structures = []

        # Find @import rules
        import_pattern = r'@import\s+(?:url\(["\']?([^"\')\s]+)["\']?\)|["\']([^"\']+)["\'])'
        for match in re.finditer(import_pattern, text, re.IGNORECASE):
            url = match.group(1) or match.group(2)
            line_num = text[:match.start()].count("\n") + 1
            structures.append(StructureNode(
                type="import",
                name=url,
                start_line=line_num,
                end_line=line_num,
                modifiers=["import"]
            ))

        # Find @media queries
        media_pattern = r'@media\s+([^{]+)\s*\{'
        for match in re.finditer(media_pattern, text, re.IGNORECASE):
            query = match.group(1).strip()
            line_num = text[:match.start()].count("\n") + 1
            structures.append(StructureNode(
                type="media_query",
                name=query[:50] + "..." if len(query) > 50 else query,
                start_line=line_num,
                end_line=line_num,
                signature=query,
                modifiers=["media"]
            ))

        # Find @keyframes
        keyframes_pattern = r'@keyframes\s+([^\s{]+)\s*\{'
        for match in re.finditer(keyframes_pattern, text, re.IGNORECASE):
            name = match.group(1)
            line_num = text[:match.start()].count("\n") + 1
            structures.append(StructureNode(
                type="keyframes",
                name=name,
                start_line=line_num,
                end_line=line_num,
                modifiers=["keyframes"]
            ))

        # Find @font-face
        fontface_pattern = r'@font-face\s*\{'
        for match in re.finditer(fontface_pattern, text, re.IGNORECASE):
            line_num = text[:match.start()].count("\n") + 1
            structures.append(StructureNode(
                type="font_face",
                name="@font-face",
                start_line=line_num,
                end_line=line_num,
                modifiers=["font-face"]
            ))

        # Find :root rule (CSS variables)
        root_pattern = r':root\s*\{'
        for match in re.finditer(root_pattern, text):
            line_num = text[:match.start()].count("\n") + 1
            structures.append(StructureNode(
                type="rule_set",
                name=":root",
                start_line=line_num,
                end_line=line_num,
                modifiers=["root", "has-variables"]
            ))

        # Find class selectors (common patterns)
        class_pattern = r'^\s*(\.[a-zA-Z_][\w-]*(?:\s*[,>+~]\s*[^{]+)?)\s*\{'
        for match in re.finditer(class_pattern, text, re.MULTILINE):
            selector = match.group(1).strip()
            line_num = text[:match.start()].count("\n") + 1
            if len(selector) > 50:
                selector = selector[:47] + "..."
            structures.append(StructureNode(
                type="rule_set",
                name=selector,
                start_line=line_num,
                end_line=line_num,
                modifiers=["class"]
            ))

        # Find ID selectors
        id_pattern = r'^\s*(#[a-zA-Z_][\w-]*(?:\s*[,>+~]\s*[^{]+)?)\s*\{'
        for match in re.finditer(id_pattern, text, re.MULTILINE):
            selector = match.group(1).strip()
            line_num = text[:match.start()].count("\n") + 1
            if len(selector) > 50:
                selector = selector[:47] + "..."
            structures.append(StructureNode(
                type="rule_set",
                name=selector,
                start_line=line_num,
                end_line=line_num,
                modifiers=["id"]
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from CSSAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from CSS file.

        Patterns supported:
        - @import url("...")
        - @import "..."
        - url(...) references in properties
        """
        imports = []

        # Pattern 1: @import statements
        import_pattern = r'@import\s+(?:url\(["\']?([^"\')\s]+)["\']?\)|["\']([^"\']+)["\'])'
        for match in re.finditer(import_pattern, content, re.IGNORECASE):
            url = match.group(1) or match.group(2)
            line_num = content[:match.start()].count("\n") + 1

            if self._is_external_url(url):
                continue

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=url,
                line=line_num,
                import_type="css_import",
                imported_names=[],
            ))

        # Pattern 2: url() references in properties (fonts, images, etc.)
        url_pattern = r'url\(["\']?([^"\')\s]+)["\']?\)'
        for match in re.finditer(url_pattern, content, re.IGNORECASE):
            url = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            # Skip data URIs and external URLs
            if url.startswith("data:") or self._is_external_url(url):
                continue

            # Determine asset type
            url_lower = url.lower()
            if any(ext in url_lower for ext in [".woff", ".woff2", ".ttf", ".otf", ".eot"]):
                import_type = "font"
            elif any(ext in url_lower for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]):
                import_type = "image"
            else:
                import_type = "asset"

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=url,
                line=line_num,
                import_type=import_type,
                imported_names=[],
            ))

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in CSS file.

        Entry points:
        - Main stylesheets (main.css, styles.css, app.css)
        - Files with :root CSS variables
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        # Check for main stylesheet files
        main_patterns = ["main.css", "styles.css", "style.css", "app.css", "global.css"]
        if filename in main_patterns:
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="main_stylesheet",
                name=filename,
                line=1,
                framework="CSS",
            ))

        # Check for :root with CSS variables
        root_pattern = r':root\s*\{([^}]+)\}'
        root_match = re.search(root_pattern, content, re.DOTALL)
        if root_match:
            line_num = content[:root_match.start()].count("\n") + 1
            # Count CSS variables
            var_count = root_match.group(1).count("--")
            if var_count > 0:
                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="css_variables",
                    name=f":root ({var_count} variables)",
                    line=line_num,
                ))

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract definitions by reusing scan() output.

        For CSS, definitions include rule sets, media queries, keyframes, etc.
        """
        try:
            structures = self.scan(content.encode("utf-8"))
            if not structures:
                return []
            return self._structures_to_definitions(file_path, structures)
        except Exception:
            return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """CSS doesn't have function calls - return empty list."""
        return []

    # ===========================================================================
    # Classification (enhanced for CSS)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify CSS file into architectural cluster."""
        cluster = super().classify_file(file_path, content)

        if cluster == "other":
            filename = Path(file_path).name.lower()

            # Check for main stylesheets
            if any(pattern in filename for pattern in ["main", "styles", "app", "global"]):
                return "entry_points"

            # Check for utility/helper stylesheets
            if any(pattern in filename for pattern in [
                "utils", "utility", "helpers", "mixins", "variables"
            ]):
                return "utilities"

            # Check for component stylesheets
            if any(pattern in filename for pattern in [
                "component", "button", "card", "modal", "form"
            ]):
                return "core_logic"

            # Check for reset/normalize
            if any(pattern in filename for pattern in ["reset", "normalize", "base"]):
                return "utilities"

        return cluster

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
        """Resolve CSS @import to file path.

        CSS imports are relative paths or URLs.
        """
        # Skip URLs
        if module.startswith(("http://", "https://", "//")):
            return None

        # Direct path match
        if module in all_files:
            return module

        # Try with .css extension
        if not module.endswith(".css"):
            candidate = f"{module}.css"
            if candidate in all_files:
                return candidate

        # Try relative to source file
        source_dir = str(Path(source_file).parent)
        if source_dir != ".":
            candidate = f"{source_dir}/{module}"
            if candidate in all_files:
                return candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format CSS entry point for display."""
        if ep.type == "main_stylesheet":
            return f"  {ep.file}:{ep.name} (main stylesheet)"
        elif ep.type == "css_variables":
            return f"  {ep.file}:{ep.name}"
        else:
            return super().format_entry_point(ep)

    # ===========================================================================
    # Helper methods
    # ===========================================================================

    def _is_external_url(self, url: str) -> bool:
        """Check if a URL is external (not a local file reference)."""
        if not url:
            return True

        # Check for protocol prefixes
        if url.startswith(("http://", "https://", "//", "data:", "blob:")):
            return True

        return False
