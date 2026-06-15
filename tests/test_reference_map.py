"""Directed reference mapping: a producer referenced nowhere is an orphan; a
referenced one is reached."""
from scantool.reference_map import run, HTTP_ROUTE, JINJA_TEMPLATE


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

    _reached, orphan, _unresolvable = run(tmp_path, HTTP_ROUTE)
    keys = {p.key for p in orphan}
    assert "/konto-hint" in keys      # referenced nowhere
    assert "/alive" not in keys       # referenced by the template -> reached


def test_http_route_cross_framework_cross_language(tmp_path):
    # Routes in NestJS (TS) and Spring (Java); the consumer is a JS/HTML frontend.
    # The handler↔URL binding and the URL reference live in DIFFERENT languages —
    # the call graph cannot connect them; the directed reference map does.
    (tmp_path / "nest.ts").write_text(
        'class C {\n'
        '  @Get("/profile") profile() {}\n'        # referenced by fetch -> reached
        '  @Get("/forgotten-nest") gone() {}\n'    # referenced nowhere -> orphan
        '}\n'
    )
    (tmp_path / "Spring.java").write_text(
        'class C {\n'
        '  @GetMapping("/orders") public void orders() {}\n'         # reached
        '  @GetMapping("/forgotten-spring") public void g() {}\n'    # orphan
        '}\n'
    )
    (tmp_path / "front.html").write_text(
        '<a href="/profile">p</a><script>axios.get("/orders");</script>'
    )

    _reached, orphan, _unresolvable = run(tmp_path, HTTP_ROUTE)
    keys = {p.key for p in orphan}
    assert "/forgotten-nest" in keys      # NestJS route no frontend hits
    assert "/forgotten-spring" in keys    # Spring route no frontend hits
    assert "/profile" not in keys         # reached cross-language (TS route, HTML href)
    assert "/orders" not in keys          # reached cross-language (Java route, JS axios)


def test_http_route_imperative_registration(tmp_path):
    # The dominant JS style (Express/Hono/Fastify/Deno): no decorator, the handler is
    # an inline closure and the route PATH is the producer. Consumer is a Swift app.
    # Also locks the external-endpoint guard (well-known/assets are never orphans).
    (tmp_path / "server.ts").write_text(
        "nonceRouter.post('/nonce', (c) => c.json({}));\n"            # reached by Swift
        "metaRouter.get('/credentials/email/v1', (c) => c.json({}));\n"  # reached by Swift
        "adminRouter.get('/admin/forgotten-panel', (c) => c.json({}));\n"  # orphan
        "issuerRouter.get('/.well-known/jwks.json', (c) => c.json({}));\n"  # external -> not orphan
        "store.get(nonce);\n"                                         # NOT a route (no leading slash)
    )
    (tmp_path / "Wallet.swift").write_text(
        'let a = URL(string: "https://id.example/nonce")!\n'
        'let vct = "https://id.example/credentials/email/v1"\n'
    )

    _reached, orphan, _unresolvable = run(tmp_path, HTTP_ROUTE)
    keys = {p.key for p in orphan}
    assert "/admin/forgotten-panel" in keys      # imperative route no consumer hits
    assert "/nonce" not in keys                  # reached cross-language (TS route, Swift URL)
    assert "/credentials/email/v1" not in keys   # reached cross-language
    assert "/.well-known/jwks.json" not in keys  # external endpoint, never an orphan


def test_http_route_no_false_producer(tmp_path):
    # A non-route decorator must never become a route producer (the false-producer
    # trap): @cache.get("k") has no leading slash; @property is not a verb.
    (tmp_path / "app.py").write_text(
        '@app.get("/users")\ndef users(): return 1\n'
        '@cache.get("memo_key_xyz")\ndef cached(): return 2\n'
    )
    (tmp_path / "front.ts").write_text('fetch("/users");')

    _reached, orphan, _unresolvable = run(tmp_path, HTTP_ROUTE)
    all_keys = {p.key for p in orphan} | {p.key for p, _ in _reached}
    assert "memo_key_xyz" not in all_keys   # @cache.get is not a route producer
    assert not orphan                        # /users is referenced -> no orphan


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
