"""
FILE: parts.py

PROBLEM:
  A multi-part report cut by `| head -N` loses content silently: the reader
  cannot tell which parts fell below the cut, and cannot fetch one part
  alone.

SOLUTION:
  Every multi-part report describes itself on its first line — an
  inventory of part IDs with their rendered line counts, in body order —
  and each part opens with a header line carrying its ID, so `--part ID`
  prints that part alone after the same first line. This module holds what
  the reports share: the inventory text, the body assembly and the
  selection parse.

SCOPE:
  ✓ inventory text, body assembly, selection parse and validation
  ✗ the parts themselves: each report renders its own
"""

from collections.abc import Mapping, Sequence

from .commands import UsageError

Parts = Mapping[str, Sequence[str]]

# The IDs each report renders, in body order; the render functions key their
# parts by these and a test holds them to it.
OVERLAP_PARTS = ("branches", "history", "shared", "colliding", "order")
SURFACE_DIFF_PARTS = ("added", "changed", "moved", "removed")


def parts_inventory(parts: Parts, showing: Sequence[str] = ()) -> str:
    """`parts: a 3, b 7` — IDs with line counts as rendered, in body order,
    header lines included; with a selection `; showing b` follows, the
    counts still those of the full render, so the map stays complete."""
    text = "parts: " + ", ".join(f"{name} {len(lines)}" for name, lines in parts.items())
    if showing:
        text += "; showing " + ", ".join(showing)
    return text


def body(parts: Parts, showing: Sequence[str] = ()) -> list[str]:
    """Every part in order, or only the selected ones."""
    return [
        line for name, lines in parts.items() if not showing or name in showing for line in lines
    ]


def select_parts(part: str, known: Sequence[str], command: str) -> list[str]:
    """The IDs a `--part` value names (comma list), in the report's body
    order; an unknown ID is a usage error that lists the IDs."""
    wanted = [name.strip() for name in part.split(",") if name.strip()]
    for name in wanted:
        if name not in known:
            raise UsageError(f"sct {command}: unknown part {name!r}; parts: {', '.join(known)}")
    return [name for name in known if name in wanted]
