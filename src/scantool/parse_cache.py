"""
FILE: parse_cache.py

PROBLEM:
  The same blob is parsed again on every call. The MCP server parses it
  once per call and per caller; the CLI parses it once per process, which
  is every `sct` invocation. Measured on this repository at v0.23.0:
  `scan_directory(src/scantool, ref=v0.23.0)` costs 0.73 s of which 0.58 s
  (80 %) is parsing 58 blobs, and the second identical call costs the
  same. Brief §5.1 item 8: key on the blob, parse once across calls and
  callers.

SOLUTION:
  A memo keyed on the git blob id (sha1 over "blob N\\0" + bytes, git's own
  object id, so a file at a ref and the same bytes on stdin share a key),
  the handler, the parameters that shape the answer, and the scantool
  version. Two layers: an in-process LRU of pickled results, and a disk
  layer under the user's cache directory so the next process hits too.
  A hit is `pickle.loads`, fresh objects every time (0.001 s for 59
  files against 0.19 s to parse), so a caller may mutate what it gets.
  Transparent by construction: the same bytes, handler and parameters
  give the same nodes; the goldens and every existing test run with it on.

SCOPE:
  ✓ the parse (BaseLanguage.scan) and the annotated result of
    FileScanner._scan_source when no per-line git signals are in play
  ✓ SCANTOOL_CACHE_DIR relocates the disk layer, SCANTOOL_NO_CACHE=1
    turns the disk layer off (the in-process layer stays)
  ✗ CodeMap keeps its own stat-fingerprint cache; exceptions are never
    cached; results with per-line edit labels are never cached
"""

import contextlib
import hashlib
import os
import pickle
import tempfile
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any

CACHE_DIR_ENV = "SCANTOOL_CACHE_DIR"
NO_CACHE_ENV = "SCANTOOL_NO_CACHE"

_MEMORY_ENTRIES = 512
_MEMORY_BYTES = 64 * 1024 * 1024
_DISK_BYTES = 200 * 1024 * 1024
_PRUNE_EVERY = 100  # writes between disk-size checks

_memory: OrderedDict[str, bytes] = OrderedDict()
_memory_size = 0
_writes = 0


def blob_id(data: bytes) -> str:
    """git's object id for these bytes: `git hash-object` gives the same."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def memo(key: tuple, compute: Callable[[], Any]) -> Any:
    """The result of compute() for this key, fresh objects on every call.
    The key is hashed with the scantool version, so a new release never
    reads an old release's nodes."""
    digest = _digest(key)
    stored = _memory.get(digest)
    if stored is None:
        stored = _read_disk(digest)
    if stored is None:
        stored = pickle.dumps(compute(), protocol=pickle.HIGHEST_PROTOCOL)
        _write_disk(digest, stored)
    _remember(digest, stored)
    return pickle.loads(stored)


def scan(language: Any, data: bytes) -> Any:
    """language.scan(data) through the memo: the parse itself, keyed on the
    blob, the handler and the flags that change what it returns."""
    key = (
        "scan",
        blob_id(data),
        type(language).__name__,
        getattr(language, "show_errors", None),
        getattr(language, "fallback_on_errors", None),
    )
    return memo(key, lambda: language.scan(data))


def clear() -> None:
    """Forget the in-process layer (tests, and a handler that changed)."""
    global _memory_size
    _memory.clear()
    _memory_size = 0


def cache_dir() -> Path | None:
    """Where the disk layer lives, or None when it is off."""
    if os.environ.get(NO_CACHE_ENV):
        return None
    from . import __version__

    root = os.environ.get(CACHE_DIR_ENV)
    if root:
        base = Path(root)
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "scantool"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "scantool"
    return base / f"parse-{__version__}"


# ── layers ───────────────────────────────────────────────────────────────────


def _digest(key: tuple) -> str:
    from . import __version__

    return hashlib.sha1(repr((__version__, *key)).encode("utf-8")).hexdigest()


def _remember(digest: str, stored: bytes) -> None:
    global _memory_size
    if digest in _memory:
        _memory.move_to_end(digest)
        return
    _memory[digest] = stored
    _memory_size += len(stored)
    while _memory and (len(_memory) > _MEMORY_ENTRIES or _memory_size > _MEMORY_BYTES):
        _, evicted = _memory.popitem(last=False)
        _memory_size -= len(evicted)


def _read_disk(digest: str) -> bytes | None:
    directory = cache_dir()
    if directory is None:
        return None
    path = directory / f"{digest}.pkl"
    try:
        stored = path.read_bytes()
        pickle.loads(stored)  # a torn or foreign file is a miss, not an error
        return stored
    except FileNotFoundError:
        return None
    except Exception:
        with contextlib.suppress(OSError):
            path.unlink()
        return None


def _write_disk(digest: str, stored: bytes) -> None:
    global _writes
    directory = cache_dir()
    if directory is None:
        return
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(handle, "wb") as out:
            out.write(stored)
        os.replace(temporary, directory / f"{digest}.pkl")
    except OSError:
        return  # a read-only or full disk means no disk layer, nothing else
    _writes += 1
    if _writes % _PRUNE_EVERY == 0:
        _prune(directory)


def _prune(directory: Path) -> None:
    """Keep the disk layer under its cap: oldest entries go first."""
    try:
        entries = [(p.stat().st_mtime, p.stat().st_size, p) for p in directory.glob("*.pkl")]
    except OSError:
        return
    total = sum(size for _, size, _ in entries)
    if total <= _DISK_BYTES:
        return
    for _, size, path in sorted(entries):
        try:
            path.unlink()
        except OSError:
            continue
        total -= size
        if total <= _DISK_BYTES * 3 // 4:
            break
