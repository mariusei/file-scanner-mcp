"""
Self-levelling connectivity tail for scan_file (server layer).

Silent on clean code (returns ""); speaks only when it catches an unprompted
regression you were not looking for — surfaced where you already work:
  - drift  : a function breaks a call pattern its siblings follow (find_divergences)
  - dead   : a source def with no inbound caller that survives reachability-channel
             subtraction (decorators / entry points / exports / name-references),
             down-weighted when the corpus uses dynamic dispatch
  - orphan : a route/template referenced nowhere (reference_map: routes + templates)

"Candidates, not verdicts." Built on the warm-cached CodeMap so always-on stays
cheap; NOT wired/referenced-by (measured grep-equivalent overhead). Server-layer,
so it is outside the frozen golden scope (like git churn / delta notes).
"""

import re
import threading
import time
from collections import Counter, OrderedDict
from pathlib import Path

from . import reference_map
from .code_map import CodeMap
from .consensus import DivergenceConfig, find_divergences
from .scanner import FileScanner

_DEAD_SKIP = frozenset({"__init__", "__repr__", "__str__", "__eq__", "__hash__", "main"})
# Dispatch-by-name conventions: invoked via getattr/framework (ast.NodeVisitor
# visit_*, cmd do_*, handlers on_*/handle_*), so structurally invisible to the
# call graph — a zero-inbound match here is reachable, not dead.
_DISPATCH_PREFIXES = ("visit_", "do_", "handle_", "on_")
_MEMO_MAX_DIRS = 8
# Above this corpus size the dead/orphan whole-repo scans are skipped (drift only).
_MAX_HEAVY_FILES = 6000
_scanner = FileScanner()

# ── Background warming ────────────────────────────────────────────────────────
# scan_file's tail is a constant-time read of the LAST computed corpus state;
# the (expensive) compute runs off the request path in a daemon thread, so a scan
# never waits. State is at most one refresh cycle stale — you see a just-introduced
# dead fn on the next scan. Lock-guarded; lives for the server process.
#   _STATE: dir -> (signature, dead:set[(file,qual)], orphans:list,
#                   drift_findings:list, dyn_dispatch:bool, timestamp)
_STATE: "OrderedDict[str, tuple]" = OrderedDict()
_LOCK = threading.Lock()
_WARMING: set = set()
_REFRESH_INTERVAL = 2.0  # seconds: do not respawn a refresh more often than this


def clear_connectivity_cache() -> None:
    with _LOCK:
        _STATE.clear()
        _WARMING.clear()


def _short(qualified: str) -> str:
    return qualified.split(":")[-1] if ":" in qualified else qualified


def _rel(directory: str, file_path: str) -> str:
    try:
        return str(Path(file_path).resolve().relative_to(Path(directory).resolve()))
    except ValueError:
        return file_path


def _decorators_in(repo: Path, relfile: str, cache: dict) -> dict:
    if relfile in cache:
        return cache[relfile]
    out: dict = {}
    try:
        nodes = _scanner.scan_file(str(repo / relfile), include_file_metadata=False) or []
    except Exception:
        nodes = []
    stack = list(nodes)
    while stack:
        n = stack.pop()
        if getattr(n, "decorators", None):
            out[n.name] = n.decorators
        stack.extend(getattr(n, "children", []) or [])
    cache[relfile] = out
    return out


def _compute_dead(directory: str, result) -> "tuple[set, bool]":
    """Zero-inbound source defs surviving channel subtraction; + dynamic-dispatch flag.

    Channels subtracted (reclassified, NOT claimed dead): decorator-registered,
    exported (__init__/__all__), name-referenced (dispatch table / registry / config).
    """
    repo = Path(directory)
    entry = {ep.name for ep in result.entry_points if ep.name}

    corpus, inits = [], []
    exts = (".py", ".js", ".ts", ".html", ".j2", ".jinja", ".yaml", ".yml", ".toml", ".json")
    for f in reference_map.source_files(repo, exts):
        try:
            t = f.read_text(errors="replace")
        except OSError:
            continue
        corpus.append(t)
        if f.name in ("__init__.py", "pyproject.toml"):
            inits.append(t)
    blob = "\n".join(corpus)
    init_text = "\n".join(inits)
    dyn = bool(re.search(r"\bgetattr\(|\bglobals\(\)\[|importlib", blob))

    # Precompute once (O(blob)), not per-candidate (O(candidates*blob)): how often
    # each name appears as a call `name(` and as a bare mention anywhere.
    call_counts = Counter(re.findall(r"\b(\w+)\s*\(", blob))
    word_counts = Counter(re.findall(r"\b\w+\b", blob))
    export_names = set(re.findall(r"\b(\w+)\b", init_text))  # lenient: any init/pyproject token

    dec_cache: dict = {}
    residue = set()
    for n in result.call_graph.values():
        qual = _short(n.name)
        bare = qual.split(".")[-1]
        if n.callers or n.type not in ("function", "method"):
            continue
        if bare in entry or bare.startswith("_") or bare in _DEAD_SKIP:
            continue
        if bare.startswith(_DISPATCH_PREFIXES):  # dispatched by name (getattr/framework)
            continue
        if "test" in n.file.lower():
            continue
        if bare in export_names:                 # exported in __init__/__all__/pyproject
            continue
        if word_counts.get(bare, 0) - call_counts.get(bare, 0) >= 1:
            continue                             # referenced but not called -> dispatch/registry
        if _decorators_in(repo, n.file, dec_cache).get(bare):  # framework-registered
            continue
        residue.add((n.file, qual))
    return residue, dyn


def _compute_orphans(directory: str) -> list:
    """(location, tag, key, pid) for every convention-aware orphan."""
    repo = Path(directory)
    out = []
    for spec in reference_map.DIRECTED_SPECS:
        try:
            _reached, orphan, _unres = reference_map.run(repo, spec)
            out += [(p.location, p.tag, p.key, p.pid) for p in orphan]
        except Exception:
            pass
    return out


def warm(directory: str, result=None) -> None:
    """Compute and cache a repo's corpus connectivity (dead + orphan + corpus-wide
    drift). Synchronous, idempotent (skips recompute when the corpus signature is
    unchanged), NEVER raises. Run inline (scan_diff) or in a daemon thread (scan_file).
    """
    try:
        if result is None:
            result = CodeMap(directory).analyze()
        sig = (len(result.definitions), len(result.calls))
        with _LOCK:
            prev = _STATE.get(directory)
            if prev is not None and prev[0] == sig:
                _STATE[directory] = (*prev[:5], time.time())  # touch ts, keep state
                return
        if result.total_files > _MAX_HEAVY_FILES:
            dead, orphans, dyn = set(), [], False
        else:
            dead, dyn = _compute_dead(directory, result)
            orphans = _compute_orphans(directory)
        try:
            fc = {f: c for c, fs in result.clusters.items() for f in fs}
            drift = find_divergences(result.definitions, result.calls,
                                     config=DivergenceConfig(TOP_N=50), file_clusters=fc)
        except Exception:
            drift = []
        with _LOCK:
            _STATE[directory] = (sig, dead, orphans, drift, dyn, time.time())
            while len(_STATE) > _MEMO_MAX_DIRS:
                _STATE.popitem(last=False)
    except Exception:
        pass
    finally:
        with _LOCK:
            _WARMING.discard(directory)


def corpus_dead_orphans(directory: str, result=None) -> "tuple[set, list, bool]":
    """Public, SYNCHRONOUS: ensure the repo's connectivity is computed, return
    (dead:set[(file,qual)], orphans:list[(loc,tag,key,pid)], dyn). Used by scan_diff,
    where review wants the current state, not a stale one."""
    warm(directory, result)
    with _LOCK:
        entry = _STATE.get(directory)
    return (entry[1], entry[2], entry[4]) if entry else (set(), [], False)


def _format_tail(entry: tuple, directory: str, file_path: str, max_items: int) -> str:
    _sig, dead_all, orphans_all, drift_all, dyn, _ts = entry
    rel = _rel(directory, file_path)
    dead = sorted({qual for f, qual in dead_all if f == rel})
    orphan = [(t, k, p) for loc, t, k, p in orphans_all if loc == rel]
    drift = [(_short(f.site), f.anchor, f.missing) for f in drift_all if f.site.startswith(rel)]
    if not (dead or orphan or drift):
        return ""
    lines = ["", "── CONNECTIVITY (whole-corpus view — candidates, not verdicts) ──"]
    if orphan:
        lines.append("  orphan (referenced nowhere — candidate dead):")
        for tag, key, pid in orphan[:max_items]:
            lines.append(f"    {tag} {key}  ({pid})")
    if dead:
        note = " [corpus uses dynamic dispatch — down-weighted]" if dyn else ""
        lines.append(f"  candidate-dead (no inbound caller, survives channel subtraction){note}:")
        lines.append(f"    {', '.join(dead[:max_items])}")
    if drift:
        lines.append("  drift (breaks a sibling call pattern):")
        for site, anchor, missing in drift[:max_items]:
            lines.append(f"    {site}: calls {anchor} but (unlike peers) not {missing}")
    return "\n".join(lines)


def connectivity_tail(directory: str, file_path: str, max_items: int = 12) -> str:
    """Constant-time connectivity note for a file: serve the last computed corpus
    state, refresh it in the background. '' until the first warm completes (the next
    scan shows it) — a scan never blocks on the corpus build."""
    with _LOCK:
        entry = _STATE.get(directory)
        stale = entry is None or (time.time() - entry[5]) > _REFRESH_INTERVAL
        spawn = stale and directory not in _WARMING
        if spawn:
            _WARMING.add(directory)
    if spawn:
        threading.Thread(target=warm, args=(directory,), daemon=True).start()
    if entry is None:
        return ""
    try:
        return _format_tail(entry, directory, file_path, max_items)
    except Exception:
        return ""
