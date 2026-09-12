"""Tests for TOML language structure scanning."""

from pathlib import Path

import pytest

from scantool.languages.toml import TOMLLanguage


@pytest.fixture
def toml_language():
    """Create TOML language instance."""
    return TOMLLanguage()


@pytest.fixture
def basic_toml():
    """Load basic.toml test file."""
    path = Path(__file__).parent / "samples" / "basic.toml"
    return path.read_bytes()


@pytest.fixture
def edge_cases_toml():
    """Load edge_cases.toml test file."""
    path = Path(__file__).parent / "samples" / "edge_cases.toml"
    return path.read_bytes()


@pytest.fixture
def broken_toml():
    """Load broken.toml test file."""
    path = Path(__file__).parent / "samples" / "broken.toml"
    return path.read_bytes()


@pytest.fixture
def comments_toml():
    """Load comments.toml: a header block, attached doc lines, a block inside
    a table, a comment inside an array and a trailing comment."""
    path = Path(__file__).parent / "samples" / "comments.toml"
    return path.read_bytes()


class TestTOMLScanner:
    """Tests for TOMLLanguage.scan()."""

    def test_get_extensions(self):
        assert TOMLLanguage.get_extensions() == [".toml"]

    def test_get_language_name(self):
        assert TOMLLanguage.get_language_name() == "TOML"

    def test_should_skip_lock_file(self):
        assert TOMLLanguage.should_skip("Cargo.lock") is True
        assert TOMLLanguage.should_skip("Cargo.toml") is False

    def test_scan_top_level_pairs_before_first_table(self, toml_language, basic_toml):
        """Pairs written before the first table header are top-level nodes."""
        structures = toml_language.scan(basic_toml)
        assert structures is not None

        top_level_keys = [s for s in structures if s.type == "key"]
        assert {s.name for s in top_level_keys} == {"name", "version"}
        by_name = {s.name: s for s in top_level_keys}
        assert by_name["name"].signature == '"demo-app"'

    def test_scan_table_becomes_a_node_with_pairs_as_children(self, toml_language, basic_toml):
        structures = toml_language.scan(basic_toml)
        server = next(s for s in structures if s.type == "table" and s.name == "server")
        assert {c.name for c in server.children} == {"host", "port"}

    def test_scan_dotted_table_name_is_literal(self, toml_language, basic_toml):
        """A `[a.b]` header's node name is the literal dotted key text."""
        structures = toml_language.scan(basic_toml)
        tls = next(s for s in structures if s.type == "table" and s.name == "server.tls")
        assert {c.name for c in tls.children} == {"enabled", "cert"}
        assert tls.synthetic is False

    def test_scan_array_table_repeats_per_element(self, toml_language, basic_toml):
        """Each `[[x]]` block becomes its own array_table node."""
        structures = toml_language.scan(basic_toml)
        plugin_tables = [s for s in structures if s.type == "array_table" and s.name == "plugins"]
        assert len(plugin_tables) == 2
        names = [dict((c.name, c.signature) for c in t.children)["name"] for t in plugin_tables]
        assert names == ['"auth"', '"cache"']

    def test_scan_table_end_line_excludes_trailing_blank_lines(self, toml_language, basic_toml):
        """The TOML grammar extends a table's span through trailing blank
        lines up to the next header; end_line should reflect real content."""
        structures = toml_language.scan(basic_toml)
        server = next(s for s in structures if s.type == "table" and s.name == "server")
        assert server.start_line == 5
        assert server.end_line == 7  # last pair ("port = 8080"), not the blank line after it

    def test_scan_inline_table_nests_like_an_object(self, toml_language, edge_cases_toml):
        structures = toml_language.scan(edge_cases_toml)
        details = next(s for s in structures if s.name == "metadata.details")
        info = next(c for c in details.children if c.name == "info")
        assert info.type == "object"
        assert {c.name for c in info.children} == {"author", "version"}

    def test_scan_array_value_is_a_leaf_with_item_count(self, toml_language, edge_cases_toml):
        structures = toml_language.scan(edge_cases_toml)
        details = next(s for s in structures if s.name == "metadata.details")
        tags = next(c for c in details.children if c.name == "tags")
        assert tags.type == "array"
        assert tags.children == []
        assert tags.signature == "5 items"

    def test_scan_quoted_key_strips_quotes(self, toml_language, edge_cases_toml):
        structures = toml_language.scan(edge_cases_toml)
        metadata = next(s for s in structures if s.name == "metadata")
        assert any(c.name == "quoted key" for c in metadata.children)

    def test_scan_long_string_is_truncated(self, toml_language, edge_cases_toml):
        structures = toml_language.scan(edge_cases_toml)
        details = next(s for s in structures if s.name == "metadata.details")
        description = next(c for c in details.children if c.name == "description")
        assert description.signature is not None
        assert description.signature.endswith("...")
        assert len(description.signature) == 50

    def test_scan_empty_table_has_no_children(self, toml_language, edge_cases_toml):
        structures = toml_language.scan(edge_cases_toml)
        empty = next(s for s in structures if s.type == "table" and s.name == "empty")
        assert empty.children == []
        assert empty.start_line == empty.end_line

    def test_scan_empty_file(self, toml_language):
        assert toml_language.scan(b"") == []

    def test_scan_broken_toml_does_not_crash(self, toml_language, broken_toml):
        structures = toml_language.scan(broken_toml)
        assert isinstance(structures, list)


class TestTOMLCommentBlocks:
    """Full-line comments are structure: blocks become `comment` nodes,
    an attached single line becomes the pair's or table's docstring."""

    def test_leading_header_separated_by_a_blank_line_is_a_comment_node(
        self, toml_language, comments_toml
    ):
        structures = toml_language.scan(comments_toml)
        header = structures[0]
        assert header.type == "comment"
        assert (header.start_line, header.end_line) == (1, 2)
        assert header.name == "Build configuration for the demo app."
        assert header.signature == "2 lines"
        assert header.synthetic is False

    def test_attached_single_line_becomes_the_docstring(self, toml_language, comments_toml):
        structures = toml_language.scan(comments_toml)
        name = next(s for s in structures if s.name == "name")
        assert name.docstring == "Package identity"
        version = next(s for s in structures if s.name == "version")
        assert version.docstring is None
        assert version.signature == '"1.2.3"'  # the trailing comment is left alone
        tls = next(s for s in structures if s.name == "server.tls")
        assert tls.docstring == "TLS is off in development"

    def test_block_inside_a_table_is_a_child_of_the_table(self, toml_language, comments_toml):
        structures = toml_language.scan(comments_toml)
        server = next(s for s in structures if s.name == "server")
        host = next(c for c in server.children if c.name == "host")
        assert host.docstring == "Listening address; 0.0.0.0 in containers"
        # A block after the last pair, blank line before the next header:
        # placed before that header at top level, named past the "---" line
        block = next(s for s in structures if s.type == "comment" and s.start_line == 12)
        assert block.end_line == 14
        assert block.name == "Ports below 1024 need CAP_NET_BIND_SERVICE on L..."
        assert block.synthetic is True
        assert (
            structures.index(block)
            == structures.index(next(s for s in structures if s.name == "server.tls")) - 1
        )

    def test_comment_inside_an_array_is_ignored_and_short_lone_lines_dropped(
        self, toml_language, comments_toml
    ):
        structures = toml_language.scan(comments_toml)
        assert not any("inside arrays" in s.name for s in structures)
        assert not any(s.name == "TODO" for s in structures)
        trailing = structures[-1]
        assert trailing.type == "comment"
        assert trailing.start_line == trailing.end_line == 25
        assert trailing.name.startswith("Trailing note after the last pair")

    def test_no_comments_no_change(self, toml_language, edge_cases_toml):
        structures = toml_language.scan(edge_cases_toml)
        assert not any(s.type == "comment" for s in structures)
