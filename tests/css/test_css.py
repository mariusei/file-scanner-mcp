"""Tests for CSS scanner and analyzer."""

import pytest
from pathlib import Path

from scantool.scanners.css_scanner import CSSScanner
from scantool.analyzers.css_analyzer import CSSAnalyzer


@pytest.fixture
def css_scanner():
    """Create a CSS scanner instance."""
    return CSSScanner()


@pytest.fixture
def css_analyzer():
    """Create a CSS analyzer instance."""
    return CSSAnalyzer()


@pytest.fixture
def basic_css():
    """Load basic.css test file."""
    path = Path(__file__).parent / "basic.css"
    return path.read_bytes()


@pytest.fixture
def edge_cases_css():
    """Load edge_cases.css test file."""
    path = Path(__file__).parent / "edge_cases.css"
    return path.read_bytes()


@pytest.fixture
def broken_css():
    """Load broken.css test file."""
    path = Path(__file__).parent / "broken.css"
    return path.read_bytes()


class TestCSSScanner:
    """Tests for CSSScanner."""

    def test_get_extensions(self):
        """Test supported file extensions."""
        extensions = CSSScanner.get_extensions()
        assert ".css" in extensions

    def test_get_language_name(self):
        """Test language name."""
        assert CSSScanner.get_language_name() == "CSS"

    def test_should_skip_minified(self):
        """Test skipping minified files."""
        assert CSSScanner.should_skip("app.min.css") is True
        assert CSSScanner.should_skip("styles.css") is False

    def test_should_skip_sourcemap(self):
        """Test skipping source maps."""
        assert CSSScanner.should_skip("styles.css.map") is True

    def test_scan_basic_imports(self, css_scanner, basic_css):
        """Test @import extraction."""
        structures = css_scanner.scan(basic_css)
        assert structures is not None

        imports = [s for s in structures if s.type == "import"]
        assert len(imports) >= 2

    def test_scan_basic_root_variables(self, css_scanner, basic_css):
        """Test :root with CSS variables."""
        structures = css_scanner.scan(basic_css)
        assert structures is not None

        root_rules = [s for s in structures
                      if s.type == "rule_set" and "root" in s.modifiers]
        assert len(root_rules) >= 1
        assert "has-variables" in root_rules[0].modifiers

    def test_scan_basic_class_selectors(self, css_scanner, basic_css):
        """Test class selector extraction."""
        structures = css_scanner.scan(basic_css)
        assert structures is not None

        class_rules = [s for s in structures
                       if s.type == "rule_set" and "class" in s.modifiers]
        assert len(class_rules) >= 5

    def test_scan_basic_id_selectors(self, css_scanner, basic_css):
        """Test ID selector extraction."""
        structures = css_scanner.scan(basic_css)
        assert structures is not None

        id_rules = [s for s in structures
                    if s.type == "rule_set" and "id" in s.modifiers]
        assert len(id_rules) >= 1

    def test_scan_basic_media_queries(self, css_scanner, basic_css):
        """Test @media extraction."""
        structures = css_scanner.scan(basic_css)
        assert structures is not None

        media_queries = [s for s in structures if s.type == "media_query"]
        assert len(media_queries) >= 2

        # Check that media queries have nested rules
        responsive = next((m for m in media_queries if "768px" in (m.signature or "")), None)
        assert responsive is not None
        assert len(responsive.children) >= 1

    def test_scan_basic_keyframes(self, css_scanner, basic_css):
        """Test @keyframes extraction."""
        structures = css_scanner.scan(basic_css)
        assert structures is not None

        keyframes = [s for s in structures if s.type == "keyframes"]
        assert len(keyframes) >= 2

        fadein = next((k for k in keyframes if k.name == "fadeIn"), None)
        assert fadein is not None

    def test_scan_basic_font_face(self, css_scanner, basic_css):
        """Test @font-face extraction."""
        structures = css_scanner.scan(basic_css)
        assert structures is not None

        font_faces = [s for s in structures if s.type == "font_face"]
        assert len(font_faces) >= 1

    def test_scan_basic_important_comment(self, css_scanner, basic_css):
        """Test important comment extraction."""
        structures = css_scanner.scan(basic_css)
        assert structures is not None

        comments = [s for s in structures if s.type == "comment"]
        assert len(comments) >= 1

    def test_scan_edge_cases_long_selector(self, css_scanner, edge_cases_css):
        """Test long selector truncation."""
        structures = css_scanner.scan(edge_cases_css)
        assert structures is not None

        # Find a rule with truncated name
        long_rules = [s for s in structures
                      if s.type == "rule_set" and "..." in s.name]
        assert len(long_rules) >= 1

    def test_scan_edge_cases_multiple_selectors(self, css_scanner, edge_cases_css):
        """Test multiple selectors on one rule."""
        structures = css_scanner.scan(edge_cases_css)
        assert structures is not None

        # Find rule with multiple selectors
        multi = [s for s in structures
                 if s.type == "rule_set" and "(+" in s.name]
        assert len(multi) >= 1

    def test_scan_edge_cases_pseudo_selectors(self, css_scanner, edge_cases_css):
        """Test pseudo-class and pseudo-element selectors."""
        structures = css_scanner.scan(edge_cases_css)
        assert structures is not None

        pseudo_rules = [s for s in structures
                        if s.type == "rule_set" and "has-pseudo" in s.modifiers]
        assert len(pseudo_rules) >= 1

    def test_scan_edge_cases_nested_media(self, css_scanner, edge_cases_css):
        """Test nested @media with @supports."""
        structures = css_scanner.scan(edge_cases_css)
        assert structures is not None

        media_queries = [s for s in structures if s.type == "media_query"]
        assert len(media_queries) >= 1

    def test_scan_edge_cases_layer(self, css_scanner, edge_cases_css):
        """Test @layer rule extraction."""
        structures = css_scanner.scan(edge_cases_css)
        assert structures is not None

        layers = [s for s in structures if "layer" in s.modifiers]
        assert len(layers) >= 1

    def test_scan_edge_cases_container(self, css_scanner, edge_cases_css):
        """Test @container query extraction."""
        structures = css_scanner.scan(edge_cases_css)
        assert structures is not None

        containers = [s for s in structures if "container" in s.modifiers]
        assert len(containers) >= 1

    def test_scan_broken_css(self, css_scanner, broken_css):
        """Test parsing of broken CSS."""
        structures = css_scanner.scan(broken_css)
        assert structures is not None

        # Should still find valid structures
        assert len(structures) >= 1


class TestCSSAnalyzer:
    """Tests for CSSAnalyzer."""

    def test_get_extensions(self):
        """Test supported file extensions."""
        extensions = CSSAnalyzer.get_extensions()
        assert ".css" in extensions

    def test_get_language_name(self):
        """Test language name."""
        assert CSSAnalyzer.get_language_name() == "CSS"

    def test_extract_imports_at_import(self, css_analyzer, basic_css):
        """Test @import extraction."""
        content = basic_css.decode("utf-8")
        imports = css_analyzer.extract_imports("test.css", content)

        css_imports = [i for i in imports if i.import_type == "css_import"]
        assert len(css_imports) >= 2
        assert any("reset.css" in i.target_module for i in css_imports)
        assert any("buttons.css" in i.target_module for i in css_imports)

    def test_extract_imports_font_url(self, css_analyzer, basic_css):
        """Test font URL extraction."""
        content = basic_css.decode("utf-8")
        imports = css_analyzer.extract_imports("test.css", content)

        fonts = [i for i in imports if i.import_type == "font"]
        assert len(fonts) >= 1
        assert any("woff2" in i.target_module for i in fonts)

    def test_extract_imports_image_url(self, css_analyzer, edge_cases_css):
        """Test image URL extraction."""
        content = edge_cases_css.decode("utf-8")
        imports = css_analyzer.extract_imports("test.css", content)

        images = [i for i in imports if i.import_type == "image"]
        assert len(images) >= 1
        assert any("hero-bg.jpg" in i.target_module for i in images)

    def test_extract_imports_ignores_data_uri(self, css_analyzer, edge_cases_css):
        """Test that data URIs are ignored."""
        content = edge_cases_css.decode("utf-8")
        imports = css_analyzer.extract_imports("test.css", content)

        # Should not include data URIs
        for imp in imports:
            assert not imp.target_module.startswith("data:")

    def test_extract_imports_ignores_external(self, css_analyzer, edge_cases_css):
        """Test that external URLs are ignored."""
        content = edge_cases_css.decode("utf-8")
        imports = css_analyzer.extract_imports("test.css", content)

        # Should not include external URLs
        for imp in imports:
            assert "googleapis.com" not in imp.target_module

    def test_find_entry_points_main_stylesheet(self, css_analyzer, basic_css):
        """Test main stylesheet detection."""
        content = basic_css.decode("utf-8")
        entry_points = css_analyzer.find_entry_points("main.css", content)

        main_entries = [e for e in entry_points if e.type == "main_stylesheet"]
        assert len(main_entries) >= 1

    def test_find_entry_points_root_variables(self, css_analyzer, basic_css):
        """Test :root CSS variables detection."""
        content = basic_css.decode("utf-8")
        entry_points = css_analyzer.find_entry_points("styles.css", content)

        var_entries = [e for e in entry_points if e.type == "css_variables"]
        assert len(var_entries) >= 1
        assert "variables" in var_entries[0].name

    def test_classify_file_main(self, css_analyzer):
        """Test file classification for main stylesheets."""
        cluster = css_analyzer.classify_file("main.css", ":root {}")
        assert cluster == "entry_points"

    def test_classify_file_utilities(self, css_analyzer):
        """Test file classification for utility files."""
        cluster = css_analyzer.classify_file("utils.css", ".sr-only {}")
        assert cluster == "utilities"

    def test_classify_file_reset(self, css_analyzer):
        """Test file classification for reset files."""
        cluster = css_analyzer.classify_file("reset.css", "* { margin: 0; }")
        assert cluster == "utilities"

    def test_should_analyze_normal(self, css_analyzer):
        """Test normal files should be analyzed."""
        assert css_analyzer.should_analyze("styles.css") is True

    def test_should_analyze_minified(self, css_analyzer):
        """Test minified files should be skipped."""
        assert css_analyzer.should_analyze("app.min.css") is False

    def test_should_analyze_sourcemap(self, css_analyzer):
        """Test source maps should be skipped."""
        assert css_analyzer.should_analyze("styles.css.map") is False

    def test_is_low_value_small_file(self, css_analyzer):
        """Test small files are low value."""
        assert css_analyzer.is_low_value_for_inventory("stub.css", 30) is True

    def test_is_low_value_vendor(self, css_analyzer):
        """Test vendor files are low value."""
        assert css_analyzer.is_low_value_for_inventory("vendor.css", 5000) is True
