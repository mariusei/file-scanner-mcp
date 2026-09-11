"""
FILE: surface.py

PROBLEM:
  "What does this package export, and where is each name really defined?"
  A facade answers with __all__, a lazy-import table (PEP 562), imports
  under TYPE_CHECKING and re-export chains; the definition sits files away.
  In the field study three agents independently called this the most
  useful single call, and each rebuilt it with ast over git show.

SOLUTION:
  Parse the package with ast, list the public names in the order the
  facade gives them, follow each name through lazy tables and re-exports to
  the module that defines it, and say how it got exported. Classes carry
  their public methods and the members they inherit from bases inside the
  package, marked as inherited. A surface at another ref diffs against
  this one, direction stated.

SCOPE:
  ✓ Python packages; __all__, lazy tables, TYPE_CHECKING, re-export chains,
    inheritance inside the package, signatures via ast
  ✗ other languages; runtime __getattr__ that is not a literal table
"""

import ast
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

MAX_METHODS = 8
MAX_CHAIN = 40


@dataclass
class Export:
    name: str
    kind: str  # function | class | value | module | external | unresolved
    via: str  # how the facade gets it: definition | re-export | lazy table | TYPE_CHECKING
    module: str | None  # dotted module that defines it, inside the package
    path: str | None  # relative to the directory holding the package
    line: int | None
    signature: str
    inherited: list[str] = field(default_factory=list)  # "Base: m1, m2"
    listed: bool = False  # named in __all__

    @property
    def location(self) -> str:
        return f"{self.path}:{self.line}" if self.path else "-"


@dataclass
class Surface:
    package: str
    exports: list[Export]


# ── ast helpers ──────────────────────────────────────────────────────────────


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args

    def render(arg: ast.arg, default: ast.expr | None = None) -> str:
        text = arg.arg
        if arg.annotation is not None:
            text += ": " + ast.unparse(arg.annotation)
        if default is not None:
            text += (" = " if arg.annotation is not None else "=") + ast.unparse(default)
        return text

    positional = [*args.posonlyargs, *args.args]
    offset = len(positional) - len(args.defaults)
    parts = []
    for index, arg in enumerate(positional):
        parts.append(render(arg, args.defaults[index - offset] if index >= offset else None))
        if args.posonlyargs and index == len(args.posonlyargs) - 1:
            parts.append("/")
    if args.vararg is not None:
        parts.append("*" + render(args.vararg))
    elif args.kwonlyargs:
        parts.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        parts.append(render(arg, default))
    if args.kwarg is not None:
        parts.append("**" + render(args.kwarg))
    text = "(" + ", ".join(parts) + ")"
    if node.returns is not None:
        text += " -> " + ast.unparse(node.returns)
    return ("async " if isinstance(node, ast.AsyncFunctionDef) else "") + text


def _definitions(tree: ast.Module) -> dict[str, tuple[str, ast.AST]]:
    """name -> (kind, node) for what the module body defines."""
    index: dict[str, tuple[str, ast.AST]] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            index[node.name] = ("function", node)
        elif isinstance(node, ast.ClassDef):
            index[node.name] = ("class", node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    index[target.id] = ("value", node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            index[node.target.id] = ("value", node)
    return index


def _imports(tree: ast.Module) -> dict[str, tuple[str | None, int, str | None, bool]]:
    """local name -> (module, level, imported name or None for a module, under TYPE_CHECKING)."""
    out: dict[str, tuple[str | None, int, str | None, bool]] = {}

    def walk(body, guarded: bool):
        for node in body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        out.setdefault(
                            alias.asname or alias.name,
                            (node.module, node.level, alias.name, guarded),
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    out.setdefault(local, (alias.name, 0, None, guarded))
            elif isinstance(node, ast.If):
                test = ast.unparse(node.test)
                walk(node.body, guarded or "TYPE_CHECKING" in test)
                walk(node.orelse, guarded)

    walk(tree.body, False)
    return out


def _lazy_table(tree: ast.Module) -> dict[str, tuple[str, str | None]]:
    """A module-level dict of name -> "module[:attr]" (the PEP 562 facade shape)."""
    out: dict[str, tuple[str, str | None]] = {}
    for node in tree.body:
        value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
        if not isinstance(value, ast.Dict):
            continue
        try:
            literal = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            continue
        if not literal or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in literal.items()
        ):
            continue
        for name, target in literal.items():
            if name.startswith("_"):
                continue
            module, sep, attr = target.partition(":")
            if all(part.isidentifier() for part in module.split(".")) and (
                not sep or attr.isidentifier()
            ):
                out.setdefault(name, (module, attr if sep else None))
    return out


def _dunder_all(tree: ast.Module) -> list[str] | None:
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        if "__all__" in targets and isinstance(node, ast.Assign | ast.AnnAssign) and node.value:
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
            if isinstance(value, list | tuple):
                return [str(v) for v in value]
    return None


def _public_methods(cls: ast.ClassDef) -> list[str]:
    return [
        node.name
        for node in cls.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and (not node.name.startswith("_") or node.name == "__init__")
    ]


# ── resolving names through the package ──────────────────────────────────────


class _Resolver:
    def __init__(self, root: str, package: str):
        self.root = root  # directory holding the package directory
        self.package = package
        self.trees: dict[str, ast.Module | None] = {}

    def module_path(self, dotted: str) -> str | None:
        base = os.path.join(self.root, *dotted.split("."))
        for candidate in (base + ".py", os.path.join(base, "__init__.py")):
            if os.path.isfile(candidate):
                return candidate
        return None

    def tree(self, path: str) -> ast.Module | None:
        if path not in self.trees:
            try:
                self.trees[path] = ast.parse(Path(path).read_bytes())
            except (OSError, SyntaxError, ValueError):
                self.trees[path] = None
        return self.trees[path]

    def absolute(self, module: str | None, level: int, current: str) -> str:
        """The dotted module an import refers to, from the module that imports."""
        if level == 0:
            return module or ""
        parts = current.split(".")
        path = self.module_path(current) or ""
        if not path.endswith("__init__.py"):
            parts = parts[:-1]  # a module imports relative to its package
        base = parts[: len(parts) - (level - 1)]
        return ".".join([*base, module]) if module else ".".join(base)

    def rel(self, path: str) -> str:
        return os.path.relpath(path, self.root).replace(os.sep, "/")

    def resolve(self, name: str, dotted: str, via: str, seen: set | None = None) -> Export:
        seen = set() if seen is None else seen
        if (name, dotted) in seen or len(seen) > MAX_CHAIN:
            return Export(name, "unresolved", via, dotted, None, None, "re-export cycle")
        seen.add((name, dotted))
        path = self.module_path(dotted)
        tree = self.tree(path) if path else None
        if path is None or tree is None:
            reason = "outside the package" if path is None else "does not parse"
            return Export(name, "external", via, dotted, None, None, f"from {dotted} ({reason})")

        definitions = _definitions(tree)
        if name in definitions:
            kind, node = definitions[name]
            return self._defined(name, kind, node, dotted, path, via)
        lazy = _lazy_table(tree)
        if name in lazy:
            module, attr = lazy[name]
            if attr is None:
                return self.as_module(name, module, "lazy table")
            return self.resolve(attr, module, "lazy table", seen)
        imports = _imports(tree)
        if name in imports:
            imported_from, level, imported, guarded = imports[name]
            target = self.absolute(imported_from, level, dotted)
            how = "TYPE_CHECKING" if guarded else via if via != "definition" else "re-export"
            if imported is None:
                return self.as_module(name, target, how)
            if self.module_path(f"{target}.{imported}"):  # `from . import submodule`
                return self.as_module(name, f"{target}.{imported}", how)
            return self.resolve(imported, target, how, seen)
        return Export(name, "unresolved", via, dotted, self.rel(path), None, "not found in module")

    def as_module(self, name: str, dotted: str, via: str) -> Export:
        path = self.module_path(dotted)
        tree = self.tree(path) if path else None
        if path is None or tree is None:
            return Export(name, "external", via, dotted, None, None, f"module {dotted}")
        names = _dunder_all(tree)
        if names is None:
            names = [n for n in [*_definitions(tree), *_lazy_table(tree)] if not n.startswith("_")]
        return Export(
            name, "module", via, dotted, self.rel(path), 1, f"module ({len(names)} names)"
        )

    def _defined(
        self, name: str, kind: str, node: ast.AST, dotted: str, path: str, via: str
    ) -> Export:
        export = Export(name, kind, via, dotted, self.rel(path), getattr(node, "lineno", None), "")
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            export.signature = _signature(node)
        elif isinstance(node, ast.ClassDef):
            methods = [m for m in _public_methods(node) if m != "__init__"]
            shown = methods[:MAX_METHODS]
            inner = ", ".join(shown) or "none"
            if len(methods) > len(shown):
                inner += f", +{len(methods) - len(shown)} more"
            bases = ", ".join(ast.unparse(base) for base in node.bases)
            export.signature = (
                f"class({bases}) methods: {inner}" if bases else f"class methods: {inner}"
            )
            export.inherited = self._inherited(node, dotted, set(methods))
        elif isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            export.signature = "= " + ast.unparse(node.value)[:80]
        return export

    def _inherited(
        self, cls: ast.ClassDef, dotted: str, own: set[str], depth: int = 0
    ) -> list[str]:
        """Public methods the class gets from bases defined inside the package."""
        if depth > 5:
            return []
        out = []
        for base in cls.bases:
            base_name = ast.unparse(base).split(".")[-1]
            resolved = self.resolve(base_name, dotted, "definition")
            if resolved.kind != "class" or resolved.path is None:
                continue
            tree = self.tree(os.path.join(self.root, *resolved.path.split("/")))
            node = (
                _definitions(tree)[base_name][1]
                if tree and base_name in _definitions(tree)
                else None
            )
            if not isinstance(node, ast.ClassDef):
                continue
            gained = [m for m in _public_methods(node) if m != "__init__" and m not in own]
            if gained:
                out.append(f"{base_name}: {', '.join(gained)}")
                own |= set(gained)
            out.extend(self._inherited(node, resolved.module or dotted, own, depth + 1))
        return out


def read_surface(package_dir: str) -> Surface:
    """The public surface of the package whose directory is given."""
    package_dir = os.path.abspath(package_dir.rstrip("/\\"))
    package = os.path.basename(package_dir)
    root = os.path.dirname(package_dir)
    resolver = _Resolver(root, package)
    init = os.path.join(package_dir, "__init__.py")
    tree = resolver.tree(init)
    if tree is None:
        return Surface(package, [])
    listed = _dunder_all(tree)
    names = (
        listed
        if listed is not None
        else [n for n in [*_definitions(tree), *_lazy_table(tree)] if not n.startswith("_")]
    )
    exports = [resolver.resolve(name, package, "definition") for name in names]
    for export in exports:
        export.listed = listed is not None
    return Surface(package, exports)


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


def format_surface_diff(a: Surface, b: Surface, label_a: str, label_b: str) -> str:
    """Names added, removed, changed (signature) or moved between A and B."""
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
    lines = [
        f"<{_count(len(added), 'name')} added, {len(removed)} removed, {len(changed)} changed, "
        f"{len(moved)} moved> surface diff {label_a} → {label_b}: package {b.package}"
    ]
    if not (added or removed or changed or moved):
        lines.append(f"no surface differences between {label_a} and {label_b}")
        return "\n".join(lines)
    for name in added:
        lines.append(f"  + {name}  {new[name].signature}   B:{new[name].location}")
    for name in changed:
        lines.append(
            f"  ~ {name}   {old[name].signature} → {new[name].signature}   "
            f"A:{old[name].location} → B:{new[name].location}"
        )
    for name in moved:
        lines.append(f"  = {name}  moved   A:{old[name].location} → B:{new[name].location}")
    for name in removed:
        lines.append(f"  - {name}  {old[name].signature}   A:{old[name].location}")
    return "\n".join(lines)


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
