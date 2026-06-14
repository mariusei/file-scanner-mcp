"""
Mechanism tests for peer-divergence detection (consensus.find_divergences).

Ported from experiments/network_consensus/: the three properties that make this
distinct from the seven failed distributional attempts —
  1. knock-out recovery: removing a coupled call surfaces exactly that site,
  2. directional asymmetry: ADDING an extra call surfaces nothing (extra is
     richness, not a hole — a symmetric metric would flag it),
  3. self-levelling silence: a corpus with no real consensus stays empty,
plus base-rate suppression (builtin-named callees carry no rule) and the
suspect filter (review mode looks only at changed code).

The synthetic builder gives precise control over support and base rate; one
integration test runs the real tree-sitter pipeline over the frozen fixture.
"""

from pathlib import Path

from scantool.code_map import CodeMap
from scantool.consensus import find_divergences
from scantool.languages.models import CallInfo, DefinitionInfo

FIXTURE = Path(__file__).parent / "golden" / "consensus_fixture"


def _corpus(callers: dict[str, list[str]]):
    """Build (definitions, calls) from a {caller_name: [callee_names]} map.

    Every distinct name is defined (so callees qualify as internal); each
    (caller, callee) becomes one call in a single synthetic file."""
    names = set(callers) | {c for cs in callers.values() for c in cs}
    defs = [DefinitionInfo(file="m.py", type="function", name=n, line=1) for n in names]
    calls = [
        CallInfo(caller_file="m.py", caller_name=caller, callee_name=callee, line=1)
        for caller, callees in callers.items()
        for callee in callees
    ]
    return defs, calls


def _family(extra_noise: int = 25) -> dict[str, list[str]]:
    """Eight siblings call read_node+record; `noise` unrelated callers keep the
    base rate of record low and never call read_node/record."""
    callers: dict[str, list[str]] = {}
    for i in range(8):
        callers[f"extract_{i}"] = ["read_node", "record"]
    callers["extract_outlier"] = ["read_node"]  # same role, missing record
    for i in range(extra_noise):
        callers[f"noise_{i}"] = [f"helper_{i % 5}", f"util_{i % 4}"]
    return callers


def test_knockout_recovery():
    """The one site missing the coupled call is surfaced."""
    defs, calls = _corpus(_family())
    findings = find_divergences(defs, calls)
    sites = {f.site for f in findings}
    assert ("m.py:extract_outlier") in sites
    hit = next(f for f in findings if f.site == "m.py:extract_outlier")
    assert hit.anchor == "read_node" and hit.missing == "record"


def test_conforming_site_not_flagged():
    """A sibling that follows the pattern is never a finding."""
    defs, calls = _corpus(_family())
    sites = {f.site for f in find_divergences(defs, calls)}
    assert "m.py:extract_3" not in sites


def test_directional_asymmetry():
    """Adding an EXTRA unique call (richness) creates no finding — only a
    MISSING coupled call (a hole) does. A symmetric metric would flag this."""
    family = _family()
    family["extract_0"] = ["read_node", "record", "an_extra_unique_call"]
    defs, calls = _corpus(family)
    sites = {f.site for f in find_divergences(defs, calls)}
    assert "m.py:extract_0" not in sites


def test_self_levelling_silence():
    """A corpus with no shared pattern yields nothing — not a weak guess."""
    callers = {f"fn_{i}": [f"a_{i}", f"b_{i}"] for i in range(20)}  # all distinct
    defs, calls = _corpus(callers)
    assert find_divergences(defs, calls) == []


def test_base_rate_suppression():
    """A builtin-named callee (append) co-occurring with everything forms no
    rule — it carries no contract."""
    callers = {f"fn_{i}": ["read_node", "append"] for i in range(8)}
    callers["solo"] = ["read_node"]  # 'missing' append, but append is noise
    callers.update({f"n_{i}": [f"h_{i % 3}"] for i in range(15)})
    defs, calls = _corpus(callers)
    findings = find_divergences(defs, calls)
    assert all(f.missing != "append" for f in findings)


def test_suspect_filter_restricts_to_changed_code():
    """Review mode: only sites among the suspects are returned."""
    defs, calls = _corpus(_family())
    only = find_divergences(defs, calls, suspects={("m.py", "extract_outlier")})
    assert {f.site for f in only} == {"m.py:extract_outlier"}
    none = find_divergences(defs, calls, suspects={("m.py", "extract_3")})
    assert none == []


def test_role_conditioning_dissolves_cross_role_site():
    """A caller of the same anchor missing the coupled call is flagged ONLY if it
    shares the conformers' role. A different name-role (scan_* vs extract_*) is
    dissolved by conditioning but present without it."""
    fam = _family()
    fam["scan_thing"] = ["read_node"]  # caller of read_node, missing record, cross-role
    defs, calls = _corpus(fam)
    on = {f.site for f in find_divergences(defs, calls, role_conditioning=True)}
    off = {f.site for f in find_divergences(defs, calls, role_conditioning=False)}
    assert "m.py:scan_thing" in off  # a divergence by the raw metric
    assert "m.py:scan_thing" not in on  # dissolved: different architectural role
    assert "m.py:extract_outlier" in on  # same-role divergence survives conditioning


def test_fixture_surfaces_planted_outlier():
    """End-to-end over the frozen fixture via the real tree-sitter pipeline."""
    result = CodeMap(str(FIXTURE)).analyze()
    findings = find_divergences(result.definitions, result.calls)
    sites = {f.site for f in findings}
    assert "extractors.py:extract_legacy" in sites
    assert not any(s.startswith("other.py") for s in sites)
    assert "extractors.py:extract_view" not in sites
