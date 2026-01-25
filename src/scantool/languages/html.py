"""HTML language support - unified scanner and analyzer.

This module combines HTMLScanner and HTMLAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_html
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


# Semantic HTML5 elements that define document structure
SEMANTIC_SECTIONS = {
    "header", "nav", "main", "footer", "article", "aside", "section"
}

# Form-related elements
FORM_ELEMENTS = {"form"}
FORM_CONTROLS = {"input", "select", "textarea", "button", "fieldset", "label"}

# Heading elements
HEADING_ELEMENTS = {"h1", "h2", "h3", "h4", "h5", "h6"}

# List elements
LIST_ELEMENTS = {"ul", "ol", "dl"}

# Table elements
TABLE_ELEMENTS = {"table"}

# Media elements
MEDIA_ELEMENTS = {"img", "video", "audio", "picture", "canvas", "svg"}

# Elements with external resources
RESOURCE_ELEMENTS = {"script", "style", "link"}


class HTMLLanguage(BaseLanguage):
    """Unified language handler for HTML files (.html, .htm, .xhtml).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract semantic sections, forms, headings, tables, scripts
    - extract_imports(): Find linked resources (scripts, stylesheets, images)
    - find_entry_points(): Find index files, DOCTYPE declarations
    - extract_definitions(): Convert scan() output to DefinitionInfo
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_html.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".html", ".htm", ".xhtml"]

    @classmethod
    def get_language_name(cls) -> str:
        return "HTML"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip minified and generated HTML files."""
        if filename.endswith(".min.html"):
            return True
        # Skip common generated/template cache files
        if any(pattern in filename.lower() for pattern in [
            ".cache.", ".generated.", ".compiled."
        ]):
            return True
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Skip HTML files that should not be analyzed.

        - Skip minified HTML files
        - Skip generated/compiled files
        """
        filename = Path(file_path).name.lower()

        # Skip minified files
        if ".min." in filename:
            return False

        # Skip common generated patterns
        if any(pattern in filename for pattern in [
            ".generated.", ".compiled.", ".cache."
        ]):
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value HTML files for inventory listing.

        Low-value files:
        - Very small files (likely stubs)
        - Common boilerplate files
        """
        filename = Path(file_path).name.lower()

        # Very small HTML files are likely stubs
        if size < 100:
            return True

        # Common boilerplate files
        if filename in ("404.html", "500.html", "error.html"):
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from HTMLScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan HTML source code and extract structure with metadata."""
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
                print(f"HTML parsing error: {e}")
            if self.fallback_on_errors:
                return self._fallback_extract(source_code)
            return None

    def _extract_structure(
        self, root: Node, source_code: bytes
    ) -> list[StructureNode]:
        """Extract structure from HTML document."""
        structures = []

        def traverse(node: Node, parent_list: list):
            """Recursively traverse and extract meaningful structures."""
            if node.type == "ERROR":
                # Continue traversing children of ERROR nodes to find valid structures
                # Tree-sitter often wraps valid HTML in ERROR when there's a syntax issue
                for child in node.children:
                    traverse(child, parent_list)
                return

            # DOCTYPE declaration
            if node.type == "doctype":
                parent_list.append(StructureNode(
                    type="doctype",
                    name="DOCTYPE",
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1
                ))

            # Element nodes
            elif node.type == "element":
                element_node = self._extract_element(node, source_code)
                if element_node:
                    parent_list.append(element_node)
                    # Traverse children for nested structures
                    for child in node.children:
                        traverse(child, element_node.children)
                else:
                    # Not a structural element, continue traversing
                    for child in node.children:
                        traverse(child, parent_list)

            # Script and style elements (self-contained)
            elif node.type in ("script_element", "style_element"):
                resource_node = self._extract_resource_element(node, source_code)
                if resource_node:
                    parent_list.append(resource_node)

            # Continue traversing for other node types
            else:
                for child in node.children:
                    traverse(child, parent_list)

        traverse(root, structures)
        return structures

    def _extract_element(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract a structural HTML element."""
        tag_name = self._get_tag_name(node, source_code)
        if not tag_name:
            return None

        tag_lower = tag_name.lower()

        # Determine if this is a structural element worth extracting
        if tag_lower in SEMANTIC_SECTIONS:
            return self._create_section_node(node, source_code, tag_lower)
        elif tag_lower in FORM_ELEMENTS:
            return self._create_form_node(node, source_code)
        elif tag_lower in HEADING_ELEMENTS:
            return self._create_heading_node(node, source_code, tag_lower)
        elif tag_lower in LIST_ELEMENTS:
            return self._create_list_node(node, source_code, tag_lower)
        elif tag_lower in TABLE_ELEMENTS:
            return self._create_table_node(node, source_code)

        # Check for elements with id attribute (landmarks)
        attrs = self._extract_attributes(node, source_code)
        if attrs.get("id"):
            return self._create_landmark_node(node, source_code, tag_lower, attrs)

        return None

    def _get_tag_name(self, node: Node, source_code: bytes) -> Optional[str]:
        """Get the tag name from an element node."""
        for child in node.children:
            if child.type == "start_tag":
                for tag_child in child.children:
                    if tag_child.type == "tag_name":
                        return self._get_node_text(tag_child, source_code)
            elif child.type == "self_closing_tag":
                for tag_child in child.children:
                    if tag_child.type == "tag_name":
                        return self._get_node_text(tag_child, source_code)
        return None

    def _extract_attributes(
        self, node: Node, source_code: bytes
    ) -> dict[str, str]:
        """Extract attributes from an element."""
        attrs = {}
        for child in node.children:
            if child.type in ("start_tag", "self_closing_tag"):
                for attr_node in child.children:
                    if attr_node.type == "attribute":
                        name = None
                        value = None
                        for attr_child in attr_node.children:
                            if attr_child.type == "attribute_name":
                                name = self._get_node_text(attr_child, source_code)
                            elif attr_child.type in (
                                "attribute_value", "quoted_attribute_value"
                            ):
                                value = self._get_node_text(
                                    attr_child, source_code
                                ).strip('"\'')
                        if name:
                            attrs[name.lower()] = value or ""
        return attrs

    def _create_section_node(
        self, node: Node, source_code: bytes, tag_name: str
    ) -> StructureNode:
        """Create a node for semantic section elements."""
        attrs = self._extract_attributes(node, source_code)
        name = attrs.get("id") or attrs.get("aria-label") or tag_name

        signature_parts = []
        if attrs.get("id"):
            signature_parts.append(f"#{attrs['id']}")
        if attrs.get("class"):
            classes = attrs["class"].split()[:3]  # First 3 classes
            signature_parts.extend(f".{c}" for c in classes)

        return StructureNode(
            type="section",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=" ".join(signature_parts) if signature_parts else None,
            docstring=attrs.get("aria-label") or attrs.get("title"),
            modifiers=[tag_name],
            children=[]
        )

    def _create_form_node(
        self, node: Node, source_code: bytes
    ) -> StructureNode:
        """Create a node for form elements."""
        attrs = self._extract_attributes(node, source_code)
        name = attrs.get("id") or attrs.get("name") or "form"
        method = attrs.get("method", "GET").upper()
        action = attrs.get("action", "#")

        # Count form controls
        control_count = self._count_form_controls(node, source_code)

        return StructureNode(
            type="form",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"{method} {action}",
            docstring=attrs.get("aria-label") or attrs.get("title"),
            modifiers=[method.lower()],
            complexity={"fields": control_count},
            children=[]
        )

    def _count_form_controls(self, node: Node, source_code: bytes) -> int:
        """Count form control elements within a form."""
        count = 0

        def count_controls(n: Node):
            nonlocal count
            if n.type == "element":
                tag = self._get_tag_name(n, source_code)
                if tag and tag.lower() in FORM_CONTROLS:
                    count += 1
            for child in n.children:
                count_controls(child)

        count_controls(node)
        return count

    def _create_heading_node(
        self, node: Node, source_code: bytes, tag_name: str
    ) -> StructureNode:
        """Create a node for heading elements."""
        level = int(tag_name[1])  # h1 -> 1, h2 -> 2, etc.
        text = self._extract_text_content(node, source_code)
        attrs = self._extract_attributes(node, source_code)

        name = text[:50] + "..." if len(text) > 50 else text
        if not name.strip():
            name = f"(empty {tag_name})"

        return StructureNode(
            type="heading",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"H{level}",
            docstring=attrs.get("id"),
            children=[]
        )

    def _create_list_node(
        self, node: Node, source_code: bytes, tag_name: str
    ) -> StructureNode:
        """Create a node for list elements."""
        attrs = self._extract_attributes(node, source_code)
        list_type = "ordered" if tag_name == "ol" else (
            "definition" if tag_name == "dl" else "unordered"
        )

        # Count list items
        item_count = self._count_list_items(node, tag_name)

        name = attrs.get("id") or f"{list_type} list"

        return StructureNode(
            type="list",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"{item_count} items",
            modifiers=[list_type],
            children=[]
        )

    def _count_list_items(self, node: Node, tag_name: str) -> int:
        """Count items in a list."""
        item_tag = "dt" if tag_name == "dl" else "li"
        count = 0

        def count_items(n: Node):
            nonlocal count
            if n.type == "element":
                for child in n.children:
                    if child.type == "start_tag":
                        for tag_child in child.children:
                            if tag_child.type == "tag_name":
                                if self._get_node_text(
                                    tag_child, n.text
                                ).lower() == item_tag:
                                    count += 1
            for child in n.children:
                count_items(child)

        count_items(node)
        return count

    def _create_table_node(
        self, node: Node, source_code: bytes
    ) -> StructureNode:
        """Create a node for table elements."""
        attrs = self._extract_attributes(node, source_code)
        name = attrs.get("id") or "table"

        # Count rows and columns
        rows, cols = self._count_table_dimensions(node, source_code)

        return StructureNode(
            type="table",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"{rows}x{cols}" if cols > 0 else f"{rows} rows",
            docstring=attrs.get("aria-label") or attrs.get("summary"),
            children=[]
        )

    def _count_table_dimensions(
        self, node: Node, source_code: bytes
    ) -> tuple[int, int]:
        """Count rows and columns in a table."""
        rows = 0
        max_cols = 0

        def traverse(n: Node):
            nonlocal rows, max_cols
            tag = self._get_tag_name(n, source_code) if n.type == "element" else None

            if tag and tag.lower() == "tr":
                rows += 1
                cols = 0
                for child in n.children:
                    child_tag = (
                        self._get_tag_name(child, source_code)
                        if child.type == "element" else None
                    )
                    if child_tag and child_tag.lower() in ("td", "th"):
                        cols += 1
                max_cols = max(max_cols, cols)

            for child in n.children:
                traverse(child)

        traverse(node)
        return rows, max_cols

    def _create_landmark_node(
        self, node: Node, source_code: bytes, tag_name: str, attrs: dict
    ) -> StructureNode:
        """Create a node for elements with id (landmarks)."""
        name = attrs.get("id", tag_name)

        signature_parts = [f"<{tag_name}>"]
        if attrs.get("class"):
            classes = attrs["class"].split()[:2]
            signature_parts.extend(f".{c}" for c in classes)

        return StructureNode(
            type="element",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=" ".join(signature_parts),
            docstring=attrs.get("title") or attrs.get("aria-label"),
            modifiers=[tag_name],
            children=[]
        )

    def _extract_resource_element(
        self, node: Node, source_code: bytes
    ) -> Optional[StructureNode]:
        """Extract script or style element."""
        is_script = node.type == "script_element"
        element_type = "script" if is_script else "style"

        # Find the start tag to get attributes
        attrs = {}
        for child in node.children:
            if child.type == "start_tag":
                for attr_node in child.children:
                    if attr_node.type == "attribute":
                        name = None
                        value = None
                        for attr_child in attr_node.children:
                            if attr_child.type == "attribute_name":
                                name = self._get_node_text(attr_child, source_code)
                            elif attr_child.type in (
                                "attribute_value", "quoted_attribute_value"
                            ):
                                value = self._get_node_text(
                                    attr_child, source_code
                                ).strip('"\'')
                        if name:
                            attrs[name.lower()] = value or ""

        if is_script:
            src = attrs.get("src", "")
            name = src.split("/")[-1] if src else "inline"
            signature = src if src else "inline script"
            modifiers = []
            if attrs.get("type"):
                modifiers.append(attrs["type"])
            if attrs.get("async") is not None:
                modifiers.append("async")
            if attrs.get("defer") is not None:
                modifiers.append("defer")
        else:
            media = attrs.get("media", "")
            name = attrs.get("id", "style")
            signature = f"media={media}" if media else None
            modifiers = [media] if media else []

        return StructureNode(
            type=element_type,
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            modifiers=modifiers,
            children=[]
        )

    def _extract_text_content(self, node: Node, source_code: bytes) -> str:
        """Extract text content from an element, excluding nested tags."""
        text_parts = []

        def collect_text(n: Node):
            if n.type == "text":
                text_parts.append(self._get_node_text(n, source_code))
            for child in n.children:
                collect_text(child)

        collect_text(node)
        return " ".join(text_parts).strip()

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for malformed HTML files."""
        text = source_code.decode("utf-8", errors="replace")
        structures = []

        # Find DOCTYPE
        doctype_match = re.search(r'<!DOCTYPE[^>]*>', text, re.IGNORECASE)
        if doctype_match:
            line_num = text[:doctype_match.start()].count("\n") + 1
            structures.append(StructureNode(
                type="doctype",
                name="DOCTYPE",
                start_line=line_num,
                end_line=line_num
            ))

        # Find headings
        heading_pattern = r'<(h[1-6])[^>]*>(.*?)</\1>'
        for match in re.finditer(heading_pattern, text, re.IGNORECASE | re.DOTALL):
            tag = match.group(1).lower()
            content = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            line_num = text[:match.start()].count("\n") + 1
            level = int(tag[1])

            name = content[:50] + "..." if len(content) > 50 else content
            if not name:
                name = f"(empty {tag})"

            structures.append(StructureNode(
                type="heading",
                name=name,
                start_line=line_num,
                end_line=line_num,
                signature=f"H{level}"
            ))

        # Find forms
        form_pattern = r'<form([^>]*)>'
        for match in re.finditer(form_pattern, text, re.IGNORECASE):
            attrs_str = match.group(1)
            line_num = text[:match.start()].count("\n") + 1

            # Extract id/name/method/action from attributes
            id_match = re.search(r'id=["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
            method_match = re.search(
                r'method=["\']([^"\']+)["\']', attrs_str, re.IGNORECASE
            )
            action_match = re.search(
                r'action=["\']([^"\']+)["\']', attrs_str, re.IGNORECASE
            )

            name = id_match.group(1) if id_match else "form"
            method = method_match.group(1).upper() if method_match else "GET"
            action = action_match.group(1) if action_match else "#"

            structures.append(StructureNode(
                type="form",
                name=name,
                start_line=line_num,
                end_line=line_num,
                signature=f"{method} {action}",
                modifiers=[method.lower()]
            ))

        # Find semantic sections
        section_pattern = r'<(header|nav|main|footer|article|aside|section)([^>]*)>'
        for match in re.finditer(section_pattern, text, re.IGNORECASE):
            tag = match.group(1).lower()
            attrs_str = match.group(2)
            line_num = text[:match.start()].count("\n") + 1

            id_match = re.search(r'id=["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
            name = id_match.group(1) if id_match else tag

            structures.append(StructureNode(
                type="section",
                name=name,
                start_line=line_num,
                end_line=line_num,
                modifiers=[tag]
            ))

        # Find scripts with src
        script_pattern = r'<script([^>]*)>'
        for match in re.finditer(script_pattern, text, re.IGNORECASE):
            attrs_str = match.group(1)
            line_num = text[:match.start()].count("\n") + 1

            src_match = re.search(r'src=["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
            if src_match:
                src = src_match.group(1)
                name = src.split("/")[-1]
                structures.append(StructureNode(
                    type="script",
                    name=name,
                    start_line=line_num,
                    end_line=line_num,
                    signature=src
                ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from HTMLAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract resource imports from HTML file.

        Patterns supported:
        - <link href="..."> (stylesheets, icons)
        - <script src="..."> (JavaScript files)
        - <img src="..."> (images)
        - <a href="..."> (local page links)
        - CSS @import in <style> blocks
        """
        imports = []

        # Pattern 1: <link href="...">
        link_pattern = r'<link[^>]+href=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(link_pattern, content, re.IGNORECASE):
            href = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            # Determine link type from rel attribute
            rel_match = re.search(
                r'rel=["\']([^"\']+)["\']',
                match.group(0),
                re.IGNORECASE
            )
            rel = rel_match.group(1) if rel_match else "unknown"

            # Skip external URLs for import tracking
            if self._is_external_url(href):
                continue

            import_type = "stylesheet" if "stylesheet" in rel.lower() else (
                "icon" if "icon" in rel.lower() else "link"
            )

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=href,
                line=line_num,
                import_type=import_type,
                imported_names=[],
            ))

        # Pattern 2: <script src="...">
        script_pattern = r'<script[^>]+src=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(script_pattern, content, re.IGNORECASE):
            src = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            if self._is_external_url(src):
                continue

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=src,
                line=line_num,
                import_type="script",
                imported_names=[],
            ))

        # Pattern 3: <img src="..."> (for asset tracking)
        img_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
        for match in re.finditer(img_pattern, content, re.IGNORECASE):
            src = match.group(1)
            line_num = content[:match.start()].count("\n") + 1

            if self._is_external_url(src):
                continue

            # Only track local images
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=src,
                line=line_num,
                import_type="image",
                imported_names=[],
            ))

        # Pattern 4: CSS @import in <style> blocks
        style_pattern = r'<style[^>]*>(.*?)</style>'
        for style_match in re.finditer(style_pattern, content, re.IGNORECASE | re.DOTALL):
            style_content = style_match.group(1)
            style_start = content[:style_match.start()].count("\n")

            import_pattern = r'@import\s+(?:url\(["\']?([^"\')\s]+)["\']?\)|["\']([^"\']+)["\'])'
            for import_match in re.finditer(import_pattern, style_content, re.IGNORECASE):
                url = import_match.group(1) or import_match.group(2)
                line_num = style_start + style_content[:import_match.start()].count("\n") + 1

                if not self._is_external_url(url):
                    imports.append(ImportInfo(
                        source_file=file_path,
                        target_module=url,
                        line=line_num,
                        import_type="css_import",
                        imported_names=[],
                    ))

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Find entry points in HTML file.

        Entry points:
        - index.html files (main entry)
        - Files with <!DOCTYPE html>
        - Files with <html> root element
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        # Check for index files (common entry points)
        if filename in ("index.html", "index.htm", "default.html", "default.htm"):
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="html_entry",
                name="index",
                line=1,
                framework="HTML",
            ))

        # Check for DOCTYPE (indicates complete HTML document)
        doctype_pattern = r'<!DOCTYPE\s+html'
        doctype_match = re.search(doctype_pattern, content, re.IGNORECASE)
        if doctype_match:
            line_num = content[:doctype_match.start()].count("\n") + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="html_document",
                name="DOCTYPE html",
                line=line_num,
            ))

        # Check for meta viewport (indicates responsive web page)
        viewport_pattern = r'<meta[^>]+name=["\']viewport["\'][^>]*>'
        viewport_match = re.search(viewport_pattern, content, re.IGNORECASE)
        if viewport_match:
            line_num = content[:viewport_match.start()].count("\n") + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="responsive_page",
                name="viewport meta",
                line=line_num,
            ))

        return entry_points

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract structural definitions by reusing scan() output.

        This is the key optimization: instead of re-parsing with tree-sitter,
        we convert the StructureNode output from scan() to DefinitionInfo.
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
        """HTML doesn't have function calls in the traditional sense.

        Could be extended to track:
        - JavaScript function calls in inline scripts
        - Event handler references (onclick, etc.)

        For now, returns empty list.
        """
        return []

    # ===========================================================================
    # Classification (enhanced for HTML)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify HTML file into architectural cluster.

        Enhanced classification with HTML-specific patterns.
        """
        # Use base implementation first
        cluster = super().classify_file(file_path, content)

        if cluster == "other":
            filename = Path(file_path).name.lower()

            # Check for index/entry pages
            if filename in ("index.html", "index.htm", "default.html"):
                return "entry_points"

            # Check for error pages
            if any(err in filename for err in ["404", "500", "error"]):
                return "utilities"

            # Check for template files
            if "template" in filename or "_partial" in filename:
                return "utilities"

            # Check for test/demo pages
            if any(pattern in filename for pattern in ["test", "demo", "example"]):
                return "tests"

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
        """Resolve HTML resource reference to file path.

        HTML imports are typically relative paths to JS, CSS, images.
        """
        # Skip URLs and data URIs
        if module.startswith(("http://", "https://", "//", "data:", "mailto:")):
            return None

        # Direct match
        if module in all_files:
            return module

        # Try relative to source file
        source_dir = str(Path(source_file).parent)
        if source_dir != ".":
            candidate = f"{source_dir}/{module}"
            if candidate in all_files:
                return candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format HTML entry point for display.

        Formats:
        - index: "index.html"
        - doctype: "DOCTYPE html @line"
        - viewport: "viewport meta @line"
        """
        if ep.type == "html_entry":
            return f"  {ep.file}:index @{ep.line}"
        elif ep.type == "html_document":
            return f"  {ep.file}:DOCTYPE html @{ep.line}"
        elif ep.type == "responsive_page":
            return f"  {ep.file}:viewport meta @{ep.line}"
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

        # Check for CDN patterns
        if any(cdn in url.lower() for cdn in [
            "cdn.", "cdnjs.", "unpkg.com", "jsdelivr.net",
            "googleapis.com", "cloudflare.com"
        ]):
            return True

        return False
