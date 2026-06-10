"""Oversized markdown (generated report tables) must use the regex fallback —
tree-sitter trees for 4MB pipe tables run to 1.3M nodes and dominated
directory analysis (measured: 68% of a 16s preview)."""

import time

from scantool.languages.markdown import MarkdownLanguage


def _giant_report() -> bytes:
    table_row = "| " + " | ".join(f"verdi_{i}" for i in range(12)) + " |\n"
    return (
        "# Resultater\n\n"
        "## Modellkjøring\n\n"
        + table_row * 90_000
        + "\n## Konklusjon\n\nTekst.\n"
    ).encode()


def _heading_names(structures) -> list[str]:
    names = []

    def walk(nodes):
        for node in nodes:
            names.append(node.name)
            walk(node.children or [])

    walk(structures)
    return names


class TestOversizedMarkdown:
    def test_fallback_keeps_headings(self):
        source = _giant_report()
        assert len(source) > MarkdownLanguage._TREE_SITTER_BYTE_LIMIT

        names = _heading_names(MarkdownLanguage().scan(source))

        assert "Resultater" in names
        assert "Konklusjon" in names

    def test_fallback_is_fast(self):
        source = _giant_report()

        t0 = time.perf_counter()
        MarkdownLanguage().scan(source)

        # regex-fallback skal være langt under tre-sitter-kostnaden (~0.5s+)
        assert time.perf_counter() - t0 < 0.5

    def test_small_files_still_use_tree_sitter(self):
        structures = MarkdownLanguage().scan(b"# Tittel\n\n```python\nx = 1\n```\n")

        all_types = {n.type for n in structures} | {
            c.type for n in structures for c in (n.children or [])}
        # kodeblokk-noder finnes kun i tree-sitter-veien
        assert "code-block" in all_types
