"""
EXPERIMENT: Abstractive condensation of salient code

PROBLEM:
  Today's entropy pipeline is extractive: it selects which lines are shown,
  but reprints them verbatim (formatter.py code_excerpt). Question: can an
  abstractive skeleton representation (control flow + calls + arithmetic +
  return/raise, trivial statements folded) convey intent/method with
  fewer tokens?

HYPOTHESIS (falsifiable):
  A skeleton representation of salient functions uses fewer tokens than
  verbatim excerpts, measured with tiktoken cl100k_base as a proxy.
  Falsified if: token ratio (skeleton/verbatim) >= 1.0, or if
  retention of call names < 80% (then the method is no longer visible).

OUTCOMES KEPT OPEN:
  expected / null result / paradox (shorter functions -> overhead) /
  trade-off (tokens saved but constants lost) / metric misplacement.

DESIGN:
  A  = full source code (reference)
  B  = official scan_file output (structure + verbatim excerpts)
  B' = minimal renderer + verbatim excerpts   <- control
  C  = minimal renderer + skeleton            <- experiment
  B' vs C isolates the variable (excerpt representation); B/A gives context.

  Retention metrics (proxy for information loss, not "understanding"):
  - call names: share of called function names from verbatim present in skeleton
  - numeric constants: share of numeric literals retained
"""

import ast
import copy
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scantool.scanner import FileScanner  # noqa: E402
from scantool.formatter import TreeFormatter  # noqa: E402

MAX_EXPR_LEN = 60  # truncation of unparsed expressions
SMART_TRUNC = "--smart-trunc" in sys.argv  # v2: elide args instead of tail-cutting


class _ShortenLiterals(ast.NodeTransformer):
    """Shortens lambda bodies and long string literals — preserves call names."""

    def visit_Lambda(self, node):
        return ast.Name(id="λ")

    def visit_Constant(self, node):
        if isinstance(node.value, str) and len(node.value) > 16:
            return ast.Constant(value=node.value[:13] + "…")
        return node


class _ElideNestedArgs(ast.NodeTransformer):
    """Replaces arguments in nested calls with … — the call name survives."""

    def __init__(self):
        self.depth = 0

    def visit_Call(self, node):
        node.func = self.visit(node.func)
        self.depth += 1
        if self.depth > 1:
            node.args = [ast.Name(id="…")] if (node.args or node.keywords) else []
            node.keywords = []
        else:
            node.args = [self.visit(a) for a in node.args]
            node.keywords = [self.visit(k) for k in node.keywords]
        self.depth -= 1
        return node


# ═══════════════════════════════════════════════════════════
# SKELETON GENERATION (deterministic, AST-based)
# ═══════════════════════════════════════════════════════════

def _trunc(expr: ast.AST) -> str:
    try:
        text = " ".join(ast.unparse(expr).split())
        if len(text) <= MAX_EXPR_LEN:
            return text
        if SMART_TRUNC:
            # gradual elision that preserves call names and constants
            short = _ShortenLiterals().visit(copy.deepcopy(expr))
            text = " ".join(ast.unparse(short).split())
            if len(text) <= MAX_EXPR_LEN:
                return text
            short = _ElideNestedArgs().visit(short)
            text = " ".join(ast.unparse(short).split())
            if len(text) <= MAX_EXPR_LEN * 2:  # more generous limit after elision
                return text
        return text[: MAX_EXPR_LEN - 1] + "…"
    except Exception:
        return "…"


def _has_substance(value: ast.AST) -> bool:
    """A statement is kept if the RHS carries method information: calls, arithmetic,
    comparison, conditional expression or comprehension."""
    for sub in ast.walk(value):
        if isinstance(sub, (ast.Call, ast.BinOp, ast.BoolOp, ast.Compare,
                            ast.IfExp, ast.ListComp, ast.SetComp,
                            ast.DictComp, ast.GeneratorExp)):
            return True
    return False


def _skeleton_stmts(stmts: list[ast.stmt], depth: int) -> list[str]:
    out: list[str] = []
    ind = " " * depth

    def emit(text: str) -> None:
        out.append(f"{ind}{text}")

    def fold() -> None:
        if not out or out[-1] != f"{ind}…":
            emit("…")

    for stmt in stmts:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            emit(f"def {stmt.name}(…):")
            out.extend(_skeleton_stmts(stmt.body, depth + 1))
        elif isinstance(stmt, ast.ClassDef):
            emit(f"class {stmt.name}:")
            out.extend(_skeleton_stmts(stmt.body, depth + 1))
        elif isinstance(stmt, ast.If):
            emit(f"if {_trunc(stmt.test)}:")
            out.extend(_skeleton_stmts(stmt.body, depth + 1))
            orelse = stmt.orelse
            while len(orelse) == 1 and isinstance(orelse[0], ast.If):
                emit(f"elif {_trunc(orelse[0].test)}:")
                out.extend(_skeleton_stmts(orelse[0].body, depth + 1))
                orelse = orelse[0].orelse
            if orelse:
                emit("else:")
                out.extend(_skeleton_stmts(orelse, depth + 1))
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            emit(f"for {_trunc(stmt.target)} in {_trunc(stmt.iter)}:")
            out.extend(_skeleton_stmts(stmt.body, depth + 1))
        elif isinstance(stmt, ast.While):
            emit(f"while {_trunc(stmt.test)}:")
            out.extend(_skeleton_stmts(stmt.body, depth + 1))
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            items = ", ".join(_trunc(i) for i in stmt.items)
            emit(f"with {items}:")
            out.extend(_skeleton_stmts(stmt.body, depth + 1))
        elif isinstance(stmt, ast.Try):
            emit("try:")
            out.extend(_skeleton_stmts(stmt.body, depth + 1))
            for handler in stmt.handlers:
                exc = f" {_trunc(handler.type)}" if handler.type else ""
                emit(f"except{exc}:")
                out.extend(_skeleton_stmts(handler.body, depth + 1))
            if stmt.finalbody:
                emit("finally:")
                out.extend(_skeleton_stmts(stmt.finalbody, depth + 1))
        elif isinstance(stmt, ast.Return):
            emit(f"return {_trunc(stmt.value)}" if stmt.value else "return")
        elif isinstance(stmt, ast.Raise):
            emit(f"raise {_trunc(stmt.exc)}" if stmt.exc else "raise")
        elif isinstance(stmt, ast.Assert):
            emit(f"assert {_trunc(stmt.test)}")
        elif isinstance(stmt, (ast.Break, ast.Continue)):
            emit("break" if isinstance(stmt, ast.Break) else "continue")
        elif isinstance(stmt, ast.Assign):
            if _has_substance(stmt.value):
                targets = ", ".join(_trunc(t) for t in stmt.targets)
                emit(f"{targets} = {_trunc(stmt.value)}")
            else:
                fold()
        elif isinstance(stmt, ast.AugAssign):
            emit(f"{_trunc(stmt.target)} {type(stmt.op).__name__.lower()}= "
                 f"{_trunc(stmt.value)}")
        elif isinstance(stmt, ast.AnnAssign):
            if stmt.value is not None and _has_substance(stmt.value):
                emit(f"{_trunc(stmt.target)} = {_trunc(stmt.value)}")
            else:
                fold()
        elif isinstance(stmt, ast.Expr):
            if isinstance(stmt.value, ast.Call):
                emit(_trunc(stmt.value))
            else:
                fold()  # docstring expressions, constants
        else:
            fold()  # import, pass, global, delete, ...

    return out


def build_skeleton_index(source: str) -> dict[tuple[str, int], list[str]]:
    """Map (function name, def line) -> skeleton lines for the whole file."""
    tree = ast.parse(source)
    index = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            # skip the docstring statement (already shown in the structure tree)
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    body[0].value, ast.Constant):
                body = body[1:]
            index[(node.name, node.lineno)] = _skeleton_stmts(body, 1)
    return index


# ═══════════════════════════════════════════════════════════
# RENDERERS: B' (verbatim) and C (skeleton) over the same structure
# ═══════════════════════════════════════════════════════════

def render_minimal(structures, skeleton_index=None, indent=0) -> list[str]:
    """Shared minimal renderer. skeleton_index=None -> verbatim excerpts (B'),
    otherwise excerpts are swapped for skeletons (C). Everything else identical."""
    lines = []
    ind = " " * indent
    for node in structures:
        header = f"{ind}{node.type}: {node.name or ''} @{node.start_line}"
        if getattr(node, "signature", None):
            header += f" {node.signature}"
        if getattr(node, "docstring", None):
            header += f"  # {node.docstring}"
        lines.append(header)

        excerpt = getattr(node, "code_excerpt", None)
        if excerpt:
            if skeleton_index is None:
                for i, line in enumerate(excerpt, start=node.start_line):
                    lines.append(f"{ind} {i} | {line}")
            else:
                skel = _lookup_skeleton(skeleton_index, node)
                if skel is not None:
                    lines.extend(f"{ind} ⟨{line}⟩" for line in skel)
                else:
                    for i, line in enumerate(excerpt, start=node.start_line):
                        lines.append(f"{ind} {i} | {line}")

        if node.children:
            lines.extend(render_minimal(node.children, skeleton_index,
                                        indent + 1))
    return lines


def _lookup_skeleton(index, node):
    for (name, lineno), skel in index.items():
        if name == node.name and abs(lineno - node.start_line) <= 5:
            return skel
    return None


# ═══════════════════════════════════════════════════════════
# MEASUREMENT
# ═══════════════════════════════════════════════════════════

def count_tokens(text: str, encoder) -> int:
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, len(text) // 4)  # rough fallback proxy


CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
NUM_RE = re.compile(r"\b\d+\.?\d*\b")
PY_KEYWORDS = {"if", "elif", "while", "for", "return", "with", "assert",
               "raise", "print", "def", "class", "except", "in", "not"}


def extract_calls(text: str) -> set[str]:
    return {m for m in CALL_RE.findall(text) if m not in PY_KEYWORDS}


def retention(verbatim: str, skeleton: str, pattern_fn) -> tuple[int, int]:
    ref = pattern_fn(verbatim)
    if not ref:
        return (0, 0)
    kept = ref & pattern_fn(skeleton)
    return (len(kept), len(ref))


def collect_excerpt_nodes(structures):
    found = []
    for node in structures:
        if getattr(node, "code_excerpt", None):
            found.append(node)
        if node.children:
            found.extend(collect_excerpt_nodes(node.children))
    return found


def main():
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        token_note = "tiktoken cl100k_base"
    except ImportError:
        encoder = None
        token_note = "fallback: len(text)//4 (rough proxy)"

    test_files = [
        "src/scantool/scanner.py",
        "src/scantool/preview.py",
        "src/scantool/code_map.py",
        "src/scantool/entropy/core.py",
        "src/scantool/languages/python.py",
    ]

    scanner = FileScanner()
    formatter = TreeFormatter()

    print("=" * 78)
    print("OBSERVATIONS")
    print(f"(tokenizer: {token_note}; semantics: fewer tokens = cheaper "
          f"context, the direction of 'better' depends on information loss)")
    print("=" * 78)

    totals = {"A": 0, "B": 0, "Bp": 0, "C": 0}
    call_kept = call_ref = num_kept = num_ref = 0
    per_node_rows = []

    for rel in test_files:
        path = PROJECT_ROOT / rel
        source = path.read_text()
        structures = scanner.scan_file(str(path))
        if structures is None:
            print(f"\n{rel}: scan_file returned None — skipped")
            continue

        skeleton_index = build_skeleton_index(source)

        a_text = source
        b_text = formatter.format(str(path), structures)
        bp_text = "\n".join(render_minimal(structures))
        c_text = "\n".join(render_minimal(structures, skeleton_index))

        ta = count_tokens(a_text, encoder)
        tb = count_tokens(b_text, encoder)
        tbp = count_tokens(bp_text, encoder)
        tc = count_tokens(c_text, encoder)
        totals["A"] += ta
        totals["B"] += tb
        totals["Bp"] += tbp
        totals["C"] += tc

        # per-node comparison of the excerpt representations
        nodes = collect_excerpt_nodes(structures)
        n_with_skel = 0
        for node in nodes:
            verbatim = "\n".join(node.code_excerpt)
            skel = _lookup_skeleton(skeleton_index, node)
            if skel is None:
                continue
            n_with_skel += 1
            skel_text = "\n".join(skel)
            tv = count_tokens(verbatim, encoder)
            ts = count_tokens(skel_text, encoder)
            ck, cr = retention(verbatim, skel_text, extract_calls)
            nk, nr = retention(verbatim, skel_text,
                               lambda t: set(NUM_RE.findall(t)))
            call_kept += ck
            call_ref += cr
            num_kept += nk
            num_ref += nr
            per_node_rows.append((rel, node.name, tv, ts))

        print(f"\n{rel}")
        print(f"  A  full source:           {ta:6d} tokens")
        print(f"  B  official scan_file:    {tb:6d} tokens")
        print(f"  B' minimal + verbatim:    {tbp:6d} tokens")
        print(f"  C  minimal + skeleton:    {tc:6d} tokens")
        print(f"  excerpt nodes: {len(nodes)}, with skeleton match: "
              f"{n_with_skel}")

    print("\n" + "=" * 78)
    print("PER NODE: verbatim vs skeleton (excerpt parts only)")
    print("=" * 78)
    tv_sum = sum(r[2] for r in per_node_rows)
    ts_sum = sum(r[3] for r in per_node_rows)
    for rel, name, tv, ts in per_node_rows:
        print(f"  {name:38s} verbatim {tv:5d}  skeleton {ts:5d}  "
              f"ratio {ts / tv if tv else 0:.2f}")
    print(f"\n  SUM verbatim: {tv_sum}, SUM skeleton: {ts_sum}, "
          f"ratio: {ts_sum / tv_sum if tv_sum else 0:.3f}")

    print("\n" + "=" * 78)
    print("RETENTION (proxy metrics, not 'understanding')")
    print("=" * 78)
    print(f"  call names retained:        {call_kept}/{call_ref} "
          f"({100 * call_kept / call_ref if call_ref else 0:.1f}%)")
    print(f"  numeric constants retained: {num_kept}/{num_ref} "
          f"({100 * num_kept / num_ref if num_ref else 0:.1f}%)")

    print("\n" + "=" * 78)
    print("TOTALS (all test files)")
    print("=" * 78)
    for key, label in [("A", "full source"), ("B", "official scan_file"),
                       ("Bp", "minimal + verbatim"),
                       ("C", "minimal + skeleton")]:
        print(f"  {label:24s} {totals[key]:7d} tokens "
              f"({100 * totals[key] / totals['A'] if totals['A'] else 0:.1f}% "
              f"of full source)")

    print("\n" + "=" * 78)
    print("EXAMPLE OUTPUT (first node with both verbatim and skeleton)")
    print("=" * 78)
    # show one concrete example so the representation can be inspected
    shown = False
    for rel in test_files:
        if shown:
            break
        path = PROJECT_ROOT / rel
        source = path.read_text()
        structures = scanner.scan_file(str(path))
        if structures is None:
            continue
        skeleton_index = build_skeleton_index(source)
        for node in collect_excerpt_nodes(structures):
            skel = _lookup_skeleton(skeleton_index, node)
            if skel is None or len(node.code_excerpt) < 8:
                continue
            print(f"\n--- {rel} :: {node.name} ---")
            print("VERBATIM:")
            for i, line in enumerate(node.code_excerpt,
                                     start=node.start_line):
                print(f"  {i} | {line}")
            print("SKELETON:")
            for line in skel:
                print(f"  ⟨{line}⟩")
            shown = True
            break

    print("\nFORK: interpretation is done AFTER observation — see the analysis outside "
          "the script.")


if __name__ == "__main__":
    main()
