"""Tests for template preprocessing in HTML files."""

import pytest
from pathlib import Path

from scantool.languages.html import HTMLLanguage
from scantool.languages.templates import (
    preprocess,
    detect_dialect,
    merge_trees,
    Dialect,
    _extract_jinja_tags,
    _extract_svelte_tags,
    _extract_blade_tags,
    _build_template_tree,
    _neutralize,
)
from scantool.languages.models import StructureNode


@pytest.fixture
def html_language():
    return HTMLLanguage()


@pytest.fixture
def django_html():
    path = Path(__file__).parent / "django_template.html"
    return path.read_bytes()


@pytest.fixture
def svelte_html():
    path = Path(__file__).parent / "svelte_template.html"
    return path.read_bytes()


@pytest.fixture
def blade_html():
    path = Path(__file__).parent / "blade_template.html"
    return path.read_bytes()


# ═══════════════════════════════════════════════════════════════════════
# Dialect detection
# ═══════════════════════════════════════════════════════════════════════


class TestDialectDetection:
    def test_detect_jinja(self):
        assert detect_dialect("{% extends 'base.html' %}{% block content %}") == Dialect.JINJA

    def test_detect_svelte(self):
        assert detect_dialect("{#if show}<p>Hello</p>{/if}") == Dialect.SVELTE

    def test_detect_blade(self):
        assert detect_dialect("@extends('layout')\n@section('content')") == Dialect.BLADE

    def test_detect_erb(self):
        assert detect_dialect("<% if @user %><%= @user.name %><% end %>") == Dialect.ERB

    def test_detect_none_for_plain_html(self):
        assert detect_dialect("<html><body><h1>Hello</h1></body></html>") == Dialect.NONE

    def test_detect_django_template(self, django_html):
        assert detect_dialect(django_html.decode()) == Dialect.JINJA

    def test_detect_svelte_template(self, svelte_html):
        assert detect_dialect(svelte_html.decode()) == Dialect.SVELTE

    def test_detect_blade_template(self, blade_html):
        assert detect_dialect(blade_html.decode()) == Dialect.BLADE


# ═══════════════════════════════════════════════════════════════════════
# Jinja/Django tag extraction
# ═══════════════════════════════════════════════════════════════════════


class TestJinjaTagExtraction:
    def test_extracts_extends(self):
        tags = _extract_jinja_tags('{% extends "base.html" %}')
        meta_tags = [t for t in tags if t.kind == "meta" and t.construct == "extends"]
        assert len(meta_tags) == 1
        assert '"base.html"' in meta_tags[0].expression

    def test_extracts_block_pair(self):
        source = '{% block content %}hello{% endblock %}'
        tags = _extract_jinja_tags(source)
        opens = [t for t in tags if t.kind == "open" and t.construct == "block"]
        closes = [t for t in tags if t.kind == "close" and t.construct == "block"]
        assert len(opens) == 1
        assert len(closes) == 1

    def test_extracts_if_elif_else(self):
        source = '{% if x %}a{% elif y %}b{% else %}c{% endif %}'
        tags = _extract_jinja_tags(source)
        opens = [t for t in tags if t.kind == "open" and t.construct == "if"]
        mids = [t for t in tags if t.kind == "mid"]
        closes = [t for t in tags if t.kind == "close" and t.construct == "if"]
        assert len(opens) == 1
        assert len(mids) == 2  # elif + else
        assert len(closes) == 1

    def test_extracts_for_with_empty(self):
        source = '{% for x in items %}{{ x }}{% empty %}none{% endfor %}'
        tags = _extract_jinja_tags(source)
        opens = [t for t in tags if t.kind == "open" and t.construct == "for"]
        empties = [t for t in tags if t.kind == "mid" and t.construct == "empty"]
        closes = [t for t in tags if t.kind == "close" and t.construct == "for"]
        values = [t for t in tags if t.kind == "value"]
        assert len(opens) == 1
        assert len(empties) == 1
        assert len(closes) == 1
        assert len(values) == 1

    def test_line_numbers_multiline(self):
        source = "line1\n{% if x %}\nline3\n{% endif %}\n"
        tags = _extract_jinja_tags(source)
        if_tag = [t for t in tags if t.kind == "open"][0]
        endif_tag = [t for t in tags if t.kind == "close"][0]
        assert if_tag.line == 2
        assert endif_tag.line == 4

    def test_whitespace_control(self):
        tags = _extract_jinja_tags('{%- if x -%}hello{%- endif -%}')
        assert len([t for t in tags if t.kind == "open"]) == 1
        assert len([t for t in tags if t.kind == "close"]) == 1

    def test_comments(self):
        tags = _extract_jinja_tags('{# This is a comment #}')
        comments = [t for t in tags if t.kind == "comment"]
        assert len(comments) == 1

    def test_include(self):
        tags = _extract_jinja_tags('{% include "nav.html" %}')
        includes = [t for t in tags if t.kind == "meta" and t.construct == "include"]
        assert len(includes) == 1


# ═══════════════════════════════════════════════════════════════════════
# Svelte tag extraction
# ═══════════════════════════════════════════════════════════════════════


class TestSvelteTagExtraction:
    def test_if_else(self):
        source = '{#if show}<p>Hello</p>{:else}<p>Bye</p>{/if}'
        tags = _extract_svelte_tags(source)
        assert len([t for t in tags if t.kind == "open"]) == 1
        assert len([t for t in tags if t.kind == "mid"]) == 1
        assert len([t for t in tags if t.kind == "close"]) == 1

    def test_each(self):
        source = '{#each items as item}<li>{item.name}</li>{/each}'
        tags = _extract_svelte_tags(source)
        opens = [t for t in tags if t.kind == "open" and t.construct == "each"]
        assert len(opens) == 1
        assert "items as item" in opens[0].expression

    def test_nested_if_in_each(self):
        source = '{#each items as item}{#if item.show}<span/>{/if}{/each}'
        tags = _extract_svelte_tags(source)
        opens = [t for t in tags if t.kind == "open"]
        closes = [t for t in tags if t.kind == "close"]
        assert len(opens) == 2
        assert len(closes) == 2


# ═══════════════════════════════════════════════════════════════════════
# Blade tag extraction
# ═══════════════════════════════════════════════════════════════════════


class TestBladeTagExtraction:
    def test_extends(self):
        tags = _extract_blade_tags("@extends('layout')")
        meta = [t for t in tags if t.kind == "meta" and t.construct == "extends"]
        assert len(meta) == 1

    def test_if_else_endif(self):
        source = "@if($x)\nhello\n@else\nbye\n@endif"
        tags = _extract_blade_tags(source)
        assert len([t for t in tags if t.kind == "open"]) == 1
        assert len([t for t in tags if t.kind == "mid"]) == 1
        assert len([t for t in tags if t.kind == "close"]) == 1

    def test_foreach(self):
        source = "@foreach($items as $item)\n{{ $item }}\n@endforeach"
        tags = _extract_blade_tags(source)
        opens = [t for t in tags if t.kind == "open" and t.construct == "foreach"]
        assert len(opens) == 1


# ═══════════════════════════════════════════════════════════════════════
# Template tree building
# ═══════════════════════════════════════════════════════════════════════


class TestBuildTemplateTree:
    def test_simple_block(self):
        source = "{% block content %}\nhello\n{% endblock %}"
        tags = _extract_jinja_tags(source)
        tree = _build_template_tree(tags)
        assert len(tree) == 1
        assert tree[0].type == "template-block"
        assert "content" in tree[0].name
        assert tree[0].start_line == 1
        assert tree[0].end_line == 3

    def test_if_with_else(self):
        source = "{% if x %}\na\n{% else %}\nb\n{% endif %}"
        tags = _extract_jinja_tags(source)
        tree = _build_template_tree(tags)
        assert len(tree) == 1
        assert tree[0].type == "template-if"
        assert len(tree[0].children) == 1  # else is a child
        assert tree[0].children[0].type == "template-else"

    def test_nested_blocks(self):
        source = "{% block outer %}\n{% block inner %}\nhello\n{% endblock %}\n{% endblock %}"
        tags = _extract_jinja_tags(source)
        tree = _build_template_tree(tags)
        assert len(tree) == 1
        assert tree[0].type == "template-block"
        assert len(tree[0].children) == 1
        assert tree[0].children[0].type == "template-block"
        assert "inner" in tree[0].children[0].name

    def test_for_with_nested_if(self):
        source = "{% for x in items %}\n{% if x.show %}\nhello\n{% endif %}\n{% endfor %}"
        tags = _extract_jinja_tags(source)
        tree = _build_template_tree(tags)
        assert len(tree) == 1
        assert tree[0].type == "template-for"
        assert len(tree[0].children) == 1
        assert tree[0].children[0].type == "template-if"

    def test_extends_and_blocks(self):
        source = '{% extends "base.html" %}\n{% block content %}\nhello\n{% endblock %}'
        tags = _extract_jinja_tags(source)
        tree = _build_template_tree(tags)
        assert len(tree) == 2
        assert tree[0].type == "template-extends"
        assert tree[1].type == "template-block"

    def test_if_elif_else(self):
        source = "{% if a %}\n1\n{% elif b %}\n2\n{% else %}\n3\n{% endif %}"
        tags = _extract_jinja_tags(source)
        tree = _build_template_tree(tags)
        assert len(tree) == 1
        assert tree[0].type == "template-if"
        children_types = [c.type for c in tree[0].children]
        assert "template-elif" in children_types
        assert "template-else" in children_types

    def test_svelte_if_each(self):
        source = "{#each items as item}\n{#if item.show}\n<span/>\n{/if}\n{/each}"
        tags = _extract_svelte_tags(source)
        tree = _build_template_tree(tags)
        assert len(tree) == 1
        assert tree[0].type == "template-each"
        assert len(tree[0].children) == 1
        assert tree[0].children[0].type == "template-if"


# ═══════════════════════════════════════════════════════════════════════
# Neutralization
# ═══════════════════════════════════════════════════════════════════════


class TestNeutralize:
    def test_preserves_length(self):
        source = '<div>{% if x %}<span>{% endif %}</div>'
        tags = _extract_jinja_tags(source)
        result = _neutralize(source, tags)
        assert len(result) == len(source)

    def test_preserves_newlines(self):
        source = "line1\n{% if x %}\nline3\n{% endif %}\nline5"
        tags = _extract_jinja_tags(source)
        result = _neutralize(source, tags)
        assert result.count("\n") == source.count("\n")

    def test_replaces_tags_with_spaces(self):
        source = '<div>{% if x %}<span></span>{% endif %}</div>'
        tags = _extract_jinja_tags(source)
        result = _neutralize(source, tags)
        assert '{%' not in result
        assert '%}' not in result
        assert '<div>' in result
        assert '<span>' in result

    def test_neutralizes_value_tags(self):
        source = '<p>{{ name }}</p>'
        tags = _extract_jinja_tags(source)
        result = _neutralize(source, tags)
        assert '{{' not in result
        assert '<p>' in result
        assert '</p>' in result


# ═══════════════════════════════════════════════════════════════════════
# Merge trees
# ═══════════════════════════════════════════════════════════════════════


class TestMergeTrees:
    def test_template_wraps_html(self):
        template_nodes = [
            StructureNode(type="template-block", name="block: content",
                          start_line=1, end_line=10),
        ]
        html_nodes = [
            StructureNode(type="section", name="main", start_line=3, end_line=8),
        ]
        merged = merge_trees(template_nodes, html_nodes)
        assert len(merged) == 1
        assert merged[0].type == "template-block"
        assert len(merged[0].children) == 1
        assert merged[0].children[0].type == "section"

    def test_sibling_nodes(self):
        template_nodes = [
            StructureNode(type="template-extends", name="extends: base",
                          start_line=1, end_line=1),
        ]
        html_nodes = [
            StructureNode(type="section", name="main", start_line=5, end_line=10),
        ]
        merged = merge_trees(template_nodes, html_nodes)
        assert len(merged) == 2

    def test_empty_template_returns_html(self):
        html_nodes = [StructureNode(type="section", name="x", start_line=1, end_line=5)]
        assert merge_trees([], html_nodes) == html_nodes

    def test_empty_html_returns_template(self):
        tpl = [StructureNode(type="template-block", name="x", start_line=1, end_line=5)]
        assert merge_trees(tpl, []) == tpl


# ═══════════════════════════════════════════════════════════════════════
# Full integration: preprocess()
# ═══════════════════════════════════════════════════════════════════════


class TestPreprocess:
    def test_returns_none_for_plain_html(self):
        source = b"<html><body><h1>Hello</h1></body></html>"
        assert preprocess(source) is None

    def test_django_template(self, django_html):
        result = preprocess(django_html)
        assert result is not None
        assert result.dialect == Dialect.JINJA
        assert result.tag_count > 0
        assert len(result.template_nodes) > 0

        # Verify extends is captured
        extends = [n for n in result.template_nodes if n.type == "template-extends"]
        assert len(extends) == 1

        # Verify blocks are captured
        blocks = [n for n in result.template_nodes if n.type == "template-block"]
        assert len(blocks) >= 2  # content + extra_js at minimum

    def test_svelte_template(self, svelte_html):
        result = preprocess(svelte_html)
        assert result is not None
        assert result.dialect == Dialect.SVELTE

        # Should have if and each blocks
        types = set()
        def collect_types(nodes):
            for n in nodes:
                types.add(n.type)
                collect_types(n.children)
        collect_types(result.template_nodes)

        assert "template-if" in types
        assert "template-each" in types

    def test_blade_template(self, blade_html):
        result = preprocess(blade_html)
        assert result is not None
        assert result.dialect == Dialect.BLADE

    def test_cleaned_source_same_length(self, django_html):
        result = preprocess(django_html)
        assert result is not None
        assert len(result.cleaned_source) == len(django_html)

    def test_cleaned_source_same_newlines(self, django_html):
        result = preprocess(django_html)
        assert result is not None
        assert result.cleaned_source.count(b"\n") == django_html.count(b"\n")


# ═══════════════════════════════════════════════════════════════════════
# Full integration: HTMLLanguage.scan() with templates
# ═══════════════════════════════════════════════════════════════════════


class TestHTMLLanguageScanWithTemplates:
    def test_django_template_has_structure(self, html_language, django_html):
        structures = html_language.scan(django_html)
        assert structures is not None
        assert len(structures) > 1  # More than just file-info would give

        types = set()
        def collect_types(nodes):
            for n in nodes:
                types.add(n.type)
                collect_types(n.children)
        collect_types(structures)

        assert "template-extends" in types
        assert "template-block" in types
        assert "template-if" in types
        assert "template-for" in types

    def test_django_template_has_html_elements(self, html_language, django_html):
        structures = html_language.scan(django_html)
        assert structures is not None

        types = set()
        def collect_types(nodes):
            for n in nodes:
                types.add(n.type)
                collect_types(n.children)
        collect_types(structures)

        # HTML structural elements should also be present
        assert "section" in types or "table" in types or "form" in types

    def test_svelte_template_has_structure(self, html_language, svelte_html):
        structures = html_language.scan(svelte_html)
        assert structures is not None

        types = set()
        def collect_types(nodes):
            for n in nodes:
                types.add(n.type)
                collect_types(n.children)
        collect_types(structures)

        assert "template-if" in types or "template-each" in types

    def test_plain_html_unchanged(self, html_language):
        source = b"<!DOCTYPE html><html><body><section id='main'><h1>Hello</h1></section></body></html>"
        structures = html_language.scan(source)
        assert structures is not None
        # Should still work normally for plain HTML
        types = set()
        def collect_types(nodes):
            for n in nodes:
                types.add(n.type)
                collect_types(n.children)
        collect_types(structures)
        assert "template-if" not in types
        assert "template-block" not in types

    def test_extract_imports_includes_template_extends(self, html_language, django_html):
        imports = html_language.extract_imports("test.html", django_html.decode())
        template_imports = [i for i in imports if i.import_type.startswith("template_")]
        assert len(template_imports) >= 1  # At least extends
        extends = [i for i in template_imports if i.import_type == "template_extends"]
        assert len(extends) == 1
        assert extends[0].target_module == "base.html"

    def test_extract_imports_includes_template_include(self, html_language, django_html):
        imports = html_language.extract_imports("test.html", django_html.decode())
        includes = [i for i in imports if i.import_type == "template_include"]
        assert len(includes) >= 1
        assert "bilag/_kommentar_felt.html" in [i.target_module for i in includes]
