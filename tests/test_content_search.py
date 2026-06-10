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
        assert found[0].hits[0][0] == 6  # linjenummer beholdes — grep-paritet

    def test_hits_grouped_per_node(self, tmp_path):
        results = scan(tmp_path, {"comp.py": PY_FILE})

        found = search_content(results, "zlib")

        chains = {h.chain: len(h.hits) for h in found}
        assert chains["Compressor > conditional"] == 1
        assert chains["Compressor > plain"] == 1
        assert chains["(module level)"] == 1  # import-linjen

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

    def test_hit_cap_per_node(self, tmp_path):
        body = "\n".join(f"    target_{i} = call_{i}()" for i in range(8))
        results = scan(tmp_path, {"many.py": f"def crowded():\n{body}\n"})

        output = format_hits(search_content(results, "target_"), "target_")

        assert "+4 more in this structure" in output
