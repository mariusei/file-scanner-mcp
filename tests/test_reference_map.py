"""Directed reference mapping: a producer referenced nowhere is an orphan; a
referenced one is reached."""
from scantool.reference_map import run, FASTAPI_ROUTE, JINJA_TEMPLATE


def test_fastapi_orphan_vs_reached(tmp_path):
    (tmp_path / "app.py").write_text(
        '@router.get("/alive")\n'
        'def alive():\n    return 1\n\n'
        '@router.get("/konto-hint")\n'
        'def hent_konto_hint():\n    return 2\n'
    )
    tpl = tmp_path / "templates"
    tpl.mkdir()
    (tpl / "page.html").write_text('<a href="/alive">go</a>')  # references /alive only

    _reached, orphan, _unresolvable = run(tmp_path, FASTAPI_ROUTE)
    keys = {p.key for p in orphan}
    assert "/konto-hint" in keys      # referenced nowhere
    assert "/alive" not in keys       # referenced by the template -> reached


def test_jinja_orphan_vs_reached(tmp_path):
    tpl = tmp_path / "templates"
    tpl.mkdir()
    (tpl / "used.html").write_text("<p>used</p>")
    (tpl / "dead.html").write_text("<p>dead</p>")
    (tmp_path / "views.py").write_text('render("used.html")\n')

    _reached, orphan, _unresolvable = run(tmp_path, JINJA_TEMPLATE)
    keys = {p.key for p in orphan}
    assert "dead.html" in keys
    assert "used.html" not in keys
