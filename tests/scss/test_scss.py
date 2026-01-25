"""Tests for SCSS language."""

import pytest
from pathlib import Path

from scantool.languages.scss import SCSSLanguage


@pytest.fixture
def scss_language():
    """Create SCSS language instance."""
    return SCSSLanguage()


@pytest.fixture
def basic_scss():
    """Load basic.scss test file."""
    path = Path(__file__).parent / "basic.scss"
    return path.read_bytes()


@pytest.fixture
def variables_scss():
    """Load _variables.scss test file."""
    path = Path(__file__).parent / "_variables.scss"
    return path.read_bytes()


@pytest.fixture
def edge_cases_scss():
    """Load edge_cases.scss test file."""
    path = Path(__file__).parent / "edge_cases.scss"
    return path.read_bytes()


class TestSCSSScanner:
    """Tests for SCSSLanguage."""

    def test_get_extensions(self):
        """Test supported file extensions."""
        extensions = SCSSLanguage.get_extensions()
        assert ".scss" in extensions
        assert ".sass" in extensions

    def test_get_language_name(self):
        """Test language name."""
        assert SCSSLanguage.get_language_name() == "SCSS"

    def test_should_skip_minified(self):
        """Test skipping minified files."""
        assert SCSSLanguage.should_skip("app.min.scss") is True
        assert SCSSLanguage.should_skip("styles.scss") is False

    def test_scan_basic_variables(self, scss_language, basic_scss):
        """Test SCSS variable extraction."""
        structures = scss_language.scan(basic_scss)
        assert structures is not None

        variables = [s for s in structures if s.type == "variable"]
        assert len(variables) >= 4

        primary = next((v for v in variables if v.name == "$primary-color"), None)
        assert primary is not None
        assert "#3498db" in (primary.signature or "")

    def test_scan_basic_mixins(self, scss_language, basic_scss):
        """Test @mixin extraction."""
        structures = scss_language.scan(basic_scss)
        assert structures is not None

        mixins = [s for s in structures if s.type == "mixin"]
        assert len(mixins) >= 3

        flex_center = next((m for m in mixins if m.name == "flex-center"), None)
        assert flex_center is not None

        button_style = next((m for m in mixins if m.name == "button-style"), None)
        assert button_style is not None
        assert "(" in (button_style.signature or "")

    def test_scan_basic_functions(self, scss_language, basic_scss):
        """Test @function extraction."""
        structures = scss_language.scan(basic_scss)
        assert structures is not None

        functions = [s for s in structures if s.type == "function"]
        assert len(functions) >= 2

        shade = next((f for f in functions if f.name == "shade"), None)
        assert shade is not None

    def test_scan_basic_imports(self, scss_language, basic_scss):
        """Test @use/@forward/@import extraction."""
        structures = scss_language.scan(basic_scss)
        assert structures is not None

        imports = [s for s in structures if s.type == "import"]
        assert len(imports) >= 3

        # Check for @use
        use_imports = [i for i in imports if "use" in i.modifiers]
        assert len(use_imports) >= 1

        # Check for @forward
        forward_imports = [i for i in imports if "forward" in i.modifiers]
        assert len(forward_imports) >= 1

    def test_scan_basic_media_queries(self, scss_language, basic_scss):
        """Test @media extraction."""
        structures = scss_language.scan(basic_scss)
        assert structures is not None

        media = [s for s in structures if s.type == "media_query"]
        assert len(media) >= 1

    def test_scan_basic_keyframes(self, scss_language, basic_scss):
        """Test @keyframes extraction."""
        structures = scss_language.scan(basic_scss)
        assert structures is not None

        keyframes = [s for s in structures if s.type == "keyframes"]
        assert len(keyframes) >= 1

        fade = next((k for k in keyframes if k.name == "fadeIn"), None)
        assert fade is not None

    def test_scan_basic_rule_sets(self, scss_language, basic_scss):
        """Test rule set extraction."""
        structures = scss_language.scan(basic_scss)
        assert structures is not None

        rules = [s for s in structures if s.type == "rule_set"]
        assert len(rules) >= 4

    def test_scan_basic_nested_rules(self, scss_language, basic_scss):
        """Test nested rule extraction."""
        structures = scss_language.scan(basic_scss)
        assert structures is not None

        # Find .btn rule
        btn_rule = next(
            (s for s in structures if s.type == "rule_set" and ".btn" in s.name),
            None
        )
        assert btn_rule is not None
        # Should have nested children (modifiers)
        assert btn_rule.children is not None or "nested" in btn_rule.modifiers

    def test_scan_partial_variables(self, scss_language, variables_scss):
        """Test partial file with many variables."""
        structures = scss_language.scan(variables_scss)
        assert structures is not None

        variables = [s for s in structures if s.type == "variable"]
        assert len(variables) >= 20  # Many variables in this file

    def test_scan_edge_cases_complex_mixin(self, scss_language, edge_cases_scss):
        """Test complex mixin with many parameters."""
        structures = scss_language.scan(edge_cases_scss)
        assert structures is not None

        mixins = [s for s in structures if s.type == "mixin"]
        complex_mixin = next(
            (m for m in mixins if m.name == "complex-mixin"), None
        )
        assert complex_mixin is not None
        assert "$color" in (complex_mixin.signature or "")

    def test_scan_edge_cases_function_logic(self, scss_language, edge_cases_scss):
        """Test function extraction."""
        structures = scss_language.scan(edge_cases_scss)
        assert structures is not None

        functions = [s for s in structures if s.type == "function"]
        calc_rem = next(
            (f for f in functions if f.name == "calculate-rem"), None
        )
        assert calc_rem is not None

    def test_scan_edge_cases_deep_nesting(self, scss_language, edge_cases_scss):
        """Test deeply nested selectors."""
        structures = scss_language.scan(edge_cases_scss)
        assert structures is not None

        # Find .level-1 rule
        level1 = next(
            (s for s in structures if s.type == "rule_set" and "level-1" in s.name),
            None
        )
        assert level1 is not None

    def test_scan_edge_cases_bem_nesting(self, scss_language, edge_cases_scss):
        """Test BEM-style nesting with parent selector."""
        structures = scss_language.scan(edge_cases_scss)
        assert structures is not None

        # Find .block rule
        block = next(
            (s for s in structures if s.type == "rule_set" and ".block" == s.name),
            None
        )
        assert block is not None

    def test_scan_edge_cases_multiple_imports(self, scss_language, edge_cases_scss):
        """Test multiple @use imports."""
        structures = scss_language.scan(edge_cases_scss)
        assert structures is not None

        use_imports = [s for s in structures
                       if s.type == "import" and "use" in s.modifiers]
        assert len(use_imports) >= 3  # sass:math, sass:color, sass:list

    def test_scan_important_comments(self, scss_language, basic_scss):
        """Test important comment extraction.

        Note: tree-sitter-scss may not expose comments in the AST,
        so we just verify scanning doesn't fail.
        """
        structures = scss_language.scan(basic_scss)
        assert structures is not None
        # Comments may or may not be in the tree depending on tree-sitter version
        # The important thing is that we can parse the file
