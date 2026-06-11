"""
FILE: delta.py

PROBLEM:
  An agent working iteratively re-scans from scratch and pays full price
  for information it has already received. grep and AST tools are
  stateless by definition — state is structurally unmatchable.

SOLUTION:
  The server process remembers the previous scan per file (file fingerprint
  = mtime+size, node fingerprint = source hash). A re-scan delivers only
  changes: unchanged files as one line, unchanged nodes without skeletons.
  The token-allocation principle in its purest form: unchanged costs ~zero,
  changes get all the attention.

CONTRACT:
  - Delta refers ONLY to what equals the previous output — never a guess.
    Output always says how to get everything (delta=False), because the
    consumer's context may have been compacted away.
  - The first scan of a file is always full.
  - The memory is AGE-LIMITED: a long-lived server process (HTTP, reused
    stdio) crosses conversations, and delta must never refer to output a
    new conversation has never seen. Entries older than the TTL are treated
    as a first scan, and unchanged messages state the age.
"""

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Optional

# Within-session iteration is preserved; cross-conversation ghosts die
_MEMORY_TTL_SECONDS = 30 * 60


def format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)} sec"
    return f"{int(seconds / 60)} min"


@dataclass
class NodeDiff:
    """Node-level changes for a re-scanned, modified file."""

    new: set[str] = field(default_factory=set)        # node keys
    changed: set[str] = field(default_factory=set)
    removed: list[str] = field(default_factory=list)  # display names
    unchanged: set[str] = field(default_factory=set)


def node_key(node, parent_chain: str = "") -> str:
    return f"{parent_chain}/{node.type}:{node.name}"


def node_hashes(structures, source_lines: list[str]) -> dict[str, str]:
    """Fingerprint every named node by its source block — the shared
    primitive for both session deltas and ref diffs."""
    hashes: dict[str, str] = {}

    def walk(nodes, chain: str):
        for node in nodes or []:
            if node.type != "file-info" and node.name:
                key = node_key(node, chain)
                # whitespace-normalized: trailing-space/blank-line edits are
                # not structural changes
                block = "\n".join(
                    line.rstrip()
                    for line in source_lines[node.start_line - 1:node.end_line]
                    if line.strip()
                )
                hashes[key] = hashlib.sha1(block.encode()).hexdigest()
                walk(node.children, key)
            else:
                walk(node.children, chain)

    walk(structures, "")
    return hashes


def diff_nodes(previous: dict[str, str], current: dict[str, str]) -> NodeDiff:
    """Structural change set between two node-fingerprint maps."""
    diff = NodeDiff()
    for key, digest in current.items():
        if key not in previous:
            diff.new.add(key)
        elif previous[key] != digest:
            diff.changed.add(key)
        else:
            diff.unchanged.add(key)
    diff.removed = sorted(
        key.rsplit(":", 1)[-1] for key in previous if key not in current
    )
    return diff


class ScanMemory:
    """Remembers previous scans; answers "what changed since last time?"."""

    def __init__(self):
        self._files: dict[str, tuple] = {}  # path -> (stat_fp, {key: hash}, recorded_at)

    def clear(self) -> None:
        self._files.clear()

    @staticmethod
    def _stat_fingerprint(path: str) -> Optional[tuple]:
        try:
            stat = os.stat(path)
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def file_unchanged(self, path: str) -> Optional[float]:
        """Age in seconds of the previous identical scan — None if changed,
        unseen, or the memory has expired (TTL)."""
        cached = self._files.get(path)
        if cached is None:
            return None
        age = time.time() - cached[2]
        if age > _MEMORY_TTL_SECONDS:
            del self._files[path]
            return None
        fingerprint = self._stat_fingerprint(path)
        if fingerprint is not None and fingerprint == cached[0]:
            return age
        return None

    def diff_and_record(self, path: str, structures,
                        source_lines: list[str]) -> Optional[NodeDiff]:
        """Node-diff against the previous scan (None on first scan), then
        record the current state."""
        fingerprint = self._stat_fingerprint(path)
        current = node_hashes(structures, source_lines)
        previous = self._files.get(path)

        self._files[path] = (fingerprint, current, time.time())

        if previous is None or time.time() - previous[2] > _MEMORY_TTL_SECONDS:
            return None  # expired memory = first scan, never a ghost diff
        return diff_nodes(previous[1], current)


def apply_node_delta(structures, diff: NodeDiff) -> tuple[int, int]:
    """Suppress code detail for unchanged nodes and label new/changed ones.

    Headers always survive — only skeletons/excerpts are suppressed, so a
    consumer with compacted context still sees the full structure.

    Returns (changed_count, unchanged_count).
    """
    changed = unchanged = 0

    def walk(nodes, chain: str):
        nonlocal changed, unchanged
        for node in nodes or []:
            if node.type != "file-info" and node.name:
                key = node_key(node, chain)
                if key in diff.new:
                    node.delta_status = "new"
                    changed += 1
                elif key in diff.changed:
                    node.delta_status = "changed"
                    changed += 1
                elif key in diff.unchanged:
                    node.code_skeleton = None
                    node.code_excerpt = None
                    unchanged += 1
                walk(node.children, key)
            else:
                walk(node.children, chain)

    walk(structures, "")
    return changed, unchanged
