"""
M2-BENCHMARK: Information-delivery efficiency, scantool vs grep baseline

WHAT IS MEASURED (and not):
  Tokens and tool calls until ALL ground-truth facts for a task are
  visible in accumulated tool output, under canonical strategies defined
  below. This is necessary-but-not-sufficient for "the agent solves the
  task better" — real agent episodes are M2b. Deterministic and
  reproducible.

FALSIFIABILITY:
  - Facts are "what the agent must know to act": enclosing functions,
    files, collaborators — not just hit lines
  - The baseline is GENEROUS: smart grep with context windows around hit
    clusters, not a naive cat of whole files
  - T4 is designed so grep can win (literal lookup) — if scantool wins
    everything, the harness is suspect

CANONICAL STRATEGIES:
  scantool concept:   search_structures(content_pattern) → scan_file(top-
                      hit file, budget=2000) → scan_directory(dir)
  scantool structure: search_structures(name_pattern) → scan_file(...)
  scantool overview:  preview_directory(deep) → scan_directory(dir)
  grep concept:       grep -rn → ±40-line windows around hit clusters in
                      the file with most hits → next file → full cat of top file
  grep overview:      find *.py → cat README → cat main.py
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@dataclass
class Task:
    name: str
    kind: str                 # "concept" | "structure" | "overview"
    query: str                # search term for both toolsets
    facts: list[str]          # distinct substrings that MUST be visible
    description: str = ""
    directory: str = ""


def load_sg_tasks() -> list[Task]:
    """The original T1–T5 task set targets a private production backend
    ("sg"); its repo path and ground-truth facts are held outside this
    repo. Point SG_TASKS at the private task JSON to reproduce.
    --swebench needs no private config."""
    path = os.environ.get("SG_TASKS")
    if not path:
        sys.exit("SG_TASKS is not set — the sg task definitions are held "
                 "privately. Run with --swebench for the public task set.")
    return [Task(**row) for row in json.load(open(path))]


def coverage(accumulated: str, facts: list[str]) -> float:
    return sum(1 for f in facts if f in accumulated) / len(facts)


# ── scantool strategy ────────────────────────────────────────────────────

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

    # follow the first lead (the leads footer) — the structural jump to the neighboring file
    lead_file = _first_lead(out)
    if lead_file and lead_file != top_file:
        yield f"scan_file(lead: {Path(lead_file).name})", \
            scan_file.fn(lead_file, budget=2000)[0].text

    yield "scan_directory", scan_directory.fn(task.directory)[0].text


def _first_lead(output: str):
    m = re.search(r"leads \(called in hits, defined elsewhere\): \w+ → (\S+)@\d+", output)
    return m.group(1) if m else None


def _first_path(output: str):
    for line in output.split("\n"):
        candidate = line.strip()
        if candidate.startswith("/") and Path(candidate).is_file():
            return candidate
    return None


# ── grep baseline (generous: smart context windows) ─────────────────────

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

    # file with most hits → ±40-line windows around hit clusters
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
        yield f"windows ±40 in {Path(path).name}", "\n".join(windows)

    if ranked_files:
        yield f"cat {Path(ranked_files[0]).name}", \
            Path(ranked_files[0]).read_text(errors="replace")


# ── execution ────────────────────────────────────────────────────────────

def load_swebench_tasks() -> list[Task]:
    """Externally anchored tasks: facts = files and functions that the
    SWE-bench instance's gold patch actually changed (mechanically
    extracted), directory = the repo checked out at the instance's
    base_commit."""
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

    print(f"{'task':42s} {'toolset':10s} {'calls':>5s} "
          f"{'tokens@full':>12s} {'coverage':>8s}")
    print("-" * 82)

    tasks = load_swebench_tasks() if "--swebench" in sys.argv else load_sg_tasks()
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
                    break  # the agent stops once it has what it needs
            cov = coverage(accumulated, task.facts)
            full = str(tokens_at_full) if tokens_at_full else f"({tokens})"
            print(f"{task.name:42s} {label:10s} {calls:5d} {full:>12s} "
                  f"{100*cov:7.0f}%")
            if cov < 1.0:
                missing = [f for f in task.facts if f not in accumulated]
                print(f"{'':42s} {'':10s}      missing: {missing}")
        print()


if __name__ == "__main__":
    run()
