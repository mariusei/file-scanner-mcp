"""Pretty tree formatter for file structure with rich metadata display."""

import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .languages import StructureNode, get_registry

# Experiment flag: rows carry the language keyword before the name and their
# decorators inline (`- def list_items(limit: int) -> list @13 @router.get`),
# so grepping scan output for the keyword finds the names it would find in
# the source. The keywords live in each language handler. Unset: the frozen
# output contract, byte for byte.
ROW_KEYWORD_ENV = "SCANTOOL_ROW_KEYWORD"
INLINE_DECORATOR_WIDTH = 60


def _no_keyword(node: StructureNode) -> str | None:
    return None


def _inline_decorator(decorator: str) -> str:
    """One decorator as a row token: whitespace collapsed, cut to the width."""
    text = " ".join(decorator.split())
    if len(text) > INLINE_DECORATOR_WIDTH:
        return text[: INLINE_DECORATOR_WIDTH - 1] + "…"
    return text


def _spans_source(node: StructureNode) -> bool:
    return (node.start_line > 0 or node.end_line > 0) and node.file_metadata is None


def _walk(structures: list[StructureNode]):
    for node in structures:
        if node.type != "file-info":
            yield node
        yield from _walk(node.children)


def file_coverage(structures: list[StructureNode]) -> dict:
    """What a single-file answer shows and what the budget cut."""
    nodes = list(_walk(structures))
    return {
        "files_seen": 1,
        "structures_shown": len(nodes),
        "elided": sum(1 for node in nodes if node.elided),
    }


def next_focus(structures: list[StructureNode]) -> str | None:
    """The qualified name of the elided node hiding the most lines: the one
    call that recovers the most of what the budget cut, or None."""

    def walk(nodes, ancestors=()):
        for node in nodes:
            if node.type != "file-info":
                yield node, ancestors
            yield from walk(node.children, (*ancestors, node))

    elided = [(node, anc) for node, anc in walk(structures) if node.elided]
    if not elided:
        return None
    node, ancestors = max(elided, key=lambda pair: pair[0].end_line - pair[0].start_line)
    return ".".join(n.name for n in (*ancestors, node))


def format_file_coverage(structures: list[StructureNode]) -> str:
    """The line every single-file answer opens with. Elided nodes are the
    ones a budget cut to a header: shown as ⟨…⟩ +N in the tree, readable in
    full with focus."""
    coverage = file_coverage(structures)
    shown = coverage["structures_shown"]
    parts = ["1 file seen", f"{shown} structure{'' if shown == 1 else 's'} shown"]
    if coverage["elided"]:
        parts.append(f"{coverage['elided']} elided (budget)")
    return "<" + ", ".join(parts) + ">"


def structures_to_json(structures: list[StructureNode], file_path: str, return_dict: bool = False):
    """The JSON output format: one document per file, nodes nested as in the
    tree. Optional fields appear only when set; synthetic only when true."""

    def node_to_dict(node: StructureNode) -> dict:
        result: dict = {
            "type": node.type,
            "name": node.name,
            "start_line": node.start_line,
            "end_line": node.end_line,
        }
        if node.synthetic:
            result["synthetic"] = True
        if node.signature:
            result["signature"] = node.signature
        if node.decorators:
            result["decorators"] = node.decorators
        if node.docstring:
            result["docstring"] = node.docstring
        if node.modifiers:
            result["modifiers"] = node.modifiers
        if node.complexity:
            result["complexity"] = node.complexity
        if node.children:
            result["children"] = [node_to_dict(child) for child in node.children]
        return result

    data = {"file": file_path, "structures": [node_to_dict(s) for s in structures]}
    return data if return_dict else json.dumps(data, indent=2)


class TreeFormatter:
    """Formats structure nodes as a pretty tree with metadata."""

    # Outline markers. ASCII bullets + plain indentation: box-drawing glyphs
    # are multi-byte and tokenize to 2-3 BPE tokens each — measured at 26%
    # of total output (experiments/entropy_metrics/)
    BRANCH = "-"
    LAST_BRANCH = "-"
    VERTICAL = "  "  # 2-space indent
    SPACE = "  "  # 2-space indent

    def __init__(
        self,
        show_signatures: bool = True,
        show_decorators: bool = True,
        show_docstrings: bool = True,
        show_complexity: bool = False,
        condense: bool = True,
    ):
        """
        Initialize formatter with display options.

        Args:
            show_signatures: Display function signatures
            show_decorators: Display decorators
            show_docstrings: Display first line of docstrings
            show_complexity: Display complexity metrics
            condense: Show condensed skeletons (pseudocode lines without
                line numbers) instead of verbatim excerpts where available
        """
        self.show_signatures = show_signatures
        self.show_decorators = show_decorators
        self.show_docstrings = show_docstrings
        self.show_complexity = show_complexity
        self.condense = condense
        # Set per format() call from the experiment flag and the file's language
        self._inline_rows = False
        self._row_keyword: Callable[[StructureNode], str | None] = _no_keyword

    def format(self, file_path: str, structures: list[StructureNode]) -> str:
        """Format the structure as a pretty tree."""
        self._inline_rows = os.environ.get(ROW_KEYWORD_ENV) == "1"
        language = get_registry().get_class(Path(file_path).suffix) if self._inline_rows else None
        self._row_keyword = language._row_keyword if language else _no_keyword

        if not structures:
            return f"{Path(file_path).name} (empty file)"

        # The range covers nodes from the source; the file-info record sits
        # at line 1 without being content
        content_nodes = [s for s in self._flatten(structures) if _spans_source(s)]
        if content_nodes:
            min_line = min(s.start_line for s in content_nodes)
            max_line = max(s.end_line for s in content_nodes)
            lines = [f"{Path(file_path).name} ({min_line}-{max_line})"]
        else:
            lines = [f"{Path(file_path).name}"]

        for i, node in enumerate(structures):
            is_last = i == len(structures) - 1
            lines.extend(self._format_node(node, "", is_last))

        return "\n".join(lines)

    def _format_node(self, node: StructureNode, prefix: str, is_last: bool) -> list[str]:
        """Format a single node and its children with metadata."""
        lines = []

        # Current node connector
        connector = self.LAST_BRANCH if is_last else self.BRANCH

        # Special formatting for file-info nodes
        if node.type == "file-info" and node.file_metadata:
            meta = node.file_metadata

            # Format timestamp as readable datetime with unix timestamp
            modified_iso = meta.get("modified", "")
            if modified_iso:
                try:
                    dt = datetime.fromisoformat(modified_iso)
                    # Format as: 2025-10-17 14:30 with unix timestamp for LLM processing
                    readable = dt.strftime("%Y-%m-%d %H:%M")
                    unix_ts = int(dt.timestamp())
                    modified_str = f"{readable} [ts:{unix_ts}]"
                except Exception:
                    # Fallback to just date if parsing fails
                    modified_str = modified_iso.split("T")[0]
            else:
                modified_str = ""

            churn = meta.get("churn_90d")
            parts = [
                f"{prefix}{connector} {node.type}:",
                meta["size_formatted"],
                f"modified: {modified_str}" if modified_str else "",
                f"churn: {churn} commits/90d" if churn else "",
            ]
            lines.append(" ".join(p for p in parts if p))
            return lines

        # Build the main node line (token-optimized format)
        # Remove "type:" prefix (redundant), shorten line range format
        signature = node.signature if self.show_signatures and node.signature else ""
        keyword = self._row_keyword(node)
        if keyword:
            # `def name(args)`: a bracketed signature glues to the name as in
            # the source; a worded one (`extends Base`, `: byte`) keeps a space
            glue = "" if signature[:1] in ("(", "<", "[") else " "
            parts = [f"{prefix}{connector} {keyword} {node.name}{glue}{signature}".rstrip()]
        else:
            parts = [f"{prefix}{connector} {node.name}"]
            if signature:
                parts.append(signature)

        # Add line numbers in compact format @startline
        if node.start_line > 0 or node.end_line > 0:
            parts.append(f"@{node.start_line}")

        # Add modifiers if present; `async` folded into the keyword is not
        # repeated
        modifiers = node.modifiers
        if keyword and keyword.startswith("async "):
            modifiers = [m for m in modifiers if m != "async"]
        if modifiers:
            modifiers_str = " ".join(modifiers)
            parts.append(f"[{modifiers_str}]")

        # Per-node git activity (only set when counts differ across nodes)
        if node.recent_edits:
            parts.append(f"[{node.recent_edits} edits/90d]")

        # Delta mode: new/changed vs previous scan
        if node.delta_status:
            parts.append(f"[{node.delta_status}]")

        # Add complexity indicator if enabled
        if self.show_complexity and node.complexity:
            complexity_str = self._format_complexity(node.complexity)
            if complexity_str:
                parts.append(complexity_str)

        # Experiment: decorators inline, before the docstring comment
        if self.show_decorators and node.decorators and self._inline_rows:
            parts.extend(_inline_decorator(d) for d in node.decorators)

        # Add docstring inline as comment (token-optimized)
        if self.show_docstrings and node.docstring:
            parts.append(f"# {node.docstring}")

        lines.append(" ".join(parts))

        # Add decorators on separate lines (2-space indent, token-optimized)
        if self.show_decorators and node.decorators and not self._inline_rows:
            decorator_prefix = prefix + (self.SPACE if is_last else self.VERTICAL) + " "  # 2-space
            for decorator in node.decorators:
                lines.append(f"{decorator_prefix}{decorator}")

        # Add code for salient (high-entropy) nodes: condensed skeleton when
        # available, verbatim excerpt otherwise; a node the budget cut to its
        # header says so, with the number of lines focus= would show
        if node.elided:
            code_prefix = prefix + (self.SPACE if is_last else self.VERTICAL) + " "
            lines.append(f"{code_prefix}⟨…⟩ +{node.end_line - node.start_line}")
        elif node.code_skeleton and self.condense:
            # Plain pseudocode lines, no line numbers — that absence is what
            # distinguishes condensed skeletons from verbatim excerpts
            code_prefix = (
                prefix + (self.SPACE if is_last else self.VERTICAL) + " "
            )  # 2-space indent
            for line in node.code_skeleton:
                lines.append(f"{code_prefix}{line}")
        elif node.code_excerpt:
            code_prefix = (
                prefix + (self.SPACE if is_last else self.VERTICAL) + " "
            )  # 2-space indent

            # No blank line (token-optimized)
            # Compact line number format: {i} | instead of {i:4d} |
            for i, line in enumerate(node.code_excerpt, start=node.start_line):
                lines.append(f"{code_prefix}{i} | {line}")

        # Format children (2-space indent, token-optimized)
        if node.children:
            child_prefix = prefix + (self.SPACE if is_last else self.VERTICAL)

            for i, child in enumerate(node.children):
                is_last_child = i == len(node.children) - 1
                lines.extend(self._format_node(child, child_prefix, is_last_child))

        return lines

    def _format_complexity(self, complexity: dict) -> str:
        """Format complexity metrics as compact text (no emoji - cleaner output)."""
        parts = []

        if complexity.get("lines", 0) > 100:
            parts.append(f"L{complexity['lines']}")

        if complexity.get("max_depth", 0) > 5:
            parts.append(f"D{complexity['max_depth']}")

        if complexity.get("branches", 0) > 10:
            parts.append(f"B{complexity['branches']}")

        return " ".join(parts) if parts else ""

    def _flatten(self, structures: list[StructureNode]) -> list[StructureNode]:
        """Flatten structure tree to get all nodes."""
        result = []
        for node in structures:
            result.append(node)
            if node.children:
                result.extend(self._flatten(node.children))
        return result
