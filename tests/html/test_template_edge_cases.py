"""Edge case tests for template preprocessing.

Tests robustness against:
- Unclosed blocks (WIP files, copy-paste errors)
- Mismatched open/close pairs
- Orphan close tags without openers
- Empty blocks, deeply nested blocks
- Template tags inside HTML attributes
- Multiline template tags
- Minimal files (only value tags, no blocks)
- Corrupted/binary-ish content
- Mixed dialect confusion
"""

import pytest
from pathlib import Path

from scantool.languages.html import HTMLLanguage
from scantool.languages.templates import preprocess, Dialect


@pytest.fixture
def html_language():
    return HTMLLanguage()


@pytest.fixture
def edge_cases_html():
    path = Path(__file__).parent / "template_edge_cases.html"
    return path.read_bytes()


@pytest.fixture
def minimal_html():
    path = Path(__file__).parent / "template_minimal.html"
    return path.read_bytes()


# ═══════════════════════════════════════════════════════════════════════
# Unclosed blocks
# ═══════════════════════════════════════════════════════════════════════


class TestUnclosedBlocks:
    def test_unclosed_if_no_crash(self):
        source = "{% if x %}\n<p>Hello</p>\n"
        result = preprocess(source.encode())
        assert result is not None
        assert len(result.template_nodes) >= 1

    def test_unclosed_for_no_crash(self):
        source = "{% for x in items %}\n<li>{{ x }}</li>\n"
        result = preprocess(source.encode())
        assert result is not None

    def test_unclosed_block_no_crash(self):
        source = '{% extends "base.html" %}\n{% block content %}\n<h1>WIP</h1>\n'
        result = preprocess(source.encode())
        assert result is not None
        blocks = [n for n in result.template_nodes if n.type == "template-block"]
        assert len(blocks) == 1

    def test_unclosed_nested_if_for(self):
        source = "{% if a %}\n{% for x in items %}\n<p>{{ x }}</p>\n"
        result = preprocess(source.encode())
        assert result is not None
        tree = result.template_nodes
        # The if should contain the unclosed for
        assert len(tree) >= 1

    def test_multiple_unclosed_blocks(self):
        source = "{% block a %}\n{% block b %}\n{% block c %}\n<p>deep</p>\n"
        result = preprocess(source.encode())
        assert result is not None
        # Should not crash, should produce some tree
        assert len(result.template_nodes) >= 1

    def test_unclosed_if_with_else(self):
        source = "{% if x %}\n<p>yes</p>\n{% else %}\n<p>no</p>\n"
        result = preprocess(source.encode())
        assert result is not None
        # The if node should still have an else child
        if_nodes = [n for n in result.template_nodes if n.type == "template-if"]
        assert len(if_nodes) == 1
        else_children = [c for c in if_nodes[0].children if c.type == "template-else"]
        assert len(else_children) == 1


# ═══════════════════════════════════════════════════════════════════════
# Orphan close tags
# ═══════════════════════════════════════════════════════════════════════


class TestOrphanCloseTags:
    def test_orphan_endif_ignored(self):
        source = "<p>Hello</p>\n{% endif %}\n"
        result = preprocess(source.encode())
        assert result is not None
        # Should not produce an if node — just ignore the stray endif
        if_nodes = [n for n in result.template_nodes if n.type == "template-if"]
        assert len(if_nodes) == 0

    def test_orphan_endfor_ignored(self):
        source = "<p>Hello</p>\n{% endfor %}\n"
        result = preprocess(source.encode())
        assert result is not None

    def test_orphan_endblock_ignored(self):
        source = "<p>Hello</p>\n{% endblock %}\n"
        result = preprocess(source.encode())
        assert result is not None
        blocks = [n for n in result.template_nodes if n.type == "template-block"]
        assert len(blocks) == 0

    def test_mixed_orphans_and_valid(self):
        source = "{% endif %}\n{% if x %}\n<p>ok</p>\n{% endif %}\n{% endfor %}\n"
        result = preprocess(source.encode())
        assert result is not None
        if_nodes = [n for n in result.template_nodes if n.type == "template-if"]
        assert len(if_nodes) == 1


# ═══════════════════════════════════════════════════════════════════════
# Mismatched pairs
# ═══════════════════════════════════════════════════════════════════════


class TestMismatchedPairs:
    def test_if_closed_with_endfor(self):
        source = "{% if x %}\n<p>Hello</p>\n{% endfor %}\n"
        result = preprocess(source.encode())
        assert result is not None
        # Should not crash — mismatched close is ignored, if stays unclosed

    def test_for_closed_with_endif(self):
        source = "{% for x in items %}\n<p>{{ x }}</p>\n{% endif %}\n"
        result = preprocess(source.encode())
        assert result is not None

    def test_block_closed_with_endif(self):
        source = "{% block content %}\n<p>Hello</p>\n{% endif %}\n"
        result = preprocess(source.encode())
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════
# Empty and minimal templates
# ═══════════════════════════════════════════════════════════════════════


class TestEmptyAndMinimal:
    def test_empty_file(self):
        result = preprocess(b"")
        assert result is None

    def test_only_whitespace(self):
        result = preprocess(b"   \n\n   \n")
        assert result is None

    def test_single_value_tag_below_threshold(self, minimal_html):
        # A single {{ value }} is too ambiguous to trigger preprocessing
        result = preprocess(minimal_html)
        assert result is None

    def test_multiple_value_tags_detected(self):
        source = b"<p>{{ foo }}</p>\n<p>{{ bar }}</p>\n"
        result = preprocess(source)
        assert result is not None
        assert result.dialect == Dialect.JINJA

    def test_empty_block(self):
        source = "{% block sidebar %}{% endblock %}"
        result = preprocess(source.encode())
        assert result is not None
        blocks = [n for n in result.template_nodes if n.type == "template-block"]
        assert len(blocks) == 1
        assert blocks[0].start_line == blocks[0].end_line  # Same line

    def test_empty_if(self):
        source = "{% if x %}{% endif %}"
        result = preprocess(source.encode())
        assert result is not None

    def test_empty_for(self):
        source = "{% for x in items %}{% endfor %}"
        result = preprocess(source.encode())
        assert result is not None

    def test_only_extends(self):
        source = b'{% extends "base.html" %}\n'
        result = preprocess(source)
        assert result is not None
        extends = [n for n in result.template_nodes if n.type == "template-extends"]
        assert len(extends) == 1

    def test_only_comments(self):
        source = b"{# just a comment #}\n{# another comment #}\n"
        result = preprocess(source)
        assert result is not None
        assert result.dialect == Dialect.JINJA


# ═══════════════════════════════════════════════════════════════════════
# Deep nesting
# ═══════════════════════════════════════════════════════════════════════


class TestDeepNesting:
    def test_deeply_nested_ifs(self):
        lines = []
        depth = 10
        for i in range(depth):
            lines.append(f"{{% if cond_{i} %}}")
        lines.append("<p>deep</p>")
        for i in range(depth):
            lines.append("{% endif %}")
        source = "\n".join(lines)
        result = preprocess(source.encode())
        assert result is not None
        # Walk the tree to verify depth
        node = result.template_nodes[0]
        actual_depth = 1
        while node.children:
            if_children = [c for c in node.children if c.type == "template-if"]
            if if_children:
                node = if_children[0]
                actual_depth += 1
            else:
                break
        assert actual_depth == depth

    def test_nested_for_in_if_in_block(self):
        source = (
            "{% block content %}\n"
            "{% if show %}\n"
            "{% for x in items %}\n"
            "<p>{{ x }}</p>\n"
            "{% endfor %}\n"
            "{% endif %}\n"
            "{% endblock %}\n"
        )
        result = preprocess(source.encode())
        assert result is not None
        block = result.template_nodes[0]
        assert block.type == "template-block"
        if_node = [c for c in block.children if c.type == "template-if"][0]
        for_node = [c for c in if_node.children if c.type == "template-for"][0]
        assert for_node is not None


# ═══════════════════════════════════════════════════════════════════════
# Template tags in unusual positions
# ═══════════════════════════════════════════════════════════════════════


class TestUnusualPositions:
    def test_tags_inside_html_attributes(self):
        source = '<div class="{% if active %}active{% endif %}">\n</div>'
        result = preprocess(source.encode())
        assert result is not None
        # The neutralized source should have valid-ish HTML
        assert b'{%' not in result.cleaned_source

    def test_single_value_in_attribute_below_threshold(self):
        # Single {{ }} is ambiguous — not enough signal
        source = '<img src="{{ image_url }}" alt="test">'
        result = preprocess(source.encode())
        assert result is None

    def test_multiple_values_in_attributes(self):
        source = '<img src="{{ image_url }}" alt="{{ alt_text }}">'
        result = preprocess(source.encode())
        assert result is not None
        assert b'{{' not in result.cleaned_source
        assert b'<img' in result.cleaned_source

    def test_tag_in_href(self):
        source = '<a href="{% url \'detail\' pk=obj.pk %}">Link</a>'
        result = preprocess(source.encode())
        assert result is not None
        assert b'{%' not in result.cleaned_source

    def test_multiline_tag(self):
        source = "{% if\n   long_condition\n   and another\n%}\n<p>ok</p>\n{% endif %}"
        result = preprocess(source.encode())
        assert result is not None
        # Line count should be preserved
        assert result.cleaned_source.count(b"\n") == source.encode().count(b"\n")


# ═══════════════════════════════════════════════════════════════════════
# Corrupted / non-template content
# ═══════════════════════════════════════════════════════════════════════


class TestCorruptedContent:
    def test_binary_content(self):
        source = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        result = preprocess(source)
        assert result is None

    def test_partial_tag_opening(self):
        source = b"<p>Hello {% incomplete"
        result = preprocess(source)
        # Should either return None or handle gracefully
        assert result is None or isinstance(result.template_nodes, list)

    def test_curly_braces_not_template(self):
        source = b"<script>const x = {a: 1, b: {c: 2}};</script>"
        result = preprocess(source)
        assert result is None  # No template dialect detected

    def test_json_in_script_tag(self):
        source = b'<script type="application/json">{"if": true, "for": [1,2]}</script>'
        result = preprocess(source)
        assert result is None

    def test_css_with_curly_braces(self):
        source = b"<style>.container { display: flex; } .item { color: red; }</style>"
        result = preprocess(source)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# Svelte edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestSvelteEdgeCases:
    def test_unclosed_if(self):
        source = b"{#if show}\n<p>Hello</p>\n"
        result = preprocess(source)
        assert result is not None

    def test_unclosed_each(self):
        source = b"{#each items as item}\n<li>{item.name}</li>\n"
        result = preprocess(source)
        assert result is not None

    def test_else_if(self):
        source = b"{#if a}\n<p>a</p>\n{:else if b}\n<p>b</p>\n{:else}\n<p>c</p>\n{/if}"
        result = preprocess(source)
        assert result is not None

    def test_await_then_catch(self):
        source = b"{#await promise}\n<p>Loading</p>\n{:then data}\n<p>{data}</p>\n{:catch err}\n<p>{err}</p>\n{/await}"
        result = preprocess(source)
        assert result is not None
        await_nodes = [n for n in result.template_nodes if n.type == "template-await"]
        assert len(await_nodes) == 1


# ═══════════════════════════════════════════════════════════════════════
# Blade edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestBladeEdgeCases:
    def test_unclosed_if(self):
        source = b"@if($user)\n<p>Hello</p>\n"
        result = preprocess(source)
        assert result is not None

    def test_unclosed_foreach(self):
        source = b"@foreach($items as $item)\n<li>{{ $item }}</li>\n"
        result = preprocess(source)
        assert result is not None

    def test_single_raw_output_below_threshold(self):
        # Single {!! !!} not enough signal alone
        source = b"<p>{!! $html !!}</p>"
        result = preprocess(source)
        assert result is None

    def test_raw_output_with_blade_context(self):
        source = b"@if($x)\n<p>{!! $html !!}</p>\n@endif"
        result = preprocess(source)
        assert result is not None
        assert b'{!!' not in result.cleaned_source

    def test_section_without_endsection(self):
        source = b"@extends('layout')\n@section('content')\n<p>WIP</p>\n"
        result = preprocess(source)
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════
# Full integration: HTMLLanguage.scan() with edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestHTMLLanguageScanEdgeCases:
    def test_edge_cases_no_crash(self, html_language, edge_cases_html):
        """The big edge case file should scan without crashing."""
        structures = html_language.scan(edge_cases_html)
        assert structures is not None
        assert len(structures) > 0

    def test_edge_cases_has_template_nodes(self, html_language, edge_cases_html):
        """Should extract template structure even from messy files."""
        structures = html_language.scan(edge_cases_html)
        types = set()
        def collect(nodes):
            for n in nodes:
                types.add(n.type)
                collect(n.children)
        collect(structures)
        assert "template-extends" in types
        assert "template-block" in types

    def test_edge_cases_has_html_nodes(self, html_language, edge_cases_html):
        """Should still extract HTML structure from messy template files."""
        structures = html_language.scan(edge_cases_html)
        types = set()
        def collect(nodes):
            for n in nodes:
                types.add(n.type)
                collect(n.children)
        collect(structures)
        html_types = types - {t for t in types if t.startswith("template-")}
        assert len(html_types) > 0

    def test_wip_file_only_extends(self, html_language):
        """A WIP file with just extends and empty block."""
        source = b'{% extends "base.html" %}\n{% block content %}\n'
        structures = html_language.scan(source)
        assert structures is not None

    def test_wip_file_unclosed_everything(self, html_language):
        """A truly messy WIP file."""
        source = (
            b'{% extends "base.html" %}\n'
            b'{% block content %}\n'
            b'<div id="main">\n'
            b'  {% if user %}\n'
            b'  <h1>{{ user.name }}</h1>\n'
            b'  {% for item in user.items %}\n'
            b'  <p>{{ item }}\n'  # unclosed <p>
            # no endfor, no endif, no endblock
        )
        structures = html_language.scan(source)
        assert structures is not None
        assert len(structures) > 0

    def test_minimal_only_values(self, html_language, minimal_html):
        """File with only {{ value }} tags, no blocks."""
        structures = html_language.scan(minimal_html)
        assert structures is not None
