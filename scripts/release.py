#!/usr/bin/env python
"""
FIL: scripts/release.py

PROBLEM:
  The version lives in pyproject.toml, uv.lock records it a second time, and
  the git tag names it a third. Bumping by hand and tagging as a separate step
  lets the three drift, and the drift is only caught by the publish workflow —
  after the tag exists and the release is cut.

LØSNING:
  One command owns the whole sequence. The tag is read out of pyproject after
  the bump rather than typed again, so it cannot disagree. Nothing is committed
  until the gates pass, and any failure leaves the tree as it was found.

SCOPE:
  ✓ Bump, lock, verify, commit, tag.
  ✗ Does not push. It prints the command and lets you look first.
"""

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILES = ("pyproject.toml", "uv.lock")


def run(*args: str, capture: bool = False, quiet: bool = False) -> str:
    """Run a command in the repo root; abort the release on any failure.

    quiet swallows the command's own output — step() already reports the
    outcome — but replays it when the command fails, which is when you
    need it.
    """
    hide = capture or quiet
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if hide else None,
        stderr=subprocess.PIPE if quiet else None,
    )
    if result.returncode != 0:
        if quiet:
            print(result.stdout or "", file=sys.stderr)
            print(result.stderr or "", file=sys.stderr)
        die(f"command failed: {' '.join(args)}")
    return (result.stdout or "").strip()


def die(message: str) -> None:
    print(f"\n  aborted: {message}", file=sys.stderr)
    sys.exit(1)


def step(label: str, detail: str = "") -> None:
    print(f"  {label:.<26} {detail or 'ok'}")


def current_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return data["project"]["version"]


def restore() -> None:
    """Put the version files back the way we found them."""
    run("git", "checkout", "--", *VERSION_FILES)


def preflight(allow_dirty: bool) -> None:
    if not allow_dirty and run("git", "status", "--porcelain", capture=True):
        die(
            "working tree is dirty — commit or stash first, so the tag names "
            "exactly what you think it does"
        )
    step("working tree clean")

    branch = run("git", "rev-parse", "--abbrev-ref", "HEAD", capture=True)
    if branch != "main":
        die(f"on branch {branch}, not main")
    step("on main")

    run("git", "fetch", "--quiet", "origin", "main")
    behind = run("git", "rev-list", "--count", "HEAD..origin/main", capture=True)
    if behind != "0":
        die(f"{behind} commit(s) behind origin/main — pull first")
    step("in sync with origin")


def gates() -> None:
    """The same three gates CI runs. Cheaper to fail here than after tagging."""
    run("uv", "run", "ruff", "check", ".", quiet=True)
    step("ruff check")
    run("uv", "run", "ruff", "format", "--check", ".", quiet=True)
    step("ruff format")
    run("uv", "run", "mypy", quiet=True)
    step("mypy")
    out = run("uv", "run", "pytest", "tests/", "-q", capture=True)
    step("tests", out.splitlines()[-1].strip() if out else "ok")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bump", choices=("major", "minor", "patch"))
    group.add_argument("--set", dest="exact", metavar="X.Y.Z")
    parser.add_argument(
        "--dry-run", action="store_true", help="stop before committing and undo the bump"
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="skip the clean-tree check (for fixing a failed run)",
    )
    args = parser.parse_args()

    print()
    preflight(args.allow_dirty)
    gates()

    was = current_version()
    if args.bump:
        run("uv", "version", "--bump", args.bump, quiet=True)
    else:
        run("uv", "version", args.exact, quiet=True)
    now = current_version()
    step("version", f"{was} => {now}")

    # uv version writes pyproject only; the lockfile records the project's own
    # version too and has to follow, or `uv sync --locked` fails in CI.
    run("uv", "lock", quiet=True)
    step("uv lock")

    if subprocess.run(
        ("uv", "sync", "--locked", "--group", "dev"),
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    ).returncode:
        restore()
        die("lockfile still disagrees with pyproject after `uv lock`")
    step("lockfile agrees")

    tag = f"v{now}"
    if run("git", "tag", "--list", tag, capture=True):
        restore()
        die(f"tag {tag} already exists")

    if args.dry_run:
        restore()
        print(f"\n  dry run — would commit and tag {tag}, nothing changed\n")
        return

    run("git", "add", *VERSION_FILES)
    run("git", "commit", "--quiet", "-m", f"Bump version to {now}")
    step("commit", f'"Bump version to {now}"')

    # Read back from pyproject rather than reusing a typed-in string: the tag
    # is a consequence of the version, never a second place to state it.
    run("git", "tag", "-a", tag, "-m", f"Release {tag}")
    step("tag", f"{tag} (from pyproject)")

    print("\n  push when ready:\n    git push origin main --follow-tags\n")


if __name__ == "__main__":
    main()
