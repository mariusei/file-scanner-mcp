"""Tests for Jupyter notebooks (.ipynb).

The load-bearing property is the addressing: a node's line numbers are lines of
the .ipynb file, so focus, delta hashing and ref diff read the right bytes. Most
of these tests assert exactly that — the name a node carries must be findable on
the file line the node claims.
"""

import json
from pathlib import Path

import pytest
from conftest import validate_line_range_invariants

from scantool.focus import format_focus
from scantool.languages import get_language
from scantool.languages.ipynb import JupyterLanguage

SAMPLE = Path(__file__).parent / "samples" / "basic.ipynb"


def _nodes(structures, ancestors=()):
    for node in structures:
        yield node, ancestors
        yield from _nodes(node.children, (*ancestors, node))


@pytest.fixture
def sample_lines():
    return SAMPLE.read_text(encoding="utf-8").split("\n")


@pytest.fixture
def structures(file_scanner):
    return file_scanner.scan_file(str(SAMPLE), include_file_metadata=False)


def test_extension_is_registered():
    language = get_language(".ipynb")
    assert isinstance(language, JupyterLanguage)
    assert language.get_language_name() == "Jupyter"


def test_cells_become_nodes(structures):
    assert [node.name for node in structures] == [
        "cell 1 (markdown)",
        "cell 2 (code)",
        "cell 3 (raw)",
    ]
    # a made-up label is never an identity a consumer may pair files on
    assert all(node.synthetic for node in structures)


def test_code_cell_yields_python_structure(structures):
    code_cell = structures[1]
    assert [child.name for child in code_cell.children] == [
        "import statements",
        "total",
        "Ledger",
    ]
    assert [child.name for child in code_cell.children[2].children] == ["__init__", "mean"]


def test_markdown_cell_yields_headings(structures):
    assert [child.name for child in structures[0].children] == ["Sales ledger"]


def test_raw_cell_is_addressable_but_has_no_inner_structure(structures):
    raw = structures[2]
    assert raw.children == []
    assert raw.end_line >= raw.start_line


def test_line_numbers_address_the_notebook_file(structures, sample_lines):
    """The decisive property: every source name sits on the .ipynb line the
    node points at, so focus and the node hashes read the right bytes."""
    for node, _ in _nodes(structures):
        if node.synthetic:
            continue
        assert node.name in sample_lines[node.start_line - 1], node


def test_cell_signature_states_the_in_cell_span(structures):
    code_cell = structures[1]
    assert code_cell.signature == (f"in-cell 1-16 at {code_cell.start_line}-{code_cell.end_line}")


def test_line_range_invariants(structures):
    validate_line_range_invariants(structures)


def test_focus_reads_the_notebook_bytes(structures, sample_lines):
    """focus prints the JSON-escaped lines — ugly, but at the line numbers the
    file actually has, which is what any follow-up read depends on."""
    rendered = format_focus(str(SAMPLE), structures, sample_lines, "Ledger.mean")
    assert "focus: cell 2 (code).Ledger.mean" in rendered
    assert '"    def mean(self):\\n",' in rendered


def test_imports_are_reported_on_their_notebook_line(sample_lines):
    language = JupyterLanguage()
    imports = language.extract_imports("basic.ipynb", SAMPLE.read_text(encoding="utf-8"))
    assert [imp.target_module for imp in imports] == ["statistics"]
    assert "import statistics" in sample_lines[imports[0].line - 1]


def test_condense_excerpt_decodes_the_json_literals():
    language = JupyterLanguage()
    excerpt = ['    "def f(x):\\n",', '    "    return x + 1\\n"']
    assert language.condense_excerpt(excerpt) == ["return x + 1"]


def test_condense_excerpt_keeps_prose_that_is_not_python():
    language = JupyterLanguage()
    assert language.condense_excerpt(['    "# Title\\n",', '    "Some prose."']) == [
        "# Title",
        "Some prose.",
    ]


def test_condense_excerpt_declines_container_lines():
    language = JupyterLanguage()
    assert language.condense_excerpt(['   "source": [', "   ],"]) is None


def _notebook(*cells: dict) -> str:
    return json.dumps({"cells": list(cells), "nbformat": 4, "nbformat_minor": 5}, indent=1)


def test_ipython_magics_do_not_derail_the_cell():
    """A magic is not Python. Masked as a comment, the cell around it still
    parses — and the mask keeps the line count, so the mapping is unmoved."""
    source = ["%matplotlib inline\n", "!pip install pandas\n", "def plot(df):\n", "    return df\n"]
    notebook = _notebook({"cell_type": "code", "source": source})
    structures = JupyterLanguage().scan(notebook.encode("utf-8"))
    names = [child.name for child in structures[0].children]
    assert names == ["plot"]
    assert "def plot(df):" in notebook.split("\n")[structures[0].children[0].start_line - 1]


def test_operators_on_a_continuation_line_are_not_mistaken_for_magics():
    source = ["def rest(a, b):\n", "    return (a\n", "            % b)\n"]
    structures = JupyterLanguage().scan(_notebook({"cell_type": "code", "source": source}).encode())
    assert [child.name for child in structures[0].children] == ["rest"]


def test_source_written_as_one_string_stays_inside_its_cell():
    """nbformat allows `source` as a single string. All of its lines then live
    on one .ipynb line, and that is what the nodes must say."""
    notebook = _notebook({"cell_type": "code", "source": "def one():\n    return 1\n"})
    structures = JupyterLanguage().scan(notebook.encode("utf-8"))
    cell = structures[0]
    function = cell.children[0]
    assert cell.start_line == cell.end_line
    assert function.start_line == function.end_line == cell.start_line
    assert "def one()" in notebook.split("\n")[function.start_line - 1]


def test_empty_cells_are_dropped():
    notebook = _notebook(
        {"cell_type": "code", "source": []},
        {"cell_type": "code", "source": ["x = 1\n"]},
    )
    structures = JupyterLanguage().scan(notebook.encode("utf-8"))
    assert [node.name for node in structures] == ["cell 2 (code)"]


def test_a_file_that_is_not_a_notebook_reports_the_parse_failure():
    structures = JupyterLanguage().scan(b"{not json at all")
    assert structures is not None
    assert structures[0].type == "error"
    assert structures[0].synthetic

    structures = JupyterLanguage().scan(b'{"nbformat": 4}')
    assert structures is not None
    assert structures[0].type == "error"
