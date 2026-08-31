#!/usr/bin/env python
"""Refuse to push a vX.Y.Z tag whose commit does not carry that version.

Runs as a pre-push hook. The release script makes the mismatch impossible;
this catches the case where the tag was made by hand anyway. It reads
pyproject.toml and uv.lock out of the tagged commit rather than the working
tree, so it judges what is actually being pushed.
"""

import subprocess
import sys
import tomllib


def show(ref: str, path: str) -> str | None:
    result = subprocess.run(("git", "show", f"{ref}:{path}"), text=True, capture_output=True)
    return result.stdout if result.returncode == 0 else None


def locked_version(text: str) -> str | None:
    """The project's own version as recorded in uv.lock."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == 'name = "scantool"':
            for follow in lines[i + 1 : i + 4]:
                if follow.startswith("version = "):
                    return follow.split('"')[1]
    return None


def main() -> int:
    tags = subprocess.run(
        ("git", "tag", "--points-at", "HEAD"), text=True, capture_output=True
    ).stdout.split()
    problems = []
    for tag in tags:
        if not tag.startswith("v"):
            continue
        named = tag[1:]

        manifest = show(tag, "pyproject.toml")
        if manifest is None:
            continue
        declared = tomllib.loads(manifest)["project"]["version"]
        if declared != named:
            problems.append(f"  {tag}: pyproject.toml at that commit says {declared}")

        lock = show(tag, "uv.lock")
        if lock is not None:
            locked = locked_version(lock)
            if locked is not None and locked != named:
                problems.append(f"  {tag}: uv.lock at that commit says {locked}")

    if problems:
        print("\nTag does not match the version it points at:\n", file=sys.stderr)
        print("\n".join(problems), file=sys.stderr)
        print(
            "\nThe publish workflow would reject this after the release was"
            "\ncut. Fix it here instead:"
            "\n  git tag -d <tag>"
            "\n  uv run scripts/release.py --set <version>\n",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
