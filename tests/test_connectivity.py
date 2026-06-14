"""The self-levelling connectivity tail: silent when clean, fires on dead/orphan,
served from a warmed corpus state (background-refreshed), never raises."""
from scantool.code_map import clear_corpus_cache
from scantool.connectivity import (
    clear_connectivity_cache,
    connectivity_tail,
    warm,
)


def _fresh():
    clear_corpus_cache()
    clear_connectivity_cache()


def test_tail_silent_on_clean_code(tmp_path):
    (tmp_path / "core.py").write_text("def used():\n    return 1\n")
    (tmp_path / "main.py").write_text(
        "from core import used\n\ndef main():\n    return used()\n")
    _fresh()
    warm(str(tmp_path))
    assert connectivity_tail(str(tmp_path), str(tmp_path / "core.py")) == ""


def test_tail_flags_dead_function(tmp_path):
    (tmp_path / "core.py").write_text(
        "def used():\n    return 1\n\ndef orphaned_helper():\n    return 2\n")
    (tmp_path / "main.py").write_text(
        "from core import used\n\ndef main():\n    return used()\n")
    _fresh()
    warm(str(tmp_path))
    tail = connectivity_tail(str(tmp_path), str(tmp_path / "core.py"))
    assert "candidate-dead" in tail
    assert "orphaned_helper" in tail
    # `used` has a caller — it must not be flagged dead
    assert "used" not in tail.split("candidate-dead", 1)[1]


def test_tail_flags_orphan_route(tmp_path):
    (tmp_path / "app.py").write_text(
        '@router.get("/konto-hint")\n'
        'def hent_konto_hint():\n    return 1\n\n'
        'def main():\n    return hent_konto_hint()\n'  # gives the call graph an edge
    )
    _fresh()
    warm(str(tmp_path))
    tail = connectivity_tail(str(tmp_path), str(tmp_path / "app.py"))
    assert "orphan" in tail
    assert "/konto-hint" in tail


def test_serve_stale_first_call_is_silent(tmp_path):
    # before any warm, the tail is "" (a background refresh is kicked off); the
    # scan never blocks on the corpus build.
    (tmp_path / "core.py").write_text(
        "def used():\n    return 1\n\ndef gone():\n    return 2\n")
    (tmp_path / "main.py").write_text(
        "from core import used\n\ndef main():\n    return used()\n")
    _fresh()
    assert connectivity_tail(str(tmp_path), str(tmp_path / "core.py")) == ""


def test_dispatch_named_not_flagged_dead(tmp_path):
    # visit_* is invoked by name (getattr/visitor) — invisible to the call graph,
    # so zero-inbound there is reachable, not dead. A plain dead fn still fires.
    (tmp_path / "v.py").write_text(
        "class V:\n"
        "    def visit_Unused(self, node):\n        return node\n\n"
        "def just_dead():\n    return 1\n")
    (tmp_path / "m.py").write_text(
        "from v import V\n\ndef main():\n    return V()\n")
    _fresh()
    warm(str(tmp_path))
    tail = connectivity_tail(str(tmp_path), str(tmp_path / "v.py"))
    assert "just_dead" in tail          # plain dead is flagged
    assert "visit_Unused" not in tail   # dispatch-named is skipped


def test_tail_never_raises_on_bad_input(tmp_path):
    missing = tmp_path / "nope"
    assert connectivity_tail(str(missing), str(missing / "x.py")) == ""
