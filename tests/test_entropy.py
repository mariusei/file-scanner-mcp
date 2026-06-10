"""Tests for entropy-based saliency analysis (entropy/core.py + callgraph.py)."""

from scantool.entropy.core import (
    _find_indentation_blocks,
    _partition_by_patterns,
    analyze_file_entropy,
)


def _boundary_count(source: bytes) -> int:
    patterns = _find_indentation_blocks(source)
    return len(patterns[0]["positions"]) if patterns else 0


class TestTabIndentation:
    """Tabs must count as an indent level — Go/C/Makefiles partition like
    space-indented files (regression: 148-line Go file got 3 partitions)."""

    SPACE_SOURCE = (
        b"func a() {\n"
        b"    x := compute()\n"
        b"    if x > 0 {\n"
        b"        return x\n"
        b"    }\n"
        b"}\n"
        b"func b() {\n"
        b"    return fallback()\n"
        b"}\n"
    )

    def test_tabs_and_spaces_partition_identically(self):
        tab_source = self.SPACE_SOURCE.replace(b"    ", b"\t")

        assert _boundary_count(tab_source) == _boundary_count(self.SPACE_SOURCE)
        assert _boundary_count(tab_source) > 0

    def test_tab_file_gets_function_granularity(self, tmp_path):
        # 8 tab-indented functions — partitioning must separate them
        source = "\n".join(
            f"func transform{i}(items []Item) []Item {{\n"
            f"\tresults := make([]Item, 0)\n"
            f"\tfor _, item := range items {{\n"
            f"\t\tif item.Score > {i}.5 {{\n"
            f"\t\t\tresults = append(results, normalize(item))\n"
            f"\t\t}}\n"
            f"\t}}\n"
            f"\treturn aggregate(results, {i})\n"
            f"}}\n"
            for i in range(8)
        )
        path = tmp_path / "sample.go"
        path.write_text(source)

        data = source.encode()
        partitions = _partition_by_patterns(data, _find_indentation_blocks(data))

        # one giant partition would mean selection can't differentiate functions
        assert len(partitions) >= 8


class TestStructureReuse:
    """Passing already-scanned structures must give the same result as the
    internal re-scan — it only skips the second tree-sitter parse."""

    def test_saliency_identical_with_and_without_structures(self, tmp_path):
        source = "\n".join(
            f'''\
def transform_{i}(items, threshold):
    results = []
    for item in items:
        if item.score > threshold * {i + 1}:
            results.append(normalize(item, mode="strict_{i}"))
    return aggregate(results, weights=[0.{i}1, 0.{i}2])
'''
            for i in range(6)
        )
        path = tmp_path / "sample.py"
        path.write_text(source)

        from scantool.languages import get_language
        structures = get_language(".py").scan(source.encode())

        with_reuse = analyze_file_entropy(str(path), structures=structures)
        with_rescan = analyze_file_entropy(str(path))

        assert [(p.start_line, p.end_line, round(p.saliency, 9)) for p in with_reuse] == \
               [(p.start_line, p.end_line, round(p.saliency, 9)) for p in with_rescan]
        assert with_reuse  # non-empty: analysis actually ran
