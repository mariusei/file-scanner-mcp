"""Warm corpus cache: transparent per-file memoization of CodeMap.analyze().

The cache must be invisible in the output (same result, just faster) and only
re-extract files whose stat-fingerprint changed.
"""
from scantool.code_map import CodeMap, clear_corpus_cache, _EXTRACT_CACHE


def _result_tuple(r):
    """A content fingerprint of a CodeMapResult for equality comparison."""
    return (
        len(r.definitions),
        len(r.calls),
        sorted(r.clusters),
        sorted((n.name, round(n.in_weight, 6), round(n.out_weight, 6))
               for n in r.call_graph.values()),
        [f.name for f in r.hot_functions],
    )


def _write_repo(root):
    (root / "a.py").write_text("def helper():\n    return 1\n")
    (root / "b.py").write_text(
        "from a import helper\n\ndef use():\n    return helper()\n")


def test_cache_is_transparent(tmp_path):
    """Cached output == uncached output, and a warm re-run is identical too."""
    _write_repo(tmp_path)
    clear_corpus_cache()
    cold = _result_tuple(CodeMap(str(tmp_path), use_cache=False).analyze())
    clear_corpus_cache()
    warm_build = _result_tuple(CodeMap(str(tmp_path)).analyze())  # populates cache
    warm_hit = _result_tuple(CodeMap(str(tmp_path)).analyze())    # reuses cache
    assert cold == warm_build == warm_hit


def test_only_changed_file_re_extracts(tmp_path):
    """An unchanged file is served from cache (same object); only the edited file
    is re-extracted; the warm result still matches a fresh uncached analyze."""
    _write_repo(tmp_path)
    clear_corpus_cache()
    CodeMap(str(tmp_path)).analyze()
    cache = next(iter(_EXTRACT_CACHE.values()))
    a_extraction = cache["a.py"][1]

    # edit b.py — different size guarantees a different fingerprint; a.py untouched
    (tmp_path / "b.py").write_text(
        "from a import helper\n\ndef use():\n    return helper() + 2  # changed\n")
    CodeMap(str(tmp_path)).analyze()

    assert cache["a.py"][1] is a_extraction  # reused, not re-extracted
    assert cache["b.py"][1] is not None      # re-extracted

    # transparency holds on the new state
    clear_corpus_cache()
    cold = _result_tuple(CodeMap(str(tmp_path), use_cache=False).analyze())
    clear_corpus_cache()
    warm = _result_tuple(CodeMap(str(tmp_path)).analyze())
    assert cold == warm


def test_deleted_file_is_pruned(tmp_path):
    _write_repo(tmp_path)
    (tmp_path / "c.py").write_text("def gone():\n    return 0\n")
    clear_corpus_cache()
    CodeMap(str(tmp_path)).analyze()
    cache = next(iter(_EXTRACT_CACHE.values()))
    assert "c.py" in cache

    (tmp_path / "c.py").unlink()
    CodeMap(str(tmp_path)).analyze()
    assert "c.py" not in cache


def test_clear_corpus_cache(tmp_path):
    _write_repo(tmp_path)
    clear_corpus_cache()
    CodeMap(str(tmp_path)).analyze()
    assert _EXTRACT_CACHE
    clear_corpus_cache()
    assert not _EXTRACT_CACHE
