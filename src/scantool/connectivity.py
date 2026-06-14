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
from collections import Counter, OrderedDict
from pathlib import Path

from . import reference_map
from .code_map import CodeMap
from .consensus import DivergenceConfig, find_divergences
from .scanner import FileScanner

_DEAD_SKIP = frozenset({"__init__", "__repr__", "__str__", "__eq__", "__hash__", "main"})
_MEMO_MAX_DIRS = 8
# Above this corpus size the dead/orphan whole-repo scans cost too much on a
# first (cold) call to do inline; keep the cheap drift signal, skip the rest.
# (Step 4: warm these in the background so huge repos get them too.)
_MAX_HEAVY_FILES = 6000
# dir -> (corpus_signature, dead:set[(file,qual)], orphans:list, dyn_dispatch:bool)
_TAIL_MEMO: "OrderedDict[str, tuple]" = OrderedDict()
_scanner = FileScanner()


def clear_connectivity_cache() -> None:
    _TAIL_MEMO.clear()


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


def _dead_and_orphans(directory: str, result) -> "tuple[set, list, bool]":
    sig = (len(result.definitions), len(result.calls))
    cached = _TAIL_MEMO.get(directory)
    if cached is not None and cached[0] == sig:
        _TAIL_MEMO.move_to_end(directory)
        return cached[1], cached[2], cached[3]
    dead, dyn = _compute_dead(directory, result)
    orphans = _compute_orphans(directory)
    _TAIL_MEMO[directory] = (sig, dead, orphans, dyn)
    while len(_TAIL_MEMO) > _MEMO_MAX_DIRS:
        _TAIL_MEMO.popitem(last=False)
    return dead, orphans, dyn


def corpus_dead_orphans(directory: str, result) -> "tuple[set, list, bool]":
    """Public: channel-subtracted dead residue (set[(file, qualname)]) +
    reference-mapping orphans (list[(location, tag, key, pid)]) + dynamic-dispatch
    flag, for a whole repo. Memoised per directory (shared with the scan_file tail).
    Empty above the heavy-corpus guard — the cheap drift signal still applies."""
    if result.total_files > _MAX_HEAVY_FILES:
        return set(), [], False
    try:
        return _dead_and_orphans(directory, result)
    except Exception:
        return set(), [], False


def connectivity_tail(directory: str, file_path: str, max_items: int = 12) -> str:
    """A connectivity note for one file, or '' when nothing fires / on error."""
    try:
        result = CodeMap(directory).analyze()
    except Exception:
        return ""
    if not result.call_graph:
        return ""
    rel = _rel(directory, file_path)

    drift = []
    try:
        fc = {f: c for c, fs in result.clusters.items() for f in fs}
        for fnd in find_divergences(result.definitions, result.calls,
                                    config=DivergenceConfig(TOP_N=20), file_clusters=fc):
            if fnd.site.startswith(rel):
                drift.append((_short(fnd.site), fnd.anchor, fnd.missing))
    except Exception:
        pass

    dead_all, orphans_all, dyn = corpus_dead_orphans(directory, result)
    dead = sorted({name for f, name in dead_all if f == rel})
    orphan = [(t, k, p) for loc, t, k, p in orphans_all if loc == rel]

    if not (drift or dead or orphan):
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
