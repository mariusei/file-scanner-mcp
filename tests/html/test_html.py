"""Tests for HTML scanner and analyzer."""

import pytest
from pathlib import Path

from scantool.scanners.html_scanner import HTMLScanner
from scantool.analyzers.html_analyzer import HTMLAnalyzer


@pytest.fixture
def html_scanner():
    """Create an HTML scanner instance."""
    return HTMLScanner()


@pytest.fixture
def html_analyzer():
    """Create an HTML analyzer instance."""
    return HTMLAnalyzer()


@pytest.fixture
def basic_html():
    """Load basic.html test file."""
    path = Path(__file__).parent / "basic.html"
    return path.read_bytes()


@pytest.fixture
def edge_cases_html():
    """Load edge_cases.html test file."""
    path = Path(__file__).parent / "edge_cases.html"
    return path.read_bytes()


@pytest.fixture
def broken_html():
    """Load broken.html test file."""
    path = Path(__file__).parent / "broken.html"
    return path.read_bytes()


class TestHTMLScanner:
    """Tests for HTMLScanner."""

    def test_get_extensions(self):
        """Test supported file extensions."""
        extensions = HTMLScanner.get_extensions()
        assert ".html" in extensions
        assert ".htm" in extensions
        assert ".xhtml" in extensions

    def test_get_language_name(self):
        """Test language name."""
        assert HTMLScanner.get_language_name() == "HTML"

    def test_should_skip_minified(self):
        """Test skipping minified files."""
        assert HTMLScanner.should_skip("app.min.html") is True
        assert HTMLScanner.should_skip("index.html") is False

    def test_scan_basic_doctype(self, html_scanner, basic_html):
        """Test DOCTYPE extraction."""
        structures = html_scanner.scan(basic_html)
        assert structures is not None

        doctypes = [s for s in structures if s.type == "doctype"]
        assert len(doctypes) == 1
        assert doctypes[0].name == "DOCTYPE"

    def test_scan_basic_sections(self, html_scanner, basic_html):
        """Test semantic section extraction."""
        structures = html_scanner.scan(basic_html)
        assert structures is not None

        sections = [s for s in structures if s.type == "section"]
        section_names = [s.name for s in sections]

        # Check main semantic sections
        assert "main-header" in section_names
        assert "content" in section_names
        assert "main-footer" in section_names

    def test_scan_basic_headings(self, html_scanner, basic_html):
        """Test heading extraction."""
        structures = html_scanner.scan(basic_html)
        assert structures is not None

        # Find headings recursively
        def find_headings(nodes):
            headings = []
            for node in nodes:
                if node.type == "heading":
                    headings.append(node)
                headings.extend(find_headings(node.children))
            return headings

        headings = find_headings(structures)
        assert len(headings) >= 3  # h1, h2, h2

        h1_headings = [h for h in headings if h.signature == "H1"]
        assert len(h1_headings) >= 1
        assert "Welcome" in h1_headings[0].name

    def test_scan_basic_forms(self, html_scanner, basic_html):
        """Test form extraction."""
        structures = html_scanner.scan(basic_html)
        assert structures is not None

        # Find forms recursively
        def find_forms(nodes):
            forms = []
            for node in nodes:
                if node.type == "form":
                    forms.append(node)
                forms.extend(find_forms(node.children))
            return forms

        forms = find_forms(structures)
        assert len(forms) >= 1

        contact_form = next((f for f in forms if f.name == "contact-form"), None)
        assert contact_form is not None
        assert contact_form.signature == "POST /api/contact"
        assert "post" in contact_form.modifiers

    def test_scan_basic_lists(self, html_scanner, basic_html):
        """Test list extraction."""
        structures = html_scanner.scan(basic_html)
        assert structures is not None

        # Find lists recursively
        def find_lists(nodes):
            lists = []
            for node in nodes:
                if node.type == "list":
                    lists.append(node)
                lists.extend(find_lists(node.children))
            return lists

        lists = find_lists(structures)
        assert len(lists) >= 2  # ul and ol

        feature_list = next((l for l in lists if l.name == "feature-list"), None)
        assert feature_list is not None
        assert "unordered" in feature_list.modifiers

    def test_scan_scripts_and_styles(self, html_scanner, basic_html):
        """Test script and style extraction."""
        structures = html_scanner.scan(basic_html)
        assert structures is not None

        scripts = [s for s in structures if s.type == "script"]
        styles = [s for s in structures if s.type == "style"]

        assert len(scripts) >= 1
        assert any("app.js" in s.name for s in scripts)

        assert len(styles) >= 1

    def test_scan_edge_cases_empty_heading(self, html_scanner, edge_cases_html):
        """Test handling of empty headings."""
        structures = html_scanner.scan(edge_cases_html)
        assert structures is not None

        def find_headings(nodes):
            headings = []
            for node in nodes:
                if node.type == "heading":
                    headings.append(node)
                headings.extend(find_headings(node.children))
            return headings

        headings = find_headings(structures)
        empty_h1 = [h for h in headings if "(empty h1)" in h.name]
        assert len(empty_h1) >= 1

    def test_scan_edge_cases_truncated_heading(self, html_scanner, edge_cases_html):
        """Test heading truncation for long text."""
        structures = html_scanner.scan(edge_cases_html)
        assert structures is not None

        def find_headings(nodes):
            headings = []
            for node in nodes:
                if node.type == "heading":
                    headings.append(node)
                headings.extend(find_headings(node.children))
            return headings

        headings = find_headings(structures)
        long_heading = [h for h in headings if "..." in h.name]
        assert len(long_heading) >= 1
        assert len(long_heading[0].name) <= 54  # 50 chars + "..."

    def test_scan_edge_cases_nested_sections(self, html_scanner, edge_cases_html):
        """Test nested semantic sections."""
        structures = html_scanner.scan(edge_cases_html)
        assert structures is not None

        # Find the nested article
        def find_by_name(nodes, name):
            for node in nodes:
                if node.name == name:
                    return node
                result = find_by_name(node.children, name)
                if result:
                    return result
            return None

        article = find_by_name(structures, "nested-article")
        assert article is not None
        assert len(article.children) > 0

    def test_scan_edge_cases_multiple_forms(self, html_scanner, edge_cases_html):
        """Test multiple forms extraction."""
        structures = html_scanner.scan(edge_cases_html)
        assert structures is not None

        def find_forms(nodes):
            forms = []
            for node in nodes:
                if node.type == "form":
                    forms.append(node)
                forms.extend(find_forms(node.children))
            return forms

        forms = find_forms(structures)
        assert len(forms) >= 3  # search-form, newsletter, anonymous

    def test_scan_edge_cases_table(self, html_scanner, edge_cases_html):
        """Test table extraction with dimensions."""
        structures = html_scanner.scan(edge_cases_html)
        assert structures is not None

        def find_tables(nodes):
            tables = []
            for node in nodes:
                if node.type == "table":
                    tables.append(node)
                tables.extend(find_tables(node.children))
            return tables

        tables = find_tables(structures)
        data_table = next((t for t in tables if t.name == "data-table"), None)
        assert data_table is not None
        assert "4x4" in data_table.signature or "4 rows" in data_table.signature

    def test_scan_edge_cases_element_with_id(self, html_scanner, edge_cases_html):
        """Test element extraction for landmarks with id."""
        structures = html_scanner.scan(edge_cases_html)
        assert structures is not None

        def find_elements(nodes):
            elements = []
            for node in nodes:
                if node.type == "element":
                    elements.append(node)
                elements.extend(find_elements(node.children))
            return elements

        elements = find_elements(structures)
        important = next((e for e in elements if e.name == "important-element"), None)
        assert important is not None

    def test_scan_broken_html_fallback(self, html_scanner, broken_html):
        """Test fallback parsing for broken HTML."""
        # Should not crash and should extract what it can
        structures = html_scanner.scan(broken_html)
        assert structures is not None

        # tree-sitter-html is very tolerant, so it may parse successfully
        # The important thing is that we don't crash and return something
        # Either tree-sitter finds structures OR fallback does
        def count_all(nodes):
            count = len(nodes)
            for node in nodes:
                count += count_all(node.children)
            return count

        # Should have at least DOCTYPE
        total = count_all(structures)
        assert total >= 1  # At minimum we should find the DOCTYPE


class TestHTMLAnalyzer:
    """Tests for HTMLAnalyzer."""

    def test_get_extensions(self):
        """Test supported file extensions."""
        extensions = HTMLAnalyzer.get_extensions()
        assert ".html" in extensions
        assert ".htm" in extensions

    def test_get_language_name(self):
        """Test language name."""
        assert HTMLAnalyzer.get_language_name() == "HTML"

    def test_extract_imports_link(self, html_analyzer, basic_html):
        """Test stylesheet and icon import extraction."""
        content = basic_html.decode("utf-8")
        imports = html_analyzer.extract_imports("test.html", content)

        # Find stylesheet import
        stylesheets = [i for i in imports if i.import_type == "stylesheet"]
        assert len(stylesheets) >= 1
        assert any("main.css" in i.target_module for i in stylesheets)

        # Find icon import
        icons = [i for i in imports if i.import_type == "icon"]
        assert len(icons) >= 1

    def test_extract_imports_script(self, html_analyzer, basic_html):
        """Test script import extraction."""
        content = basic_html.decode("utf-8")
        imports = html_analyzer.extract_imports("test.html", content)

        scripts = [i for i in imports if i.import_type == "script"]
        assert len(scripts) >= 1
        assert any("app.js" in i.target_module for i in scripts)

    def test_extract_imports_css_import(self, html_analyzer, basic_html):
        """Test CSS @import extraction from style blocks."""
        content = basic_html.decode("utf-8")
        imports = html_analyzer.extract_imports("test.html", content)

        css_imports = [i for i in imports if i.import_type == "css_import"]
        assert len(css_imports) >= 1
        assert any("buttons.css" in i.target_module for i in css_imports)

    def test_extract_imports_ignores_external(self, html_analyzer, edge_cases_html):
        """Test that external URLs are ignored."""
        content = edge_cases_html.decode("utf-8")
        imports = html_analyzer.extract_imports("test.html", content)

        # Should not include CDN URLs
        for imp in imports:
            assert "cdn.example.com" not in imp.target_module
            assert "cdnjs.cloudflare.com" not in imp.target_module
            assert "googleapis.com" not in imp.target_module

    def test_find_entry_points_index(self, html_analyzer, basic_html):
        """Test entry point detection for index files."""
        content = basic_html.decode("utf-8")
        entry_points = html_analyzer.find_entry_points("index.html", content)

        html_entries = [e for e in entry_points if e.type == "html_entry"]
        assert len(html_entries) >= 1

    def test_find_entry_points_doctype(self, html_analyzer, basic_html):
        """Test DOCTYPE detection as entry point."""
        content = basic_html.decode("utf-8")
        entry_points = html_analyzer.find_entry_points("page.html", content)

        doctypes = [e for e in entry_points if e.type == "html_document"]
        assert len(doctypes) >= 1

    def test_find_entry_points_viewport(self, html_analyzer, basic_html):
        """Test viewport meta detection."""
        content = basic_html.decode("utf-8")
        entry_points = html_analyzer.find_entry_points("page.html", content)

        viewports = [e for e in entry_points if e.type == "responsive_page"]
        assert len(viewports) >= 1

    def test_classify_file_index(self, html_analyzer):
        """Test file classification for index files."""
        cluster = html_analyzer.classify_file("index.html", "<!DOCTYPE html>")
        assert cluster == "entry_points"

    def test_classify_file_error(self, html_analyzer):
        """Test file classification for error pages."""
        cluster = html_analyzer.classify_file("404.html", "<!DOCTYPE html>")
        assert cluster == "utilities"

    def test_should_analyze_normal(self, html_analyzer):
        """Test normal files should be analyzed."""
        assert html_analyzer.should_analyze("page.html") is True

    def test_should_analyze_minified(self, html_analyzer):
        """Test minified files should be skipped."""
        assert html_analyzer.should_analyze("app.min.html") is False

    def test_is_low_value_small_file(self, html_analyzer):
        """Test small files are low value."""
        assert html_analyzer.is_low_value_for_inventory("stub.html", 50) is True

    def test_is_low_value_error_page(self, html_analyzer):
        """Test error pages are low value."""
        assert html_analyzer.is_low_value_for_inventory("404.html", 500) is True
