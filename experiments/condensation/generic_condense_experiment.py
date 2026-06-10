"""
EKSPERIMENT: Generisk tree-sitter-basert kondensering for alle språk

PROBLEM:
  condense_excerpt() er Python-only (stdlib ast). Entropi-evaluatoren er
  språkagnostisk; kondenseringen bør dekke det samme.

IDÉ:
  Linjemarkering via tree-sitter: behold linjer der "signifikante" noder
  starter (kontrollflyt, kall, tilordninger, definisjoner — matchet på
  node-typenavn på tvers av grammatikker). Blanke/punktum-linjer droppes
  stille, øvrige foldes til "…".

UTFALL HOLDES ÅPNE:
  1. Virker bredt (ratio < 0.8, struktur bevart)
  2. Fragment-parsing feiler for noen språk (alt ERROR → ingen signifikante
     noder → None → verbatim-fallback; målbart som "None-rate")
  3. Markup/deklarative språk: ingenting å folde → ratio ≈ 1.0 → None er
     korrekt utfall, ikke feil
  4. Node-typenavn for ulikt → mønsteret bommer per språk (sjekk manuelt)

MÅLING:
  Per språk: antall noder testet, None-rate, gjennomsnittlig token-ratio
  for noder som kondenseres, og eksempel-output for manuell inspeksjon.
"""

import re
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scantool.languages import get_registry  # noqa: E402

# Node-typer som bærer intent/metode — matchet mot tree-sitter-typenavn.
# Ordene er valgt fra konvensjoner på tvers av grammatikker
# (if_statement, call_expression, method_invocation, let_declaration, ...)
SIGNIFICANT = re.compile(
    r"\b(if|else|elif|for|foreach|while|do|switch|case|match|when|guard|loop"
    r"|try|catch|except|finally|return|break|continue|throw|raise|yield|defer"
    r"|call|invocation|invoke|new|await|macro"
    r"|assignment|augmented"
    r"|function|method|class|struct|enum|interface|impl|trait|lambda|closure"
    r"|let|const|short_var|local"
    r"|select|insert|update|delete|create|drop|alter)\b",
    re.IGNORECASE,
)

# Linjer med kun lukkende syntaks/punktum — droppes stille (struktur vises
# via innrykk, som i Python)
PUNCT_ONLY = re.compile(r"^[\s)\]}>;,]*$")

# Felt-navn som peker på "kroppen" til en node — linjene fra nodens start
# til kroppens start er header (flerlinje-betingelser etc.) og beholdes
BODY_FIELDS = ("body", "consequence", "block")


def significant_rows(tree, max_row: int) -> set[int]:
    rows: set[int] = set()
    cursor = [tree.root_node]
    while cursor:
        node = cursor.pop()
        if SIGNIFICANT.search(node.type.replace("_", " ")):
            start = node.start_point[0]
            end = node.start_point[0]
            for field in BODY_FIELDS:
                body = node.child_by_field_name(field)
                if body is not None:
                    end = max(start, body.start_point[0] - 1) if body.start_point[0] > start else start
                    break
            rows.update(range(start, min(end, max_row) + 1))
        cursor.extend(node.children)
    return rows


def condense_generic(language, excerpt_lines: list[str]) -> list[str] | None:
    parser = getattr(language, "parser", None)
    if parser is None:
        return None

    source = textwrap.dedent("\n".join(excerpt_lines))
    lines = source.split("\n")
    tree = parser.parse(source.encode("utf-8", errors="replace"))
    rows = significant_rows(tree, len(lines) - 1)
    if not rows:
        return None  # fragmentet ga ingen gjenkjennbar struktur

    out: list[str] = []
    folded_something = False
    for i, line in enumerate(lines):
        if PUNCT_ONLY.match(line):
            folded_something = folded_something or bool(line.strip())
            continue
        if i in rows:
            out.append(line.rstrip())
        else:
            folded_something = True
            if not out or out[-1].strip() != "…":
                indent = len(line) - len(line.lstrip())
                out.append(" " * indent + "…")

    if not folded_something:
        return None  # ingenting spart — verbatim med linjenumre er bedre
    return out


def collect_nodes(structures, kinds=("function", "method", "class", "rule",
                                     "statement", "table", "query", "element",
                                     "selector", "mixin")):
    found = []
    for node in structures or []:
        if any(k in node.type for k in kinds) and node.end_line > node.start_line:
            found.append(node)
        if node.children:
            found.extend(collect_nodes(node.children, kinds))
    return found


def main():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        count = lambda t: len(enc.encode(t))
        token_note = "tiktoken cl100k_base"
    except ImportError:
        count = lambda t: max(1, len(t) // 4)
        token_note = "fallback len//4"

    samples = sorted(
        p for pattern in ("basic", "edge_cases", "postgresql", "django_template",
                          "svelte_template", "Broken", "demo")
        for p in (PROJECT_ROOT / "tests").rglob(f"{pattern}.*")
        if p.suffix not in (".py",) or "samples" in str(p)
    )

    registry = get_registry()
    print("=" * 78)
    print(f"OBSERVASJONER (tokenizer: {token_note})")
    print("=" * 78)

    per_lang: dict[str, list] = {}
    examples = {}

    for sample in samples:
        lang_cls = registry.get_scanner(sample.suffix.lower())
        if lang_cls is None:
            continue
        language = lang_cls()
        source_lines = sample.read_text(errors="replace").split("\n")
        structures = language.scan(sample.read_bytes())
        for node in collect_nodes(structures):
            excerpt = source_lines[node.start_line - 1:node.end_line]
            if len(excerpt) < 3:
                continue
            skeleton = language.condense_excerpt(excerpt)
            name = language.get_language_name()
            stats = per_lang.setdefault(name, [])
            if skeleton is None:
                stats.append(None)
            else:
                tv = count("\n".join(excerpt))
                ts = count("\n".join(skeleton))
                stats.append(ts / tv if tv else 1.0)
                key = name
                if key not in examples and len(excerpt) >= 8:
                    examples[key] = (sample.name, node.name, excerpt, skeleton)

    print(f"\n{'Språk':14s} {'noder':>6s} {'None-rate':>10s} {'snitt-ratio':>12s}")
    for name in sorted(per_lang):
        stats = per_lang[name]
        ratios = [s for s in stats if s is not None]
        none_rate = (len(stats) - len(ratios)) / len(stats)
        avg = sum(ratios) / len(ratios) if ratios else float("nan")
        print(f"{name:14s} {len(stats):6d} {none_rate:9.0%} "
              f"{avg if ratios else 0:12.2f}{'  (ingen kondensert)' if not ratios else ''}")

    print("\n" + "=" * 78)
    print("EKSEMPLER (manuell inspeksjon av struktur-bevaring)")
    print("=" * 78)
    for name, (fname, node_name, excerpt, skeleton) in sorted(examples.items()):
        print(f"\n--- {name}: {fname} :: {node_name} ---")
        print("FØR (verbatim):")
        for line in excerpt[:14]:
            print(f"  |{line}")
        if len(excerpt) > 14:
            print(f"  |... +{len(excerpt) - 14} linjer")
        print("ETTER (generisk skjelett):")
        for line in skeleton:
            print(f"  ⟨{line}⟩")


if __name__ == "__main__":
    main()
