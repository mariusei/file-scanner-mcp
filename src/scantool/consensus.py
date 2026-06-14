"""
FIL: consensus.py

PROBLEM:
  Finne sites som bryter et kall-mønster søsknene deres følger — misalignment,
  drift, manglende konnektivitet — uten å drukne i legitim variasjon.

LØSNING:
  Call-co-occurrence-regelutvinning (Engler "bugs as deviant behavior" 2001 /
  PR-Miner 2005). Kall-grafen er JUSTEREREN: kohorten for et funn er «kallerne
  av X», justert av X — ikke fil-lokalitet eller type. Tre egenskaper, hver
  validert i experiments/network_consensus/:
    1. graf-justert kohort (ikke node-footprint),
    2. retningsbestemt — kun MANGLENDE koblet kall teller (ekstra kall = rikdom,
       ignoreres; en symmetrisk metrikk konflaterer de to),
    3. navnekvalifisering + en SELV-NIVELLERENDE gate som dreper base-rate-støy
       og setter sin egen bar etter korpusets fordeling — ingen hardkodede
       lift/confidence-gulv (REP).

  Gaten: hver kandidat-regel får en skala-fri overraskelses-score
  S = −log10 P(≥k av n kallere har Y | base-rate p). Den kalibrerer seg selv
  etter support og base-rate. Funn = robuste utliggere over korpusets egen
  S-fordeling (Tukey far-out fence, Q3 + 3·IQR). Flat fordeling (ingen ekte
  mønster) → ingen utliggere → tom output.

  Rolle-betinging (multiview-gate): en divergens beholdes kun hvis site-en spiller
  SAMME arkitektur-rolle som de konforme — målt langs ortogonale linser (navn,
  fil-cluster, kant-invariant graf-posisjon). Dette oppløser legitim kryss-rolle-
  variasjon (base-delegering, alt-parser, traverse-stil) uten å drepe ekte
  knock-outs. Validert i experiments/role_conditioning/. Rolle MÅ være ortogonal
  til usage-bags, ellers defineres signalet bort.

SCOPE:
  ✓ Ren funksjon av (definitions, calls) — deterministisk, frosset-lag, golden.
  ✓ Review-SIGNAL ("se her"), ikke defekt-orakel: peers kan legitimt avvike.
  ✓ Rolle-betinget kohort via ortogonale linser (over).
  ✗ Ingen I/O, ingen git, ingen mtime.
"""

import builtins
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from .languages.models import CallInfo, DefinitionInfo, DivergenceFinding

# Callee names that carry no contract: a co-occurring `append`/`values`/`sum`
# tells you nothing about intent — it follows everything. Builtins come from the
# interpreter programmatically; the curated set covers ubiquitous container/str
# methods that bare-name call extraction cannot distinguish from a same-named
# user definition (we have no receiver type). Same rationale as the language
# REGEX tables in CONTRIBUTING: declarative, language-level, not domain-tuned.
_COMMON_METHODS = frozenset({
    "append", "add", "extend", "insert", "remove", "pop", "get", "set", "update",
    "keys", "values", "items", "setdefault", "copy", "clear", "sort", "reverse",
    "join", "split", "rsplit", "strip", "lstrip", "rstrip", "replace", "format",
    "lower", "upper", "startswith", "endswith", "find", "rfind", "count", "index",
    "encode", "decode", "read", "write", "close", "open", "seek", "flush",
    "group", "groups", "match", "search", "finditer", "sub", "compile", "span",
    "start", "end", "exists", "is_file", "is_dir", "read_text", "write_text",
    "decode", "isdigit", "isalpha", "isspace", "title", "splitlines",
})
_NOISE_NAMES = frozenset(dir(builtins)) | _COMMON_METHODS

# Directories whose code is not a sibling family of the product: test fixtures
# build objects directly, throwaway scripts follow no shared contract. Including
# them pollutes the peer statistics (a test constructing DefinitionInfo looks
# like a "violation" of a product pattern). Matched as a path segment.
_NONSOURCE_DIRS = frozenset({
    "tests", "test", "experiments", "experiment", "examples", "benchmarks",
    "node_modules", "vendor", "third_party", "__pycache__",
})


def _is_source(path: str) -> bool:
    """True unless `path` lives under a non-product directory (see above)."""
    parts = path.replace("\\", "/").split("/")
    return not any(seg in _NONSOURCE_DIRS for seg in parts[:-1])


@dataclass(frozen=True)
class DivergenceConfig:
    """Scale-free, universal knobs — no domain-tuned thresholds (REP).

    MIN_SUPPORT  statistical floor: a consensus needs at least this many voters.
    SIG          significance floor on surprise S = -log10(p): a finding must
                 represent a statistically real consensus. 3.0 == p <= 1e-3,
                 a universal significance level (not a domain-tuned number).
    FENCE_K      Tukey far-out-outlier constant (Q3 + K·IQR); textbook universal.
                 Used only in audit mode (suspects=None) to stay conservative —
                 a consistent codebase yields no outliers, hence silence.
    PEERS_SAMPLE how many conforming siblings to cite for context.
    TOP_N        hard cap on emitted findings (display hygiene, not a gate).
    """

    MIN_SUPPORT: int = 3
    SIG: float = 3.0
    FENCE_K: float = 3.0
    MIN_FENCE_POP: int = 8  # min candidates for a meaningful IQR; below it, SIG alone gates
    PEERS_SAMPLE: int = 3
    TOP_N: int = 20


class _Cand(NamedTuple):
    strength: float  # enrichment-significance × exceptionality (ranking + gate)
    enrichment: float  # S_enr = -log10 P(>=k of n | base rate); rule-is-real gate
    anchor: str
    missing: str
    n: int
    k: int
    missing_sites: frozenset[tuple[str, str]]


def _log10_upper_tail(k: int, n: int, p: float) -> float:
    """log10 P(X >= k) for X ~ Binomial(n, p), computed in log-space.

    Stable for tiny tails (lgamma + log-sum-exp). Returns 0.0 for the
    degenerate p<=0 / p>=1 ends where the tail is exactly 1."""
    if k <= 0:
        return 0.0
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf  # impossible event -> tail 0
    if p >= 1.0:
        return 0.0  # every trial succeeds; P(X>=k)=1 for k<=n
    log_p = math.log(p)
    log_q = math.log1p(-p)
    log_terms = []
    for i in range(k, n + 1):
        log_coeff = (
            math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
        )
        log_terms.append(log_coeff + i * log_p + (n - i) * log_q)
    m = max(log_terms)
    if m == -math.inf:
        return -math.inf
    log_tail = m + math.log(sum(math.exp(t - m) for t in log_terms))
    return log_tail / math.log(10.0)


def _build_usage_bags(
    calls: list[CallInfo], internal: set[str]
) -> dict[tuple[str, str], set[str]]:
    """caller (file, name) -> set of INTERNAL callee names.

    Module-level calls (caller_name=None) are dropped — they have no enclosing
    function to attribute a usage pattern to (CLAUDE.md anti-pattern). Builtins
    are dropped by the `internal` filter: a callee co-occurring with everything
    (append/group/...) carries no contract and would only add frequent-itemset
    noise."""
    bags: dict[tuple[str, str], set[str]] = defaultdict(set)
    for c in calls:
        if not c.caller_name:
            continue
        if c.callee_name in internal and c.callee_name not in _NOISE_NAMES:
            bags[(c.caller_file, c.caller_name)].add(c.callee_name)
    return {cid: callees for cid, callees in bags.items() if callees}


def _band(x: int) -> str:
    return "0" if x == 0 else "1-2" if x <= 2 else "3-5" if x <= 5 else "6+"


def _role_conditioner(bags, file_clusters):
    """Build same_role(site, conformers, anchor, missing) -> bool.

    A site keeps a finding only if its role equals the conformers' modal role
    under EVERY orthogonal lens. Lenses (all orthogonal to the usage bags, so
    conditioning cannot define away the signal):
      - name: leading verb token of the function name (_extract_* vs _scan_*),
      - cluster: the file's architectural cluster (core vs plugins), if known,
      - graph: (in-degree band, out-degree band) — but out-degree EXCLUDES the
        contested {anchor, missing} edges so a missing call cannot shift the
        site's own band (the circularity, hardened in graph_harden.py).
    """
    in_deg: Counter = Counter()
    name_to_cids: dict[str, list] = defaultdict(list)
    for cid in bags:
        name_to_cids[cid[1]].append(cid)
    for callees in bags.values():
        for callee in callees:
            for cid in name_to_cids.get(callee, ()):
                in_deg[cid] += 1

    def name_role(cid):
        toks = [t for t in cid[1].split("_") if t]
        return toks[0] if toks else cid[1]

    def graph_role(cid, anchor, missing):
        out = len(bags.get(cid, frozenset()) - {anchor, missing})
        return (_band(in_deg.get(cid, 0)), _band(out))

    def modal(values):
        return Counter(values).most_common(1)[0][0]

    def same_role(site, conformers, anchor, missing):
        if not conformers:
            return True
        if name_role(site) != modal(name_role(c) for c in conformers):
            return False
        if file_clusters is not None:
            def cl(cid):
                return file_clusters.get(cid[0], "other")
            if cl(site) != modal(cl(c) for c in conformers):
                return False
        if graph_role(site, anchor, missing) != modal(
            graph_role(c, anchor, missing) for c in conformers
        ):
            return False
        return True

    return same_role


def find_divergences(
    definitions: list[DefinitionInfo],
    calls: list[CallInfo],
    suspects: set[tuple[str, str]] | None = None,
    config: DivergenceConfig | None = None,
    source_only: bool = True,
    file_clusters: dict[str, str] | None = None,
    role_conditioning: bool = True,
) -> list[DivergenceFinding]:
    """Mine peer-divergence findings from a call graph.

    `suspects` (a set of (file, caller) ids) restricts findings to sites that
    are among the suspects — used by scan_diff to look only at changed code,
    where divergence-from-the-established-pattern most likely means regression.
    `suspects=None` audits the whole corpus.

    `source_only` drops test/throwaway code from the peer corpus (default on);
    those follow no shared contract and only add noise.

    `role_conditioning` (default on) suppresses a finding when the site plays a
    different architectural ROLE than its conformers — the residual confound. A
    site survives only if its role equals the conformers' modal role under EVERY
    orthogonal lens (multiview-gate): name-morphology, file-cluster (needs
    `file_clusters`: file -> cluster), and edge-invariant graph position. Measured
    in `experiments/role_conditioning/` to dissolve base-delegation, alt-parser
    and traverse-style false positives while keeping true knock-outs. Role MUST be
    orthogonal to the usage bags or it would define away the signal; graph degree
    is made edge-invariant (excludes the contested edge) so a missing call cannot
    shift the site's own role.
    """
    cfg = config or DivergenceConfig()
    if source_only:
        definitions = [d for d in definitions if _is_source(d.file)]
        calls = [c for c in calls if _is_source(c.caller_file)]
    internal = {d.name for d in definitions if d.name}
    bags = _build_usage_bags(calls, internal)

    n_callers = len(bags)
    if n_callers < cfg.MIN_SUPPORT:
        return []

    callers_of: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for cid, callees in bags.items():
        for y in callees:
            callers_of[y].add(cid)
    base_rate = {y: len(cs) / n_callers for y, cs in callers_of.items()}

    # Candidate rules: X -> Y where a MAJORITY of X's callers also call Y, but
    # at least one does not. Majority (k > n/2) is the *definition* of a
    # consensus to break, not a tuning knob. Strength fuses two scale-free terms:
    #   enrichment  S_enr = -log10 P(>=k of n | base rate p) — is the rule REAL
    #               (Y specifically enriched among X's callers, not just common)?
    #               This is the frequent-itemset-noise killer and the SIG gate.
    #   exception   -log10((n-k)/(n+1)) — is the MISSING side a rare minority?
    #               Demotes weak majorities (86/140) below near-unanimous-but-
    #               small consensuses (4/5); a Beta(1,1)-smoothed miss rate.
    candidates: list[_Cand] = []
    for x, x_callers in callers_of.items():
        n = len(x_callers)
        if n < cfg.MIN_SUPPORT:
            continue
        co: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for cid in x_callers:
            for y in bags[cid]:
                if y != x:
                    co[y].add(cid)
        for y, conformers in co.items():
            k = len(conformers)
            if k <= n / 2 or k >= n:  # not a majority, or nobody is missing
                continue
            enrichment = -_log10_upper_tail(k, n, base_rate[y])
            exception = -math.log10((n - k) / (n + 1))
            candidates.append(
                _Cand(
                    enrichment * exception,
                    enrichment,
                    x,
                    y,
                    n,
                    k,
                    frozenset(x_callers - conformers),
                )
            )

    if not candidates:
        return []

    # Self-levelling gate, applied in BOTH contexts: a finding must be a far-out
    # outlier of the corpus's OWN strength distribution (Tukey fence) — a
    # consistent codebase has no outliers, hence silence, the truthful signal.
    # SIG is a secondary floor guarding degenerate tiny corpora. The contexts
    # differ only in scope:
    #   audit  (suspects=None): every outlier site.
    #   review (suspects set):  outliers AND changed code — a touched function
    #          that breaks a STRONG sibling pattern (likely regression).
    # The Tukey fence needs a populated distribution to mean anything; with too
    # few candidates the IQR is degenerate, so fall back to the SIG floor alone
    # (fence=-inf disables it). Real corpora have hundreds of candidates and use
    # the fence; a tiny module just surfaces its statistically-real breaks.
    if len(candidates) >= cfg.MIN_FENCE_POP:
        strengths = np.array([c.strength for c in candidates], dtype=float)
        q1, q3 = np.percentile(strengths, [25, 75])
        iqr = float(q3 - q1)
        fence = q3 + cfg.FENCE_K * iqr if iqr > 0 else float(np.max(strengths))
    else:
        fence = -math.inf

    same_role = _role_conditioner(bags, file_clusters) if role_conditioning else None

    findings: list[DivergenceFinding] = []
    for cand in candidates:
        if cand.enrichment < cfg.SIG:  # rule must be statistically real
            continue
        if cand.strength <= fence:  # self-levelling outlier gate (both contexts)
            continue
        conformers = sorted(callers_of[cand.anchor] & callers_of[cand.missing])
        sample = [f"{f}:{c}" for f, c in conformers][: cfg.PEERS_SAMPLE]
        for f, c in sorted(cand.missing_sites):
            if suspects is not None and (f, c) not in suspects:
                continue
            if same_role is not None and not same_role(
                (f, c), conformers, cand.anchor, cand.missing
            ):
                continue  # site plays a different architectural role — not drift
            findings.append(
                DivergenceFinding(
                    site=f"{f}:{c}",
                    anchor=cand.anchor,
                    missing=cand.missing,
                    peer_count=cand.n,
                    conform_count=cand.k,
                    surprise=cand.strength,
                    peers_sample=sample,
                )
            )

    findings.sort(key=lambda d: (-d.surprise, d.site, d.anchor, d.missing))
    return findings[: cfg.TOP_N]


def format_divergences(findings: list[DivergenceFinding]) -> str:
    """Render findings as a frozen output section, grouped by site.

    Framing is deliberate: this is a review signal, not a bug list. The header
    and footer keep an LLM consumer from treating low-confidence hints as facts
    (see HANDOVER / the network_consensus arc: director, not oracle)."""
    header = (
        "━━━ PEER DIVERGENCE ━━━  "
        "(sites breaking a sibling pattern — review, not bugs)"
    )
    if not findings:
        return header + "\n  none above the codebase's own noise floor\n"

    by_site: dict[str, list[DivergenceFinding]] = defaultdict(list)
    for f in findings:
        by_site[f.site].append(f)

    lines = [header]
    for site in sorted(
        by_site, key=lambda s: -max(f.surprise for f in by_site[s])
    ):
        group = by_site[site]
        for f in group:
            ratio = f"{f.conform_count}/{f.peer_count} peers"
            lines.append(
                f"  {site} — calls {f.anchor} but not {f.missing} "
                f"({ratio} do)  [strength {f.surprise:.1f}]"
            )
        peers = group[0].peers_sample
        if peers:
            shown = ", ".join(peers)
            lines.append(f"      e.g. siblings that conform: {shown}")
    lines.append(
        "  Note: peers may legitimately differ — treat as \"look here\", "
        "adjudicate by reading."
    )
    return "\n".join(lines) + "\n"
