"""
FILE: languages/ipynb.py

PROBLEM:
  Jupyter notebooks were the one kind of source file that scanned to nothing:
  .ipynb had no handler, so a 128 kB notebook returned zero nodes, and eight
  notebooks changed on a branch without appearing in any structural diff. The
  content is all there — it is just wrapped in JSON, one string literal per
  source line.

SOLUTION:
  Parse the container once with stdlib json, then hand each cell's text to the
  handler that already understands it: PythonLanguage for code cells,
  MarkdownLanguage for markdown cells. Every node a sub-handler returns is
  re-addressed from its in-cell line to the .ipynb line that holds it, located
  by finding each source line's JSON encoding in the raw text.

ADDRESSING (the decision every consumer inherits):
  start_line/end_line hold lines of the .ipynb FILE, not of the cell. A JSON
  line number means little to a human reader, but it is the only number that is
  true for the bytes on disk, and three consumers hash or slice those bytes:
  focus.py prints source_lines[start-1:end], delta.node_hashes fingerprints the
  same slice, and ref_diff reuses that fingerprint. Cell-relative numbers would
  make all three read the wrong lines, and there is no place to teach them
  otherwise without a per-language special case. So the file line is the
  address, and the cell is the structure: each cell is a node whose children
  are the definitions inside it, so the address form path::Qualified.name reads
  `notebook.ipynb::cell 2 (code).Ledger.mean` — the cell index is the qualifier
  a reader needs, and it is right there in the tree. The in-cell span and where
  it lands in the file are stated once per cell, in the cell node's signature.

  Consequences, stated plainly:
  - focus on a cell's function prints the JSON-escaped lines (`    "def f():\\n",`)
    with their file line numbers. It is ugly, and it is the least bad option:
    the numbers match the file, so anything the reader does next — open the
    file, diff it, hash it — lands on the same bytes. Decoding the strings for
    display while keeping JSON line numbers would print lines that are not on
    those lines. The scan view does not pay that price: condense_excerpt below
    decodes the literals, and skeletons are shown without line numbers, which
    is exactly what a decoded view may claim.
  - A cell node's name ("cell 2 (code)") is scantool's label, not the source's,
    so it is synthetic=True. Its identity is positional: inserting a cell
    renumbers the ones after it, and delta/ref_diff will report those as
    changed. Cell ids exist in nbformat >= 4.5 but are opaque hashes; a reader
    cannot use one to find the cell, so position wins.

SCOPE:
  ✓ Code cells via the Python handler: imports, functions, classes, methods
  ✓ Markdown cells via the Markdown handler: headings, code blocks
  ✓ Raw cells as addressable, diffable nodes with no inner structure
  ✓ Both documented shapes of `source` (list of lines, or one string)
  ✓ IPython magics and shell escapes masked so they cannot derail a cell's parse
  ✓ Calls from the code cells, through the Python handler with the notebook's
    own definitions, so a notebook is a call-graph node like a module: callers,
    divergence, hot functions and the diff's call relations see its edges. A
    call at the top of a cell is module level (caller_name None), the same
    convention as top-level code in a .py file.
  ✗ CLAIMS_DEAD stays False: a notebook definition with no caller in the corpus
    is run from the cells themselves and the kernel, channels no call graph
    sees, so the framework never calls one dead.
  ✗ No outputs: execution results are data, not structure
"""

import json
import re
import textwrap
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from .base import BaseLanguage
from .markdown import MarkdownLanguage
from .models import CallInfo, DefinitionInfo, EntryPointInfo, ImportInfo, StructureNode
from .python import PythonLanguage

# A line is IPython, not Python, when it opens with a magic (%timeit, %%bash)
# or a shell escape (!pip install). `% b` and `!= b` are excluded: those are
# operators on a continuation line.
_IPYTHON_LINE = re.compile(r"[ \t]*(?:%{1,2}[A-Za-z_]|![^=\s])")


class _Lined(Protocol):
    """What a semantic pass returns: a record addressed by one line."""

    line: int


L = TypeVar("L", bound=_Lined)


@dataclass
class _Cell:
    """One notebook cell: its text, and the .ipynb line every source line is on."""

    index: int
    cell_type: str
    text: str
    # in-cell line (1-based, via _at) -> .ipynb line (1-based)
    file_lines: list[int] = field(default_factory=list)


def _at(file_lines: list[int], line: int) -> int:
    """The .ipynb line for an in-cell line, clamped to the cell. A sub-handler
    may report an end_line one past the last source line (a trailing newline
    makes an empty final line); the cell's own last line is the honest answer."""
    return file_lines[min(max(line, 1), len(file_lines)) - 1]


def _readdress(nodes: list[StructureNode], file_lines: list[int]) -> None:
    """Move a cell's nodes from in-cell lines onto .ipynb lines, in place."""
    for node in nodes:
        node.start_line = _at(file_lines, node.start_line)
        node.end_line = max(_at(file_lines, node.end_line), node.start_line)
        _readdress(node.children, file_lines)


def _source_chunks(cell: object) -> list[str]:
    """nbformat writes `source` either as a list of lines or as one string."""
    source = cell.get("source") if isinstance(cell, dict) else None
    if isinstance(source, str):
        return [source]
    if isinstance(source, list):
        return [chunk for chunk in source if isinstance(chunk, str)]
    return []


def _locate(text: str, line_starts: list[int], chunk: str, cursor: int) -> tuple[int, int]:
    """The .ipynb line holding `chunk`, found by its JSON encoding from `cursor`
    forward. Returns (cursor past the match, line). Writers differ on escaping
    non-ASCII, so both encodings are tried; if neither is found — a hand-edited
    file with unusual escapes — the chunk is addressed at the cursor's own line,
    which keeps it inside the cell and never past it."""
    for encoded in (json.dumps(chunk), json.dumps(chunk, ensure_ascii=False)):
        found = text.find(encoded, cursor)
        if found != -1:
            return found + len(encoded), bisect_right(line_starts, found)
    return cursor, bisect_right(line_starts, cursor)


def _mask_ipython(source: str) -> str:
    """Comment out magics and shell escapes so the rest of the cell still parses.

    The line count is preserved, so every line number is too. The masked text is
    only ever parsed — every byte displayed comes from the file itself — so
    masking a look-alike line inside a string literal changes nothing a reader
    sees, and nothing a line number points at.
    """
    return "\n".join(
        "# " + line if _IPYTHON_LINE.match(line) else line for line in source.split("\n")
    )


class JupyterLanguage(BaseLanguage):
    """Unified language handler for Jupyter notebooks (.ipynb).

    Composes the Python and Markdown handlers over a notebook's cells; owns the
    JSON container and the in-cell -> file line mapping, nothing else.
    """

    # Code cells are Python; markdown cells have no keyworded rows
    _ROW_KEYWORDS = PythonLanguage._ROW_KEYWORDS

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._cell_languages: dict[str, BaseLanguage] = {
            "code": PythonLanguage(**kwargs),
            "markdown": MarkdownLanguage(**kwargs),
        }

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".ipynb"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Jupyter"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Structure Scanning
    # ===========================================================================

    def scan(self, source_code: bytes) -> list[StructureNode] | None:
        """Scan a notebook: one node per non-empty cell, cell structure beneath."""
        try:
            cells = self._parse_cells(source_code.decode("utf-8", errors="replace"))
        except ValueError as e:
            return [
                StructureNode(type="error", name=f"Failed to parse: {e}", start_line=1, end_line=1)
            ]

        structures = []
        for cell in cells:
            first, last = cell.file_lines[0], cell.file_lines[-1]
            node = StructureNode(
                type="cell",
                name=f"cell {cell.index} ({cell.cell_type})",
                start_line=first,
                end_line=last,
                signature=f"in-cell 1-{len(cell.file_lines)} at {first}-{last}",
                synthetic=True,  # the label is scantool's, not the notebook's
            )
            node.children = self._cell_structure(cell)
            structures.append(node)
        return structures

    def _cell_structure(self, cell: _Cell) -> list[StructureNode]:
        """Structure of one cell, addressed in .ipynb lines."""
        language = self._cell_languages.get(cell.cell_type)
        if language is None:
            return []  # raw cells (and any future type) are content, not structure
        nodes = language.scan(cell.text.encode("utf-8")) or []
        _readdress(nodes, cell.file_lines)
        return nodes

    def _parse_cells(self, text: str) -> list[_Cell]:
        """Cells with content, each carrying its in-cell -> file line mapping.

        Raises ValueError when the file is not a notebook (json.JSONDecodeError
        is a ValueError, so a malformed container lands here too).
        """
        notebook = json.loads(text)
        if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
            raise ValueError("not a Jupyter notebook: no cell list")

        line_starts = [0, *(match.end() for match in re.finditer("\n", text))]
        cells: list[_Cell] = []
        cursor = 0
        for index, raw in enumerate(notebook["cells"], start=1):
            file_lines: list[int] = []
            chunks = _source_chunks(raw)
            for chunk in chunks:
                cursor, line = _locate(text, line_starts, chunk, cursor)
                # one chunk is normally one line; a whole-cell string is one
                # JSON line holding all of them, and they share that line
                file_lines.extend([line] * max(1, len(chunk.splitlines())))
            source = "".join(chunks)
            if not source.strip():
                continue  # an empty cell has nothing to address and nothing to diff
            cell_type = raw.get("cell_type") if isinstance(raw, dict) else None
            cells.append(
                _Cell(
                    index=index,
                    cell_type=str(cell_type or "raw"),
                    text=_mask_ipython(source),
                    file_lines=file_lines,
                )
            )
        return cells

    def _cells(self, content: str) -> list[_Cell]:
        """Cells for the semantic passes, which get text rather than bytes."""
        try:
            return self._parse_cells(content)
        except ValueError:
            return []

    def condense_excerpt(self, excerpt_lines: list[str]) -> list[str] | None:
        """Decode the JSON string literals an excerpt consists of, then condense.

        A notebook's bytes are JSON; the code a reader wants is inside the
        literals. Decoding them is this language's condensation — and it is
        sound precisely because the formatter prints skeletons without line
        numbers, so a decoded view never claims to be at a given line. Lines
        that are not string literals (`"source": [`, `],`) are container, not
        content, and are dropped. None when nothing decoded: verbatim then.

        Decoded Python is then condensed by the Python handler, which answers
        None for anything that does not parse — the same verdict it gives for
        prose, so a markdown cell simply keeps its decoded text.
        """
        decoded: list[str] = []
        for line in excerpt_lines:
            literal = line.strip().rstrip(",")
            if not (literal.startswith('"') and literal.endswith('"')):
                continue
            try:
                text = json.loads(literal)
            except ValueError:
                continue
            decoded.extend(text.rstrip("\n").split("\n"))
        if not decoded:
            return None

        # a node's own indentation carried no information once it left the cell
        decoded = textwrap.dedent("\n".join(decoded)).split("\n")
        skeleton = self._cell_languages["code"].condense_excerpt(decoded)
        # an all-folded skeleton ("…" only) says less than the text it replaced
        if skeleton and any(line.strip() != "…" for line in skeleton):
            return skeleton
        return decoded

    # ===========================================================================
    # Semantic Analysis
    # ===========================================================================

    def _python_pass(self, content: str, extract: Callable[[str], list[L]]) -> list[L]:
        """One Python semantic pass over every code cell, each record moved from
        its in-cell line onto the .ipynb line. Markdown cells carry links and
        prose, not dependencies, entry points or calls."""
        found: list[L] = []
        for cell in self._cells(content):
            if cell.cell_type != "code":
                continue
            for info in extract(cell.text):
                info.line = _at(cell.file_lines, info.line)
                found.append(info)
        return found

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Python imports from the code cells, on their .ipynb lines."""
        python = self._cell_languages["code"]
        return self._python_pass(content, lambda text: python.extract_imports(file_path, text))

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """Python entry points declared in the code cells, on their .ipynb lines."""
        python = self._cell_languages["code"]
        return self._python_pass(content, lambda text: python.find_entry_points(file_path, text))

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Python calls from the code cells, on their .ipynb lines.

        `definitions` are the notebook's own (code_map extracts them from this
        handler's scan), passed through unchanged: the Python handler attributes
        a call to the nearest enclosing definition among them, and to no one
        (module level) at the top of a cell — so a notebook and a module obey
        the same caller-resolution contract.
        """
        python = self._cell_languages["code"]
        return self._python_pass(
            content, lambda text: python.extract_calls(file_path, text, definitions)
        )
