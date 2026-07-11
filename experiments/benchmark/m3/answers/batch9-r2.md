# M3 answers — batch 9 (r2): N4/N5 × A/B (ANSWER lines, bodies consistent)

## m3-N4-a-r2 [tool_uses=4 tokens=34276]
ANSWER: /tmp/m3/psf__requests-1963/requests/sessions.py :: SessionRedirectMixin.resolve_redirects :: Request object copied: `req` (line 91: `prepared_request = req.copy()`). Three (status code, method) combinations rewriting to GET: (1) 303 (see_other) with method != HEAD, (2) 302 (found) with method != HEAD, (3) 301 (moved) with method POST.

## m3-N4-b-r2 [tool_uses=4 tokens=38425]
ANSWER: /tmp/m3/psf__requests-1963/requests/sessions.py :: SessionRedirectMixin.resolve_redirects (lines 84-184) :: req object copied at line 91; three rewrites: (303, non-HEAD→GET), (302, non-HEAD→GET), (301, POST→GET)

## m3-N5-a-r2 [tool_uses=4 tokens=38650]
ANSWER: /tmp/m3/pallets__flask-4045/src/flask/config.py :: Config.from_envvar (lines 76-98) :: When environment variable is NOT set: returns False (silent=True) or raises RuntimeError (silent=False). When set: delegates to self.from_pyfile(rv, silent=silent).

## m3-N5-b-r2 [tool_uses=4 tokens=33069]
ANSWER: /tmp/m3/pallets__flask-4045/src/flask/config.py :: Config.from_envvar :: Returns False (silent=True) or raises RuntimeError (silent=False) when envvar not set; delegates to from_pyfile(rv, silent=silent) when set
