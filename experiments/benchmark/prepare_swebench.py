"""Prepare the SWE-bench suite: fetch instances, generate tasks, clone repos.

Externally anchored tasks: facts = files and function names the gold patch
actually touched, mechanically extracted from the patch context. Names the
patch ADDS ('+' lines) are excluded — they do not exist at base_commit and
are unfindable for any tool. Queries are hand-picked from the problem title
(documented here, open to critique).

    uv run python experiments/benchmark/prepare_swebench.py
    uv run --with tiktoken python experiments/benchmark/harness.py --swebench
"""

import json
import os
import re
import subprocess
import urllib.request

ROWS_URL = ("https://datasets-server.huggingface.co/rows"
            "?dataset=princeton-nlp%2FSWE-bench_Lite&config=default"
            "&split=test&offset={offset}&length=100")

# instance -> canonical search term (from the problem title)
CHOSEN = {
    "pallets__flask-4045": "blueprint",
    "pallets__flask-5063": "routes",
    "psf__requests-2674": "urllib3",
    "psf__requests-1963": "resolve_redirects",
    "pytest-dev__pytest-5221": "fixtures",
    "pytest-dev__pytest-7373": "skipif",
}

TASKS_PATH = "/tmp/swebench_tasks.json"
CLONE_ROOT = "/tmp/swb"


def fetch_rows() -> list[dict]:
    rows = []
    for offset in (0, 100, 200):
        with urllib.request.urlopen(ROWS_URL.format(offset=offset), timeout=30) as resp:
            rows += [r["row"] for r in json.load(resp)["rows"]]
    return rows


def build_tasks(rows: list[dict]) -> list[dict]:
    tasks = []
    for row in rows:
        if row["instance_id"] not in CHOSEN:
            continue
        patch = row["patch"]
        files = [f for f in re.findall(r"^diff --git a/(\S+)", patch, re.M)
                 if not f.startswith("tests/") and "/test" not in f]
        names = set()
        for m in re.finditer(r"^@@[^@]+@@ .*?def (\w+)", patch, re.M):
            names.add(m.group(1))
        for m in re.finditer(r"^-\s*(?:async )?def (\w+)", patch, re.M):
            names.add(m.group(1))
        names = {n for n in names if len(n) > 4 and not n.startswith("__")}
        tasks.append({
            "instance_id": row["instance_id"],
            "repo": row["repo"],
            "base_commit": row["base_commit"],
            "query": CHOSEN[row["instance_id"]],
            "facts": sorted({f.split("/")[-1] for f in files}) + sorted(names),
            "title": row["problem_statement"].split("\n")[0][:80],
        })
    return tasks


def clone(task: dict) -> None:
    dest = f"{CLONE_ROOT}/{task['instance_id']}"
    if os.path.exists(dest):
        return
    subprocess.run(["git", "init", "-q", dest], check=True)
    subprocess.run(["git", "-C", dest, "remote", "add", "origin",
                    f"https://github.com/{task['repo']}.git"], check=True)
    subprocess.run(["git", "-C", dest, "fetch", "--depth", "1", "-q",
                    "origin", task["base_commit"]], check=True)
    subprocess.run(["git", "-C", dest, "checkout", "-q", "FETCH_HEAD"], check=True)


def main():
    os.makedirs(CLONE_ROOT, exist_ok=True)
    tasks = build_tasks(fetch_rows())
    json.dump(tasks, open(TASKS_PATH, "w"), indent=2)
    for task in tasks:
        clone(task)
        print(f"{task['instance_id']}: ready (query={task['query']!r}, "
              f"{len(task['facts'])} facts)")


if __name__ == "__main__":
    main()
