"""Tests for Markdown analyzer."""

import pytest
from scantool.analyzers.markdown_analyzer import MarkdownAnalyzer
from scantool.analyzers.models import ImportInfo, EntryPointInfo


@pytest.fixture
def analyzer():
    """Create Markdown analyzer instance."""
    return MarkdownAnalyzer()


class TestMarkdownAnalyzer:
    """Test suite for Markdown analyzer."""

    def test_extensions(self, analyzer):
        """Test that analyzer supports correct extensions."""
        extensions = analyzer.get_extensions()
        assert ".md" in extensions
        assert ".markdown" in extensions
        assert ".mdown" in extensions
        assert ".mkd" in extensions

    def test_language_name(self, analyzer):
        """Test language name."""
        assert analyzer.get_language_name() == "Markdown"

    def test_extract_imports_markdown_links(self, analyzer):
        """Test extraction of Markdown links [text](file.md)."""
        content = """
# Documentation

See the [API Docs](api.md) for details.
Check out [Installation Guide](../docs/install.md).
"""
        imports = analyzer.extract_imports("README.md", content)

        # Should find 2 links
        link_imports = [imp for imp in imports if imp.import_type == "link"]
        assert len(link_imports) == 2
        assert any(imp.target_module == "api.md" for imp in link_imports)
        assert any("install.md" in imp.target_module for imp in link_imports)

    def test_extract_imports_skip_urls(self, analyzer):
        """Test that URLs are skipped, not treated as file references."""
        content = """
[Google](https://google.com)
[GitHub](http://github.com)
[Email](mailto:user@example.com)
"""
        imports = analyzer.extract_imports("test.md", content)

        # Should find no imports (all are URLs)
        assert len(imports) == 0

    def test_extract_imports_skip_anchors_only(self, analyzer):
        """Test that anchor-only links are skipped."""
        content = """
Jump to [section](#heading)
See [below](#another-section)
"""
        imports = analyzer.extract_imports("test.md", content)

        # Should find no imports (all are anchor-only)
        assert len(imports) == 0

    def test_extract_imports_strip_anchors(self, analyzer):
        """Test that anchors are stripped from file paths."""
        content = """
See [API](api.md#methods) for details.
Check [Guide](guide.md#installation).
"""
        imports = analyzer.extract_imports("test.md", content)

        # Should find 2 links with anchors stripped
        assert len(imports) == 2
        assert any(imp.target_module == "api.md" for imp in imports)
        assert any(imp.target_module == "guide.md" for imp in imports)
        # Ensure no anchors remain
        assert all('#' not in imp.target_module for imp in imports)

    def test_extract_imports_markdown_images(self, analyzer):
        """Test extraction of Markdown images ![alt](path)."""
        content = """
![Architecture Diagram](assets/arch.png)
![Logo](../images/logo.svg)
![Screenshot](screens/app.jpg)
"""
        imports = analyzer.extract_imports("README.md", content)

        # Should find 3 image imports
        image_imports = [imp for imp in imports if imp.import_type == "image"]
        assert len(image_imports) == 3
        assert any("arch.png" in imp.target_module for imp in image_imports)
        assert any("logo.svg" in imp.target_module for imp in image_imports)
        assert any("app.jpg" in imp.target_module for imp in image_imports)

    def test_extract_imports_html_img_tags(self, analyzer):
        """Test extraction of HTML img tags."""
        content = """
<img src="banner.png" alt="Banner">
<img src='logo.jpg' />
<IMG SRC="header.gif">
"""
        imports = analyzer.extract_imports("test.md", content)

        # Should find 3 image imports
        image_imports = [imp for imp in imports if imp.import_type == "image"]
        assert len(image_imports) == 3
        assert any(imp.target_module == "banner.png" for imp in image_imports)
        assert any(imp.target_module == "logo.jpg" for imp in image_imports)
        assert any(imp.target_module == "header.gif" for imp in image_imports)

    def test_extract_imports_skip_data_uris(self, analyzer):
        """Test that data URIs are skipped."""
        content = """
<img src="data:image/png;base64,iVBORw0KG...">
![icon](data:image/svg+xml;base64,PHN2Zy...)
"""
        imports = analyzer.extract_imports("test.md", content)

        # Should find no imports (all are data URIs)
        assert len(imports) == 0

    def test_extract_imports_include_directives(self, analyzer):
        """Test extraction of include directives."""
        content = """
{{include api.md}}
{% include 'footer.md' %}
{!snippets/example.md!}
"""
        imports = analyzer.extract_imports("test.md", content)

        # Should find 3 include directives
        include_imports = [imp for imp in imports if imp.import_type == "include"]
        assert len(include_imports) == 3
        assert any(imp.target_module == "api.md" for imp in include_imports)
        assert any(imp.target_module == "footer.md" for imp in include_imports)
        assert any("example.md" in imp.target_module for imp in include_imports)

    def test_extract_imports_mixed_types(self, analyzer):
        """Test extraction of mixed import types in one file."""
        content = """
# Project Documentation

See [API Reference](api.md) and [Guide](docs/guide.md).

![Architecture](diagrams/arch.png)

<img src="logo.png" alt="Logo">

{{include shared/footer.md}}
"""
        imports = analyzer.extract_imports("README.md", content)

        # Should find all types: 2 links, 2 images, 1 include
        assert len(imports) == 5

        link_imports = [imp for imp in imports if imp.import_type == "link"]
        image_imports = [imp for imp in imports if imp.import_type == "image"]
        include_imports = [imp for imp in imports if imp.import_type == "include"]

        assert len(link_imports) == 2
        assert len(image_imports) == 2
        assert len(include_imports) == 1

    def test_extract_imports_line_numbers(self, analyzer):
        """Test that line numbers are correctly captured."""
        content = """Line 1
Line 2
[Link](file.md)
Line 4
![Image](img.png)
"""
        imports = analyzer.extract_imports("test.md", content)

        assert len(imports) == 2
        # Link on line 3
        link_import = [imp for imp in imports if imp.import_type == "link"][0]
        assert link_import.line == 3
        # Image on line 5
        image_import = [imp for imp in imports if imp.import_type == "image"][0]
        assert image_import.line == 5

    def test_extract_imports_relative_paths(self, analyzer):
        """Test handling of relative paths."""
        content = """
[Same Dir](file.md)
[Parent](../other.md)
[Nested](sub/dir/doc.md)
"""
        imports = analyzer.extract_imports("docs/current/page.md", content)

        # All should be resolved or kept as-is
        assert len(imports) == 3
        # Relative path resolution is handled by _resolve_relative_import
        # Just verify imports are captured
        assert any("file.md" in imp.target_module for imp in imports)
        assert any("other.md" in imp.target_module for imp in imports)
        assert any("doc.md" in imp.target_module for imp in imports)

    def test_find_entry_points_readme(self, analyzer):
        """Test detection of README.md as entry point."""
        content = "# My Project\n\nWelcome!"
        entry_points = analyzer.find_entry_points("README.md", content)

        readme_entries = [ep for ep in entry_points if ep.type == "documentation_root"]
        assert len(readme_entries) == 1
        assert readme_entries[0].name == "README.MD"

    def test_find_entry_points_index(self, analyzer):
        """Test detection of INDEX.md as entry point."""
        content = "# Index\n\nTable of contents"
        entry_points = analyzer.find_entry_points("INDEX.md", content)

        index_entries = [ep for ep in entry_points if ep.type == "documentation_root"]
        assert len(index_entries) == 1
        assert index_entries[0].name == "INDEX.MD"

    def test_find_entry_points_home(self, analyzer):
        """Test detection of HOME.md as entry point."""
        content = "# Home Page"
        entry_points = analyzer.find_entry_points("HOME.md", content)

        home_entries = [ep for ep in entry_points if ep.type == "documentation_root"]
        assert len(home_entries) == 1
        assert home_entries[0].name == "HOME.MD"

    def test_find_entry_points_main_heading(self, analyzer):
        """Test detection of # Main heading as entry point."""
        content = """
# Main

This is the main documentation.
"""
        entry_points = analyzer.find_entry_points("docs.md", content)

        heading_entries = [ep for ep in entry_points if ep.type == "entry_heading"]
        assert len(heading_entries) == 1
        assert heading_entries[0].name == "Main"

    def test_find_entry_points_getting_started(self, analyzer):
        """Test detection of # Getting Started heading."""
        content = """
# Getting Started

Follow these steps...
"""
        entry_points = analyzer.find_entry_points("guide.md", content)

        heading_entries = [ep for ep in entry_points if ep.type == "entry_heading"]
        assert len(heading_entries) == 1
        assert heading_entries[0].name == "Getting Started"

    def test_find_entry_points_multiple(self, analyzer):
        """Test detection of multiple entry points in README."""
        content = """
# Home

Welcome to the project!

# Getting Started

Let's begin...
"""
        entry_points = analyzer.find_entry_points("README.md", content)

        # Should find: 1 documentation_root + 2 entry_headings
        assert len(entry_points) == 3

        doc_root = [ep for ep in entry_points if ep.type == "documentation_root"]
        headings = [ep for ep in entry_points if ep.type == "entry_heading"]

        assert len(doc_root) == 1
        assert len(headings) == 2

    def test_find_entry_points_case_insensitive(self, analyzer):
        """Test that heading detection is case-insensitive."""
        content = """
# GETTING STARTED

# introduction

# OverView
"""
        entry_points = analyzer.find_entry_points("guide.md", content)

        # Should find all 3 headings (case-insensitive)
        heading_entries = [ep for ep in entry_points if ep.type == "entry_heading"]
        assert len(heading_entries) == 3

    def test_should_analyze_normal_file(self, analyzer):
        """Test that normal Markdown files are analyzed."""
        assert analyzer.should_analyze("README.md") is True
        assert analyzer.should_analyze("docs/api.md") is True
        assert analyzer.should_analyze("guide.markdown") is True

    def test_should_analyze_skip_generated(self, analyzer):
        """Test that generated files are skipped."""
        assert analyzer.should_analyze("api.generated.md") is False
        assert analyzer.should_analyze("docs.auto.md") is False

    def test_classify_file_readme(self, analyzer):
        """Test that README files are classified as entry_points."""
        content = "# README"
        cluster = analyzer.classify_file("README.md", content)
        assert cluster == "entry_points"

        cluster = analyzer.classify_file("README.markdown", content)
        assert cluster == "entry_points"

    def test_classify_file_docs_directory(self, analyzer):
        """Test that files in docs/ are classified as documentation."""
        content = "# API Reference"
        cluster = analyzer.classify_file("docs/api.md", content)
        assert cluster == "documentation"

        cluster = analyzer.classify_file("documentation/guide.md", content)
        assert cluster == "documentation"

    def test_classify_file_other(self, analyzer):
        """Test fallback classification for other files."""
        content = "# Notes"
        # Should use BaseAnalyzer's classify_file
        cluster = analyzer.classify_file("notes.md", content)
        # BaseAnalyzer returns "other" for unrecognized patterns
        assert cluster == "other"

    def test_extract_imports_image_extensions(self, analyzer):
        """Test that various image extensions are recognized."""
        content = """
![PNG](image.png)
![JPG](photo.jpg)
![JPEG](photo.jpeg)
![GIF](anim.gif)
![SVG](vector.svg)
![WEBP](modern.webp)
[PDF Link](doc.pdf)
"""
        imports = analyzer.extract_imports("test.md", content)

        # 6 images recognized by extension, 1 non-image link
        image_imports = [imp for imp in imports if imp.import_type == "image"]
        link_imports = [imp for imp in imports if imp.import_type == "link"]

        assert len(image_imports) == 6
        assert len(link_imports) == 1
        assert link_imports[0].target_module == "doc.pdf"

    def test_extract_imports_empty_file(self, analyzer):
        """Test extraction from empty file."""
        content = ""
        imports = analyzer.extract_imports("empty.md", content)
        assert len(imports) == 0

    def test_extract_imports_no_links(self, analyzer):
        """Test extraction from file with no links."""
        content = """
# Title

Just plain text without any links.

More text here.
"""
        imports = analyzer.extract_imports("plain.md", content)
        assert len(imports) == 0

    def test_find_entry_points_no_entry_points(self, analyzer):
        """Test file with no entry points."""
        content = """
# Regular Section

Some content.

## Subsection

More content.
"""
        entry_points = analyzer.find_entry_points("regular.md", content)
        # Should find no entry points (no Main/Home/Getting Started headings)
        assert len(entry_points) == 0

    def test_extract_imports_complex_paths(self, analyzer):
        """Test extraction of complex relative paths."""
        content = """
[Up One](../file.md)
[Up Two](../../other.md)
[Deep](sub/dir/deep/file.md)
[Complex](../../../root/file.md)
"""
        imports = analyzer.extract_imports("docs/api/current/page.md", content)

        # Should capture all relative paths
        assert len(imports) == 4
        # _resolve_relative_import handles resolution
        assert all(imp.target_module for imp in imports)

    def test_extract_imports_whitespace_handling(self, analyzer):
        """Test that whitespace in paths is handled correctly."""
        content = """
[Link]( file.md )
![ Image ]( image.png )
{% include  'footer.md'  %}
"""
        imports = analyzer.extract_imports("test.md", content)

        # Should strip whitespace from paths
        assert len(imports) == 3
        assert all(not imp.target_module.startswith(' ') for imp in imports)
        assert all(not imp.target_module.endswith(' ') for imp in imports)
