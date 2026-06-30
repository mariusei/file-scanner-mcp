"""Tests for content_search: grep parity on location, structural context
on top. A hit must come back with the node chain it lives in — in any
file type."""

from scantool.content_search import search_content, format_hits
from scantool.scanner import FileScanner


def scan(tmp_path, files: dict[str, str]):
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    return FileScanner().scan_directory(str(tmp_path), pattern="**/*")


PY_FILE = '''\
import zlib


class Compressor:
    def conditional(self, data, context):
        co = zlib.compressobj(level=6, zdict=context)
        return co.compress(data)

    def plain(self, data):
        return zlib.compress(data, 9)


def unrelated():
    return 42
'''


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
        results = scan(tmp_path, {"doc.md": (
            "# Innledning\n\nGenerelt stoff.\n\n"
            "# Konfigurasjon\n\nSett zdict-parameteren for kontekst.\n"
        )})

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
        results = scan(tmp_path, {
            "aaa_sparse.py": "def one_mention():\n    return target_term()\n",
            "zzz_dense.py": "\n".join(
                f"def dense_{i}():\n    return target_term_{i}()\n" for i in range(4)
            ).replace("target_term_", "target_term_x"),
        })

        found = search_content(results, "target_term")

        assert "zzz_dense.py" in found[0].file  # densest first, despite filename

    def test_leads_point_to_definitions_in_other_files(self, tmp_path):
        from scantool.content_search import find_leads

        results = scan(tmp_path, {
            "caller.py": '''\
def orchestrate(items):
    if check_skipif(items):
        return evaluate_condition(items)
    return None
''',
            "lib.py": '''\
def evaluate_condition(items):
    return all(i.valid for i in items)
''',
        })

        found = search_content(results, "skipif")
        leads = find_leads(found, results)

        assert any(name == "evaluate_condition"
                   and any("lib.py" in f for f, _ in targets)
                   for name, targets in leads)

    def test_no_lead_for_same_file_definitions(self, tmp_path):
        from scantool.content_search import find_leads

        results = scan(tmp_path, {"solo.py": '''\
def orchestrate(items):
    return local_helper(items)  # skipif-relatert


def local_helper(items):
    return items
'''})

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

        results = scan(tmp_path, {
            "caller.py": "def run(x):\n    return transform_payload(x)  # skipif\n",
            "lib.py": "def transform_payload(x):\n    return x * 2\n",
        })
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
        results = scan(tmp_path, {
            "code.py": "def find_lake():\n    return 'lake'\n",
            "lakes.geojson": '{"features": ["lake", "lake", "lake"]}\n',
        })

        found = search_content(results, "lake")

        assert {h.file.split("/")[-1] for h in found} == {"code.py"}
