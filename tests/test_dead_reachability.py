"""Cross-language safety for dead-code detection.

The framework only claims a definition dead if its LANGUAGE has opted in
(CLAIMS_DEAD) and adjudges it off-graph-unreachable. A language whose reachability
is not modelled is silent — never a false "this is dead". These tests lock that:
public/exported API is never flagged, and un-opted-in languages stay silent.
"""
import tempfile
from pathlib import Path

from scantool.code_map import CodeMap, clear_corpus_cache
from scantool.connectivity import _compute_dead


def _dead_names(filename: str, source: str):
    d = tempfile.mkdtemp()
    Path(d, filename).write_text(source)
    clear_corpus_cache()
    result = CodeMap(d).analyze()
    dead, _dyn = _compute_dead(d, result)
    return {qual.split(".")[-1] for _f, qual in dead}


def test_go_exports_by_capitalisation():
    dead = _dead_names(
        "a.go",
        "package main\n"
        "func Exported() int { return 1 }\n"        # capitalised -> public -> reachable
        "func unexportedDead() int { return 2 }\n"  # lower-case, unused -> dead
        "func main() { _ = caller() }\nfunc caller() int { return 0 }\n",
    )
    assert "Exported" not in dead
    assert "unexportedDead" in dead


def test_java_public_is_reachable():
    dead = _dead_names(
        "A.java",
        "class A {\n"
        "  public int exported() { return 1; }\n"   # public -> reachable
        "  private int privateDead() { return 2; }\n"  # private, unused -> dead
        "}\n",
    )
    assert "exported" not in dead
    assert "privateDead" in dead


def test_unmodelled_language_is_silent():
    # Rust visibility is not yet captured -> NOT opted in -> never claims dead,
    # even for an obviously-unused private fn. Conservative safety, not a false +.
    dead = _dead_names(
        "a.rs",
        "pub fn exported_api() -> i32 { 1 }\n"
        "fn private_unused() -> i32 { 2 }\n",
    )
    assert dead == set()


def test_csharp_is_silent_until_visibility_captured():
    dead = _dead_names(
        "A.cs",
        "class A {\n  public int Exported() { return 1; }\n"
        "  private int PrivateUnused() { return 2; }\n}\n",
    )
    assert dead == set()  # not opted in -> silent (public must never be flagged)
