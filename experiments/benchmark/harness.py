"""
M2-BENCHMARK: Informasjonsleverings-effektivitet, scantool vs grep-baseline

HVA SOM MÅLES (og ikke):
  Tokens og verktøykall til ALLE fasit-fakta for en oppgave er synlige i
  akkumulert verktøyoutput, under kanoniske strategier definert under.
  Dette er nødvendig-men-ikke-tilstrekkelig for "agenten løser oppgaven
  bedre" — ekte agent-episoder er M2b. Deterministisk og reproduserbart.

FALSIFISERBARHET:
  - Fakta er "det agenten må vite for å handle": omsluttende funksjoner,
    filer, kollaboratører — ikke bare treff-linjer
  - Baseline er GENERØS: smart grep med kontekstvinduer rundt treff-
    klynger, ikke naiv cat av hele filer
  - T4 er designet for at grep skal kunne vinne (literal oppslag) —
    vinner scantool alt, er harnessen mistenkelig

KANONISKE STRATEGIER:
  scantool konsept:  search_structures(content_pattern) → scan_file(topp-
                     treff-fil, budget=2000) → scan_directory(dir)
  scantool struktur: search_structures(name_pattern) → scan_file(...)
  scantool oversikt: preview_directory(deep) → scan_directory(dir)
  grep konsept:      grep -rn → ±40-linjers vinduer rundt treffklynger i
                     fil med flest treff → neste fil → full cat av toppfil
  grep oversikt:     find *.py → cat README → cat main.py
"""

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

REPO = "/Users/mariusbergeeide/Projects/internal-backend"
DIR = f"{REPO}/backend/app"


@dataclass
class Task:
    name: str
    kind: str                 # "concept" | "structure" | "overview"
    query: str                # søkebegrep for begge verktøysett
    facts: list[str]          # distinkte substrings som MÅ være synlige
    description: str = ""
    directory: str = DIR


TASKS = [
    Task("T1 cache-invalidering", "concept", "invalidate",
         ["invalidate_cache", "run_model_calculation", "delete_model",
          "tile_cache.py", "models.py"],
         "Hvor invalideres tile-cachen, og hvilke operasjoner trigger det?"),
    Task("T2 token-utløp", "concept", "expire",
         ["create_access_token", "expires_delta", "ACCESS_TOKEN_EXPIRE_MINUTES",
          "auth.py"],
         "Hvor settes JWT-utløp, og hva er defaulten?"),
    Task("T3 indikator-regler", "structure", r".*Rule$",
         ["NumericRule", "BooleanRule", "CategoryRule", "TextRule",
          "indicators.py"],
         "Hvilke regeltyper finnes for indikatorer?"),
    Task("T4 grid-TTL (literal — grep bør vinne)", "concept", "tile_cache_ttl",
         ["get_tile_cache_ttl", "tile_type == 'grid'"],
         "Hva er cache-TTL for grid-tiles?"),
    Task("T5 backend-arkitektur", "overview", "",
         ["main.py", "database.py", "startup_validation", "get_pool",
          "health_check"],
         "Hva er hovedarkitekturen — sentrale filer og entry points?"),
]


def coverage(accumulated: str, facts: list[str]) -> float:
    return sum(1 for f in facts if f in accumulated) / len(facts)


# ── scantool-strategi ────────────────────────────────────────────────────

def scantool_steps(task: Task):
    from scantool.server import (search_structures, scan_file,
                                 scan_directory, preview_directory)

    if task.kind == "overview":
        yield "preview_directory(deep)", preview_directory.fn(task.directory, depth="deep")[0].text
        yield "scan_directory", scan_directory.fn(task.directory)[0].text
        return

    if task.kind == "structure":
        out = search_structures.fn(task.directory, name_pattern=task.query)[0].text
    else:
        out = search_structures.fn(task.directory, content_pattern=task.query)[0].text
    yield f"search_structures({task.query!r})", out

    top_file = _first_path(out)
    if top_file:
        yield f"scan_file({Path(top_file).name}, budget=2000)", \
            scan_file.fn(top_file, budget=2000)[0].text
    yield "scan_directory", scan_directory.fn(task.directory)[0].text


def _first_path(output: str):
    for line in output.split("\n"):
        candidate = line.strip()
        if candidate.startswith("/") and Path(candidate).is_file():
            return candidate
    return None


# ── grep-baseline (generøs: smarte kontekstvinduer) ─────────────────────

def grep_steps(task: Task):
    if task.kind == "overview":
        find = subprocess.run(["find", task.directory, "-name", "*.py"],
                              capture_output=True, text=True).stdout
        yield "find *.py", find
        for name in ("README.md", "main.py"):
            hits = [l for l in find.split("\n") if l.endswith(name)]
            path = hits[0] if hits else f"{task.directory}/{name}"
            if Path(path).is_file():
                yield f"cat {name}", Path(path).read_text(errors="replace")
        return

    pattern = task.query if task.kind == "concept" else task.query.strip(".*$")
    rg = subprocess.run(["grep", "-rn", "-i", pattern, task.directory, "--include=*.py"],
                        capture_output=True, text=True).stdout
    yield f"grep -rni {pattern!r}", rg

    # fil med flest treff → ±40-linjers vinduer rundt treffklynger
    by_file: dict[str, list[int]] = {}
    for line in rg.split("\n"):
        m = re.match(r"(/[^:]+):(\d+):", line)
        if m:
            by_file.setdefault(m.group(1), []).append(int(m.group(2)))
    ranked_files = sorted(by_file, key=lambda f: -len(by_file[f]))

    for path in ranked_files[:3]:
        lines = Path(path).read_text(errors="replace").split("\n")
        windows = []
        covered_to = -1
        for hit in sorted(by_file[path])[:3]:
            lo, hi = max(0, hit - 41), min(len(lines), hit + 40)
            if lo < covered_to:
                lo = covered_to
            windows.extend(lines[lo:hi])
            covered_to = hi
        yield f"vinduer ±40 i {Path(path).name}", "\n".join(windows)

    if ranked_files:
        yield f"cat {Path(ranked_files[0]).name}", \
            Path(ranked_files[0]).read_text(errors="replace")


# ── kjøring ──────────────────────────────────────────────────────────────

def load_swebench_tasks() -> list[Task]:
    """Eksternt forankrede oppgaver: fakta = filer og funksjoner som
    SWE-bench-instansens gullpatch faktisk endret (mekanisk ekstrahert),
    katalog = repoet sjekket ut på instansens base_commit."""
    import json

    tasks = []
    for row in json.load(open("/tmp/swebench_tasks.json")):
        directory = f"/tmp/swb/{row['instance_id']}"
        if not Path(directory).is_dir():
            continue
        tasks.append(Task(
            name=row["instance_id"], kind="concept", query=row["query"],
            facts=row["facts"], description=row["title"], directory=directory,
        ))
    return tasks


def run():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        count = lambda t: len(enc.encode(t))
    except ImportError:
        count = lambda t: max(1, len(t) // 4)

    print(f"{'oppgave':42s} {'verktøysett':10s} {'kall':>4s} "
          f"{'tokens@full':>12s} {'dekning':>8s}")
    print("-" * 82)

    tasks = load_swebench_tasks() if "--swebench" in sys.argv else TASKS
    for task in tasks:
        for label, steps in (("scantool", scantool_steps), ("grep", grep_steps)):
            accumulated = ""
            tokens = 0
            calls = 0
            tokens_at_full = None
            for step_name, output in steps(task):
                calls += 1
                tokens += count(output)
                accumulated += "\n" + output
                if tokens_at_full is None and coverage(accumulated, task.facts) >= 1.0:
                    tokens_at_full = tokens
                    break  # agenten stopper når den har det den trenger
            cov = coverage(accumulated, task.facts)
            full = str(tokens_at_full) if tokens_at_full else f"({tokens})"
            print(f"{task.name:42s} {label:10s} {calls:4d} {full:>12s} "
                  f"{100*cov:7.0f}%")
            if cov < 1.0:
                missing = [f for f in task.facts if f not in accumulated]
                print(f"{'':42s} {'':10s}      mangler: {missing}")
        print()


if __name__ == "__main__":
    run()
