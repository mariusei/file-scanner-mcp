"""
FILE: gitref.py

PROBLEM:
  Reading at a git ref without a checkout needs the same four moves in
  every command: find the repository from a path, tell a blob from a
  tree, read a blob, unpack a tree into a temporary directory.

SOLUTION:
  Those four, with the errors worded for the caller (§9 item 2: the message
  names the ref, the path and the repository). Callers keep the answer in
  the caller's own path names; see cli._relabel.

SCOPE:
  ✓ repository lookup from an existing ancestor, blob/tree kind, blob text,
    tree materialised under the caller's directory name
  ✗ no caching across calls (each request is its own process)
"""

import io
import os
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager


class RefError(Exception):
    """Nothing to read at the ref: the message names the ref, the path and
    the repository, so the next call can be corrected. Exit 1."""


def git(top: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", top, *args], capture_output=True)


def repo_and_rel(path: str) -> tuple[str, str]:
    """The repository containing path and path's forward-slash form relative
    to its top. The path need not exist in the working tree; it may exist
    only at the ref, so the repository is found from its nearest existing
    ancestor."""
    probe = os.path.abspath(path)
    while not os.path.isdir(probe):
        probe = os.path.dirname(probe)
    result = subprocess.run(
        ["git", "-C", probe, "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RefError(f"{path} is not inside a git repository; --ref needs one")
    top = result.stdout.strip()
    rel = os.path.relpath(os.path.abspath(path), top).replace(os.sep, "/")
    return top, "" if rel == "." else rel


def spec(ref: str, rel: str) -> str:
    return f"{ref}:{rel}" if rel else ref


def ref_kind(top: str, ref: str, rel: str) -> str:
    """'blob' or 'tree'; RefError with git's own words when there is neither."""
    result = git(top, "cat-file", "-t", spec(ref, rel))
    if result.returncode != 0:
        reason = result.stderr.decode(errors="replace").strip().splitlines()
        raise RefError(
            f"{spec(ref, rel)} is not in {top} ({reason[0] if reason else 'git failed'})"
        )
    kind = result.stdout.decode().strip()
    return "tree" if kind == "commit" else kind  # the repository root is a tree


def blob(top: str, ref: str, rel: str) -> str:
    result = git(top, "show", spec(ref, rel))
    if result.returncode != 0:
        raise RefError(f"{spec(ref, rel)} is not in {top}")
    return result.stdout.decode("utf-8", errors="replace")


@contextmanager
def materialised(top: str, ref: str, rel: str, name: str) -> Iterator[str]:
    """The tree at ref unpacked into a temporary directory under `name`, so
    the directory answer carries the caller's own name for it."""
    result = git(top, "archive", "--format=tar", spec(ref, rel))
    if result.returncode != 0:
        raise RefError(f"{spec(ref, rel)} is not a directory in {top}")
    with tempfile.TemporaryDirectory(prefix="sct-ref-") as scratch:
        target = os.path.join(scratch, name)
        os.mkdir(target)
        with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
            if hasattr(tarfile, "data_filter"):  # 3.11.4+: refuse links and absolute paths
                tar.extractall(target, filter="data")
            else:
                tar.extractall(target)
        yield target
