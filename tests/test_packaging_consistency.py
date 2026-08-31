"""The same value stated in two places drifts. These are the pairs this repo
has actually drifted on, kept honest by a test rather than by remembering.

- The Typing :: Typed classifier and the py.typed marker (the classifier
  claimed the package shipped types while the file did not exist).
- A tool pinned both in the dev group and by a pre-commit rev (hook and CI
  then format differently, and the two fight over every commit).

pyproject's version against uv.lock is deliberately NOT tested here. The
assertion is easy to write and passes for the wrong reason: `uv run`
re-syncs the lockfile before pytest starts, so the drift repairs itself
before the test can see it. Under `.venv/bin/python` it fails correctly,
under `uv run` it cannot — and `uv run` is how this suite is run. That
invariant is enforced where it actually bites: `uv sync --locked` in both
workflows and in scripts/release.py.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_typed_classifier_matches_the_marker():
    claims_typed = any(c.startswith("Typing :: Typed") for c in MANIFEST["project"]["classifiers"])
    marker = ROOT / "src" / "scantool" / "py.typed"
    assert claims_typed == marker.exists(), (
        "the Typing :: Typed classifier and src/scantool/py.typed must agree: "
        "without the marker, downstream type checkers ignore our annotations "
        "while PyPI advertises them"
    )


def test_no_tool_is_pinned_in_both_the_dev_group_and_pre_commit():
    dev = MANIFEST["dependency-groups"]["dev"]
    names = {req.split(">")[0].split("=")[0].split("[")[0].strip().lower() for req in dev}

    # Hook mirrors are named after the tool they wrap: ruff-pre-commit,
    # mirrors-mypy, black-pre-commit-mirror. pre-commit-hooks wraps no single
    # tool, so it is not a mirror and must not match.
    def wrapped_tool(repo: str) -> str | None:
        for prefix, suffix in (("", "-pre-commit"), ("mirrors-", ""), ("", "-pre-commit-mirror")):
            if suffix and repo.endswith(suffix) and repo.startswith(prefix):
                return repo[len(prefix) : -len(suffix)]
            if prefix and repo.startswith(prefix) and not suffix:
                return repo[len(prefix) :]
        return None

    config = (ROOT / ".pre-commit-config.yaml").read_text()
    clashes = set()
    for line in config.splitlines():
        if not line.strip().startswith("- repo: https://"):
            continue
        tool = wrapped_tool(line.split("/")[-1].strip())
        if tool and tool.lower() in names:
            clashes.add(tool)

    assert not clashes, (
        f"{sorted(clashes)} is version-pinned both in the dev group and by a "
        "pre-commit rev. Run it from the dev group with `language: system` so "
        "the hook and CI cannot disagree."
    )
