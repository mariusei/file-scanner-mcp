"""
EKSPERIMENT: Kryssfil-dedup av skjeletter på katalognivå

HYPOTESE:
  Kodebaser har strukturelt rim (SwiftUI-views, lifecycle-metoder,
  språkplugin-mønstre). Å vise et mønster én gang + referanser sparer
  tokens i en katalogvid skjelettvisning.

KRITISK SKILLE (falsifiserbart per nivå):
  Nivå A — EKSAKTE duplikater (identisk skjeleltekst): tapsfri dedup.
  Nivå B — FORM-duplikater (identifikatorer normalisert til x, tall til 0):
    tapsfull — medlemmenes interne kall-navn er forskjellige, og det er
    nettopp fakta-innholdet. Rapporteres som potensial med eksplisitt tap.

UTFALL HOLDES ÅPNE:
  - scantool (20 språkfiler) er kunstig gunstig; isowords (ekte iOS-app,
    388 Swift-filer) er testen som teller
  - Null-utfall: rim finnes på navnenivå (samme metodenavn) men ikke på
    skjelettnivå (ulik form) -> dedup gir < 5 %
  - Eksakt-nivået kan være tomt utenfor genererte filer

SPAREMODELL:
  dedup-kost = mønster vist én gang + ~3 tokens referanse per medlem
  besparelse = sum(medlems-skjeletter) - dedup-kost
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scantool.entropy.core import _candidate_nodes  # noqa: E402
from scantool.languages import get_language  # noqa: E402

IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
NUM_RE = re.compile(r"\b\d+(\.\d+)?\b")
REF_COST = 3  # ~tokens for en mønster-referanse på medlemmets header-linje


def shape_of(skeleton: list[str]) -> str:
    text = "\n".join(skeleton)
    text = IDENT_RE.sub("x", text)
    return NUM_RE.sub("0", text)


def collect(repo: Path, glob: str, ext: str, max_files: int = 500):
    lang = get_language(ext)
    nodes = []  # (fil, navn, skjelett-tekst, form)
    files = sorted(repo.rglob(glob))[:max_files]
    for path in files:
        try:
            data = path.read_bytes()
            structures = lang.scan(data)
        except Exception:
            continue
        if not structures:
            continue
        source_lines = data.decode("utf-8", errors="replace").split("\n")
        for node in _candidate_nodes(structures):
            excerpt = source_lines[node.start_line - 1:node.end_line]
            skeleton = lang.condense_excerpt(excerpt)
            if not skeleton or len(skeleton) < 2:
                continue
            text = "\n".join(skeleton)
            nodes.append((str(path.relative_to(repo)), node.name, text, shape_of(skeleton)))
    return len(files), nodes


def analyze(label: str, n_files: int, nodes, count):
    total_tokens = sum(count(t) for _, _, t, _ in nodes)
    print(f"\n{'=' * 78}\n{label}: {n_files} filer, {len(nodes)} noder med "
          f"skjelett ≥2 linjer, {total_tokens} skjelett-tokens\n{'=' * 78}")

    for level, key_idx in (("A eksakt (tapsfri)", 2), ("B form (tapsfull)", 3)):
        groups = defaultdict(list)
        for entry in nodes:
            groups[entry[key_idx]].append(entry)
        patterns = {k: v for k, v in groups.items() if len(v) >= 3}
        in_patterns = sum(len(v) for v in patterns.values())
        saved = sum(
            (len(v) - 1) * count(v[0][2]) - len(v) * REF_COST
            for v in patterns.values()
        )
        saved = max(0, saved)
        print(f"\n  Nivå {level}: {len(patterns)} mønstre (≥3 medlemmer), "
              f"{in_patterns}/{len(nodes)} noder dekket")
        print(f"    besparelse: {saved} tokens "
              f"({100 * saved / total_tokens if total_tokens else 0:.1f}% av skjelett-tokens)")
        top = sorted(patterns.values(), key=len, reverse=True)[:4]
        for members in top:
            sample = ", ".join(f"{f.split('/')[-1]}:{n}" for f, n, _, _ in members[:3])
            print(f"    {len(members):3d}× ({count(members[0][2])} tok): "
                  f"{sample}{', …' if len(members) > 3 else ''}")
            first_lines = members[0][2].split("\n")[:2]
            for line in first_lines:
                print(f"          | {line}")


def main():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        count = lambda t: len(enc.encode(t))
    except ImportError:
        count = lambda t: max(1, len(t) // 4)

    n, nodes = collect(PROJECT_ROOT / "src", "**/*.py", ".py")
    analyze("scantool/src (gunstig: 20 like språkfiler)", n, nodes, count)

    isowords = Path("/tmp/isowords")
    if isowords.exists():
        n, nodes = collect(isowords, "**/*.swift", ".swift")
        analyze("isowords (ekte iOS/SwiftUI-app)", n, nodes, count)
    else:
        print("\n(isowords ikke tilgjengelig — kjør git clone først)")


if __name__ == "__main__":
    main()
