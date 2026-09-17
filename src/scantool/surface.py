"""
FILE: surface.py

PROBLEM:
  "What does this package export, and where is each name really defined?"
  In the field study three agents independently called this the most
  useful single call, and each rebuilt it with ast over git show.

SOLUTION:
  The generic half only: find the language that owns the package, ask it
  for the public surface (BaseLanguage.public_surface; Python's override
  follows __all__, lazy tables, TYPE_CHECKING and re-export chains), render
  the listing grouped by defining module with a coverage line, diff two
  surfaces with the direction stated. Nothing here knows a syntax.

SCOPE:
  ✓ any language with a handler: the default surface is its top-level
    definitions not marked private; Python overrides with the facade logic
  ✗ no parsing here; that is the language file's job
"""

import os
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .languages import get_registry
from .languages.models import Export
from .parts import SURFACE_DIFF_PARTS, body, parts_inventory


@dataclass
class Surface:
    package: str
    exports: list[Export]


def _read_from_disk(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_surface(package_dir: str, read_file: Callable[[str], str | None] | None = None) -> Surface:
    """The public surface of the package whose directory is given, by the
    language that owns most of its files."""
    package_dir = os.path.abspath(package_dir.rstrip("/\\"))
    registry = get_registry()
    extensions: Counter = Counter()
    for name in os.listdir(package_dir):
        extension = os.path.splitext(name)[1].lower()
        if os.path.isfile(os.path.join(package_dir, name)) and registry.get(extension):
            extensions[extension] += 1
    if not extensions:
        return Surface(os.path.basename(package_dir), [])
    language = registry.get(extensions.most_common(1)[0][0])
    exports = language.public_surface(package_dir, read_file or _read_from_disk) if language else []
    return Surface(os.path.basename(package_dir), exports)


# ── rendering ────────────────────────────────────────────────────────────────


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def format_surface(surface: Surface, label: str) -> str:
    """Grouped by defining module; the coverage line counts how names got out."""
    vias = Counter(
        export.via for export in surface.exports if export.kind not in ("external", "unresolved")
    )
    listed = sum(1 for e in surface.exports if e.listed)
    external = sum(1 for e in surface.exports if e.kind == "external")
    unresolved = sum(1 for e in surface.exports if e.kind == "unresolved")
    parts = [_count(len(surface.exports), "public name") + (" in __all__" if listed else "")]
    parts += [f"{n} via {via}" for via, n in vias.most_common()]
    if external:
        parts.append(f"{external} outside the package")
    if unresolved:
        parts.append(f"{unresolved} unresolved")
    lines = [f"<{', '.join(parts)}> package {surface.package} {label}".rstrip()]
    groups: dict[str, list[Export]] = {}
    for export in surface.exports:
        groups.setdefault(export.module or "(unresolved)", []).append(export)
    for module, exports in groups.items():
        lines.append(module)
        width = min(max(len(e.name) + 2 + len(e.signature) for e in exports), 96)
        for export in exports:
            row = f"  {(export.name + '  ' + export.signature).ljust(width)}   {export.location}"
            if export.via != "definition":
                row += f"   via {export.via}"
            lines.append(row.rstrip())
            for inherited in export.inherited:
                lines.append(f"    inherited from {inherited}")
    return "\n".join(lines)


def diff_direction(label_a: str, label_b: str) -> str:
    """Bind the A/B side labels the diff rows use: ``A=@main → B=@next``."""
    return f"A={label_a} → B={label_b}"


def diff_parts(a: Surface, b: Surface) -> dict[str, list[str]]:
    """The diff body, every part in body order: names added, changed
    (signature), moved (module or file) or removed between A and B. A
    non-empty part opens with a header line carrying its ID; an empty one
    renders nothing but keeps its place in the inventory."""
    old = {e.name: e for e in a.exports}
    new = {e.name: e for e in b.exports}
    added = [n for n in new if n not in old]
    removed = [n for n in old if n not in new]
    changed = [n for n in old if n in new and old[n].signature != new[n].signature]
    moved = [
        n
        for n in old
        if n in new
        and n not in changed
        and (old[n].path, old[n].module) != (new[n].path, new[n].module)
    ]
    rows = {
        "added": [f"  + {n}  {new[n].signature}   B:{new[n].location}" for n in added],
        "changed": [
            f"  ~ {n}   {old[n].signature} → {new[n].signature}   "
            f"A:{old[n].location} → B:{new[n].location}"
            for n in changed
        ],
        "moved": [f"  = {n}  moved   A:{old[n].location} → B:{new[n].location}" for n in moved],
        "removed": [f"  - {n}  {old[n].signature}   A:{old[n].location}" for n in removed],
    }
    return {name: [f"{name}:", *rows[name]] if rows[name] else [] for name in SURFACE_DIFF_PARTS}


def format_surface_diff(
    a: Surface, b: Surface, label_a: str, label_b: str, showing: Sequence[str] = ()
) -> str:
    """The first line carries the name counts and the parts inventory; the
    body is every part, or with `showing` only those."""
    parts = diff_parts(a, b)
    names = {name: max(len(lines) - 1, 0) for name, lines in parts.items()}
    lines = [
        f"<{_count(names['added'], 'name')} added, {names['removed']} removed, "
        f"{names['changed']} changed, {names['moved']} moved; {parts_inventory(parts, showing)}> "
        f"surface diff {diff_direction(label_a, label_b)}: package {b.package}"
    ]
    if not any(parts.values()):
        lines.append(f"no surface differences between A={label_a} and B={label_b}")
    return "\n".join([*lines, *body(parts, showing)])


def surface_to_json(surface: Surface, label: str) -> dict:
    return {
        "coverage": {
            "public_names": len(surface.exports),
            "via": dict(Counter(e.via for e in surface.exports)),
            "in_all": sum(1 for e in surface.exports if e.listed),
            "ref": label.lstrip("@") or None,
        },
        "package": surface.package,
        "names": [
            {
                "name": e.name,
                "kind": e.kind,
                "via": e.via,
                "module": e.module,
                "path": e.path,
                "line": e.line,
                "signature": e.signature,
                "inherited": e.inherited,
            }
            for e in surface.exports
        ],
    }
