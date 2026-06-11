"""
EXPERIMENT: Cross-file dedup of skeletons at directory level

HYPOTHESIS:
  Codebases have structural rhyme (SwiftUI views, lifecycle methods,
  language-plugin patterns). Showing a pattern once + references saves
  tokens in a directory-wide skeleton view.

CRITICAL DISTINCTION (falsifiable per level):
  Level A — EXACT duplicates (identical skeleton text): lossless dedup.
  Level B — SHAPE duplicates (identifiers normalized to x, numbers to 0):
    lossy — the members' internal call names differ, and that is
    precisely the factual content. Reported as potential with explicit loss.

OUTCOMES KEPT OPEN:
  - scantool (20 language files) is artificially favorable; isowords (real iOS app,
    388 Swift files) is the test that counts
  - Null outcome: rhyme exists at the name level (same method names) but not at the
    skeleton level (different shape) -> dedup yields < 5 %
  - The exact level may be empty outside generated files

SAVINGS MODEL:
  dedup cost = pattern shown once + ~3 tokens of reference per member
  savings = sum(member skeletons) - dedup cost
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
REF_COST = 3  # ~tokens for a pattern reference on the member's header line


def shape_of(skeleton: list[str]) -> str:
    text = "\n".join(skeleton)
    text = IDENT_RE.sub("x", text)
    return NUM_RE.sub("0", text)


def collect(repo: Path, glob: str, ext: str, max_files: int = 500):
    lang = get_language(ext)
    nodes = []  # (file, name, skeleton text, shape)
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
    print(f"\n{'=' * 78}\n{label}: {n_files} files, {len(nodes)} nodes with "
          f"skeleton ≥2 lines, {total_tokens} skeleton tokens\n{'=' * 78}")

    for level, key_idx in (("A exact (lossless)", 2), ("B shape (lossy)", 3)):
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
        print(f"\n  Level {level}: {len(patterns)} patterns (≥3 members), "
              f"{in_patterns}/{len(nodes)} nodes covered")
        print(f"    savings: {saved} tokens "
              f"({100 * saved / total_tokens if total_tokens else 0:.1f}% of skeleton tokens)")
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
    analyze("scantool/src (favorable: 20 similar language files)", n, nodes, count)

    isowords = Path("/tmp/isowords")
    if isowords.exists():
        n, nodes = collect(isowords, "**/*.swift", ".swift")
        analyze("isowords (real iOS/SwiftUI app)", n, nodes, count)
    else:
        print("\n(isowords not available — run git clone first)")


if __name__ == "__main__":
    main()
