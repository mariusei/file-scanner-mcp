# M2c sluttmeldinger — arm A, rep 2

## m2c-pytest-7373-a-r2 (27789 tokens, 6 kall)
ANSWER: In pytest's `cached_eval()` function, the cache key is the `expr` string alone (accessed via `evalcache[expr]`), stored in a dictionary keyed by `evalcache_key = StoreKey[Dict[str, Any]]()` in `config._store`. The parameter `d` (containing globals from `_getglobals()` including pytest, sys, item.obj.__globals__, and config.ini values) is NOT part of the cache key, meaning different evaluation contexts can incorrectly return cached results computed with different variable bindings.
(Notat: mellomtekst listet _getglobals-innholdet upresist — "pytest module, config.getini()" er feil; sluttlinjen nevner item.obj.__globals__ korrekt.)

## m2c-pytest-5221-a-r2 (29892 tokens, 6 kall)
ANSWER: At default verbosity (verbose <= 0), fixtures with names starting with underscore are skipped. When a fixture has no docstring, pytest prints "    {location}: no docstring available" in red color.

## m2c-requests-1963-a-r2 (29772 tokens, 2 kall)
ANSWER: The request object copied at the top of each loop iteration is `req` (via `prepared_request = req.copy()`). The three (status code, method) combinations that rewrite the HTTP method to GET are: (303 See Other, non-HEAD), (302 Found, non-HEAD), and (301 Moved Permanently, POST).

## m2c-requests-2674-a-r2 (26619 tokens, 5 kall)
ANSWER: HTTPAdapter.send catches these low-level exceptions: (1) `ProtocolError` and `socket.error` → re-raised as `ConnectionError`; (2) `MaxRetryError` → re-raised as `ConnectTimeout` (if reason is ConnectTimeoutError), `RetryError` (if reason is ResponseError), or `ConnectionError` (otherwise); (3) `_ProxyError` → re-raised as `ProxyError`; (4) `_SSLError` and `_HTTPError` → re-raised as `SSLError` (if SSLError), `ReadTimeout` (if ReadTimeoutError), or re-raised unchanged.
(Notat: agenten sa selv den hadde brukt opp kallene men svarte fra scan-skjelettet.)

## m2c-flask-4045-a-r2 (26135 tokens, 3 kall)
ANSWER: Blueprint.add_url_rule asserts that (1) if endpoint is provided, it must not contain dots, and (2) if view_func is provided and has a __name__ attribute, the function name must not contain dots. The actual registration is deferred through the `self.record(lambda s: s.add_url_rule(...))` call.

## m2c-flask-5063-a-r2 (29114 tokens, 5 kall)
ANSWER: The `flask routes` command prints three columns: "Endpoint", "Methods", and "Rule". By default, it hides the "HEAD" and "OPTIONS" HTTP methods (shown only with --all-methods flag). The --sort option accepts four values: "endpoint" (default), "methods", "rule", and "match".

## m2c-sg-ttl-a-r2 (25637 tokens, 3 kall)
ANSWER: get_tile_cache_ttl returns: grid → None (never expires), dataset → 2592000 (30 days), model → 2592000 (30 days), indicator → 1800 (30 minutes), default → 300 (5 minutes).

## m2c-sg-jwt-a-r2 (25732 tokens, 5 kall)
ANSWER: When `expires_delta` is NOT provided, the expiry timestamp is computed as: `current_time_in_seconds + (ACCESS_TOKEN_EXPIRE_MINUTES * 60)`, where `ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24` (24 hours). The token payload includes two claims: `"exp"` and `"iat"` (both Unix timestamps), plus all claims from the `data` dictionary.
