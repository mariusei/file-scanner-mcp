"""M3 task verification (M3_preregistered.md, "Task verification"): for every
class-C/D task file the tail must FIRE naming the planted/decoy node; for every
class-N task file it must be SILENT. Observation only — prints the actual tails.

Usage: uv run python experiments/benchmark/m3/verify_tasks.py | tee experiments/benchmark/m3/verification.log
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from scantool import connectivity

ROOT = Path("/tmp/m3")

# (repo, relpath, class, expectation-for-the-record)
TARGETS = [
    ("pallets__flask-4045", "src/flask/debughelpers.py", "C1", "explain_ignored_app_run dead"),
    ("pallets__flask-4045", "src/flask/helpers.py", "C2", "is_ip dead"),
    ("pallets__flask-4045", "examples/tutorial/flaskr/blog.py", "D2", "orphan routes /update /delete (alive via url_for in templates)"),
    ("pallets__flask-4045", "src/flask/blueprints.py", "N", "silent"),
    ("psf__requests-2674", "requests/sessions.py", "C3", "merge_hooks dead"),
    ("psf__requests-2674", "requests/utils.py", "C4", "iter_slices dead (pre-existing candidates co-listed)"),
    ("psf__requests-2674", "requests/cookies.py", "D1", "MockRequest.* dead (alive via cookielib duck-typing)"),
    ("psf__requests-2674", "requests/adapters.py", "N", "silent"),
    ("pytest-dev__pytest-7373", "src/_pytest/pathlib.py", "C5", "resolve_from_str dead"),
    ("pytest-dev__pytest-7373", "src/_pytest/compat.py", "C6", "num_mock_patch_args dead"),
    ("pytest-dev__pytest-7373", "src/_pytest/mark/evaluate.py", "N", "silent"),
    ("psf__requests-1963", "requests/sessions.py", "N", "silent"),
    # pytest-5221 python.py DROPPED as N-task: pre-existing candidates fire there
    # (CallSpec2.setall, pyobj_property). flask-5063 cli.py also rejected
    # (FlaskGroup.get_command/list_commands/parse_args fire — click overrides).
    # Replacement: flask-4045 config.py, verified silent.
    ("pallets__flask-4045", "src/flask/config.py", "N", "silent"),
]


def main():
    for repo in sorted({t[0] for t in TARGETS}):
        directory = str(ROOT / repo)
        connectivity.clear_connectivity_cache()
        connectivity.warm(directory)
        for r, rel, cls, expect in TARGETS:
            if r != repo:
                continue
            tail = connectivity.connectivity_tail(directory, str(ROOT / repo / rel))
            print(f"--- [{cls}] {repo}/{rel} (expect: {expect})")
            print(tail if tail else "  (silent)")
        print()


if __name__ == "__main__":
    main()
