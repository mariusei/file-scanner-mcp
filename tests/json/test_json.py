"""Tests for JSON language structure scanning."""

from pathlib import Path

import pytest

from scantool.languages.json import JSONLanguage


@pytest.fixture
def json_language():
    """Create JSON language instance."""
    return JSONLanguage()


@pytest.fixture
def basic_json():
    """Load basic.json test file."""
    path = Path(__file__).parent / "samples" / "basic.json"
    return path.read_bytes()


@pytest.fixture
def edge_cases_json():
    """Load edge_cases.json test file."""
    path = Path(__file__).parent / "samples" / "edge_cases.json"
    return path.read_bytes()


@pytest.fixture
def broken_json():
    """Load broken.json test file."""
    path = Path(__file__).parent / "samples" / "broken.json"
    return path.read_bytes()


class TestJSONScanner:
    """Tests for JSONLanguage.scan()."""

    def test_get_extensions(self):
        assert JSONLanguage.get_extensions() == [".json"]

    def test_get_language_name(self):
        assert JSONLanguage.get_language_name() == "JSON"

    def test_should_skip_lock_file(self):
        assert JSONLanguage.should_skip("package-lock.json") is True
        assert JSONLanguage.should_skip("package.json") is False

    def test_should_skip_minified(self):
        assert JSONLanguage.should_skip("bundle.min.json") is True

    def test_scan_top_level_scalar_keys(self, json_language, basic_json):
        """Scalar-valued top-level keys become 'key' nodes with a compact signature."""
        structures = json_language.scan(basic_json)
        assert structures is not None

        by_name = {s.name: s for s in structures}
        assert by_name["name"].type == "key"
        assert by_name["name"].signature == '"demo-app"'
        assert by_name["private"].signature == "true"

    def test_scan_nested_object_full_depth(self, json_language, basic_json):
        """Objects nest fully: each depth produces real key/object nodes."""
        structures = json_language.scan(basic_json)
        by_name = {s.name: s for s in structures}

        config = by_name["config"]
        assert config.type == "object"
        server = {c.name: c for c in config.children}["server"]
        assert server.type == "object"
        assert {c.name for c in server.children} == {"host", "port"}

    def test_scan_array_is_a_leaf_with_item_count(self, json_language, basic_json):
        """An array value is a leaf node; its item count goes in signature."""
        structures = json_language.scan(basic_json)
        by_name = {s.name: s for s in structures}

        keywords = by_name["keywords"]
        assert keywords.type == "array"
        assert keywords.children == []
        assert keywords.signature == "3 items"

    def test_scan_line_numbers(self, json_language, basic_json):
        structures = json_language.scan(basic_json)
        by_name = {s.name: s for s in structures}
        assert by_name["name"].start_line == 2
        assert by_name["name"].end_line == 2

    def test_scan_empty_object_and_array(self, json_language, edge_cases_json):
        structures = json_language.scan(edge_cases_json)
        by_name = {s.name: s for s in structures}
        assert by_name["empty_object"].type == "object"
        assert by_name["empty_object"].children == []
        assert by_name["empty_array"].signature == "0 items"

    def test_scan_scalar_signatures(self, json_language, edge_cases_json):
        structures = json_language.scan(edge_cases_json)
        by_name = {s.name: s for s in structures}
        assert by_name["null_value"].signature == "null"
        assert by_name["boolean_true"].signature == "true"
        assert by_name["boolean_false"].signature == "false"
        assert by_name["integer"].signature == "42"
        assert by_name["negative"].signature == "-17"

    def test_scan_long_string_is_truncated(self, json_language, edge_cases_json):
        structures = json_language.scan(edge_cases_json)
        by_name = {s.name: s for s in structures}
        signature = by_name["long_string"].signature
        assert signature is not None
        assert signature.endswith("...")
        assert len(signature) == 50

    def test_scan_array_of_objects_stays_a_leaf(self, json_language, edge_cases_json):
        """Per the documented nesting decision, arrays never expand their elements."""
        structures = json_language.scan(edge_cases_json)
        by_name = {s.name: s for s in structures}
        node = by_name["array_of_objects"]
        assert node.type == "array"
        assert node.children == []
        assert node.signature == "2 items"

    def test_scan_deep_nesting(self, json_language, edge_cases_json):
        structures = json_language.scan(edge_cases_json)
        by_name = {s.name: s for s in structures}
        nested = by_name["deeply"].children[0]
        structure = nested.children[0]
        leaf = structure.children[0]
        assert leaf.name == "leaf"
        assert leaf.signature == '"value"'

    def test_scan_root_array_document(self, json_language):
        """A JSON document whose root is an array has no key to name it."""
        structures = json_language.scan(b'["a", "b", "c"]')
        assert len(structures) == 1
        node = structures[0]
        assert node.type == "array"
        assert node.signature == "3 items"
        assert node.synthetic is True

    def test_scan_empty_file(self, json_language):
        assert json_language.scan(b"") == []

    def test_scan_broken_json_does_not_crash(self, json_language, broken_json):
        structures = json_language.scan(broken_json)
        assert isinstance(structures, list)
