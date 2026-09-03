"""Tests for content_search: grep parity on location, structural context
on top. A hit must come back with the node chain it lives in — in any
file type."""

import json
from pathlib import Path

from scantool.content_search import (
    find_leads,
    format_hits,
    hits_to_json,
    search_content,
)
from scantool.scanner import FileScanner
from scantool.server import search_structures


def scan(tmp_path, files: dict[str, str]):
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    return FileScanner().scan_directory(str(tmp_path), pattern="**/*")


PY_FILE = """\
import zlib


class Compressor:
    def conditional(self, data, context):
        co = zlib.compressobj(level=6, zdict=context)
        return co.compress(data)

    def plain(self, data):
        return zlib.compress(data, 9)


def unrelated():
    return 42
"""


class TestContentSearch:
    def test_hit_maps_to_deepest_node_chain(self, tmp_path):
        results = scan(tmp_path, {"comp.py": PY_FILE})

        found = search_content(results, "zdict")

        assert len(found) == 1
        assert found[0].chain == "Compressor > conditional"
        assert found[0].hits[0][0] == 6  # line numbers kept — grep parity

    def test_hits_grouped_per_node(self, tmp_path):
        results = scan(tmp_path, {"comp.py": PY_FILE})

        found = search_content(results, "zlib")

        chains = {h.chain: len(h.hits) for h in found}
        assert chains["Compressor > conditional"] == 1
        assert chains["Compressor > plain"] == 1
        assert chains["(module level)"] == 1  # the import line

    def test_markdown_hit_returns_section(self, tmp_path):
        results = scan(
            tmp_path,
            {
                "doc.md": (
                    "# Innledning\n\nGenerelt stoff.\n\n"
                    "# Konfigurasjon\n\nSett zdict-parameteren for kontekst.\n"
                )
            },
        )

        found = search_content(results, "zdict")

        assert len(found) == 1
        assert "Konfigurasjon" in found[0].chain

    def test_case_insensitive_by_default(self, tmp_path):
        results = scan(tmp_path, {"comp.py": PY_FILE})

        assert search_content(results, "ZDICT")
        assert not search_content(results, "ZDICT", ignore_case=False)

    def test_no_hits_message(self, tmp_path):
        results = scan(tmp_path, {"comp.py": PY_FILE})

        found = search_content(results, "finnes_ikke_xyz")

        assert found == []
        assert "No content matches" in format_hits(found, "finnes_ikke_xyz")

    def test_format_shows_chain_and_lines(self, tmp_path):
        results = scan(tmp_path, {"comp.py": PY_FILE})

        output = format_hits(search_content(results, "zdict"), "zdict")

        assert "Compressor > conditional" in output
        assert "6 | " in output
        assert "comp.py" in output

    def test_densest_file_ranked_first(self, tmp_path):
        """Caps must keep the most relevant structures — densest files first."""
        results = scan(
            tmp_path,
            {
                "aaa_sparse.py": "def one_mention():\n    return target_term()\n",
                "zzz_dense.py": "\n".join(
                    f"def dense_{i}():\n    return target_term_{i}()\n" for i in range(4)
                ).replace("target_term_", "target_term_x"),
            },
        )

        found = search_content(results, "target_term")

        assert "zzz_dense.py" in found[0].file  # densest first, despite filename

    def test_leads_point_to_definitions_in_other_files(self, tmp_path):
        from scantool.content_search import find_leads

        results = scan(
            tmp_path,
            {
                "caller.py": """\
def orchestrate(items):
    if check_skipif(items):
        return evaluate_condition(items)
    return None
""",
                "lib.py": """\
def evaluate_condition(items):
    return all(i.valid for i in items)
""",
            },
        )

        found = search_content(results, "skipif")
        leads = find_leads(found, results)

        assert any(
            name == "evaluate_condition" and any("lib.py" in f for f, _ in targets)
            for name, targets in leads
        )

    def test_no_lead_for_same_file_definitions(self, tmp_path):
        from scantool.content_search import find_leads

        results = scan(
            tmp_path,
            {
                "solo.py": """\
def orchestrate(items):
    return local_helper(items)  # skipif-relatert


def local_helper(items):
    return items
"""
            },
        )

        found = search_content(results, "skipif")

        assert find_leads(found, results) == []

    def test_ambiguous_names_excluded(self, tmp_path):
        from scantool.content_search import find_leads

        files = {"caller.py": "def run():\n    return process_widget()  # skipif\n"}
        for i in range(3):
            files[f"impl_{i}.py"] = "def process_widget():\n    return 1\n"
        results = scan(tmp_path, files)

        found = search_content(results, "skipif")

        # defined in 3 files — too ambiguous to be a lead
        assert find_leads(found, results) == []

    def test_leads_rendered_in_output(self, tmp_path):
        from scantool.content_search import find_leads

        results = scan(
            tmp_path,
            {
                "caller.py": "def run(x):\n    return transform_payload(x)  # skipif\n",
                "lib.py": "def transform_payload(x):\n    return x * 2\n",
            },
        )
        found = search_content(results, "skipif")

        output = format_hits(found, "skipif", find_leads(found, results))

        assert "leads (called in hits, defined elsewhere):" in output
        assert "transform_payload → " in output

    def test_hit_cap_per_node(self, tmp_path):
        body = "\n".join(f"    target_{i} = call_{i}()" for i in range(8))
        results = scan(tmp_path, {"many.py": f"def crowded():\n{body}\n"})

        output = format_hits(search_content(results, "target_"), "target_")

        assert "+4 more in this structure" in output

    def test_unsupported_stub_not_read(self, tmp_path):
        # An unsupported file type (e.g. multi-GB geodata) is carried as a
        # file-info stub with no parseable structure; read_text()'ing it is
        # ruinously slow and yields no structural context. The matching hit
        # must come only from the supported file, never the stub.
        results = scan(
            tmp_path,
            {
                "code.py": "def find_lake():\n    return 'lake'\n",
                "lakes.geojson": '{"features": ["lake", "lake", "lake"]}\n',
            },
        )

        found = search_content(results, "lake")

        assert {Path(h.file).name for h in found} == {"code.py"}


class TestJsonOutput:
    """`output_format="json"` is a contract, not a suggestion: both branches of
    search_structures must honour it, and the JSON must answer the same
    question the tree does."""

    def test_content_pattern_json_is_parseable(self, tmp_path):
        (tmp_path / "comp.py").write_text(PY_FILE)

        out = search_structures.fn(str(tmp_path), content_pattern="zdict", output_format="json")[
            0
        ].text

        data = json.loads(out)
        assert data["pattern"] == "zdict"
        assert data["total_hits"] == 1
        chains = [s["chain"] for s in data["structures"]]
        assert any("conditional" in chain for chain in chains)

    def test_name_pattern_json_is_parseable(self, tmp_path):
        (tmp_path / "comp.py").write_text(PY_FILE)

        out = search_structures.fn(str(tmp_path), name_pattern="unrelated", output_format="json")[
            0
        ].text

        json.loads(out)

    def test_json_and_tree_report_the_same_selection(self, tmp_path):
        results = scan(tmp_path, {"comp.py": PY_FILE})
        found = search_content(results, "zlib")
        leads = find_leads(found, results)

        data = hits_to_json(found, "zlib", leads)
        tree = format_hits(found, "zlib", leads)

        assert data["total_hits"] == sum(len(n.hits) for n in found)
        assert data["total_structures"] == len(found)
        assert data["structures"], "sanity: the fixture must produce hits"
        for structure in data["structures"]:
            assert structure["chain"] in tree
            for hit in structure["hits"]:
                assert f"{hit['line']} |" in tree

    def test_caps_are_reported_not_silently_applied(self, tmp_path):
        many = "\n".join(f"def f{i}():\n    return marker\n" for i in range(45))
        results = scan(tmp_path, {"many.py": many})
        found = search_content(results, "marker")

        data = hits_to_json(found, "marker")

        assert data["total_structures"] == len(found)
        assert len(data["structures"]) < data["total_structures"]
        assert data["structures_omitted"] == data["total_structures"] - len(data["structures"])
