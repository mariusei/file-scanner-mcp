# M2c-v2 sluttmeldinger — arm B2 (ny styringstekst), rep 2

## m2c-pytest-7373-b2-r2 (25562 tokens, 5 kall)
ANSWER: In `cached_eval()`, the cache key is the expression string (`expr`) alone. The cache is stored in `config._store[evalcache_key]` (a per-config global dictionary). Critically, the evaluation context dictionary `d` (containing variables, os, sys, platform, config, and item object globals) that directly affects the result is NOT part of the cache key—only the expression string is cached, so different evaluation contexts for the same expression will incorrectly reuse cached results.

## m2c-pytest-5221-b2-r2 (27485 tokens, 5 kall)
ANSWER: At default verbosity, fixtures whose names start with underscore (`_`) are skipped. When a fixture has no docstring, pytest prints `    <file_location>: no docstring available` in red color (`red=True`), where `<file_location>` is the fixture function's location.

## m2c-requests-1963-b2-r2 (26345 tokens, 2 kall)
ANSWER: The request object copied at the top of each loop iteration is `req`. The three (status code, method) combinations that rewrite the HTTP method to GET are: (303, non-HEAD), (302, non-HEAD), and (301, POST).

## m2c-requests-2674-b2-r2 (29006 tokens, 5 kall)
ANSWER: HTTPAdapter.send catches the following low-level exceptions and re-raises them as requests exceptions: (1) `ProtocolError` and `socket.error` → `ConnectionError`; (2) `MaxRetryError` with `ConnectTimeoutError` reason → `ConnectTimeout`, with `ResponseError` reason → `RetryError`, otherwise → `ConnectionError`; (3) `_ProxyError` → `ProxyError`; (4) `_SSLError` → `SSLError`, `ReadTimeoutError` → `ReadTimeout`, others → re-raised as-is.

## m2c-flask-4045-b2-r2 (26625 tokens, 4 kall)
(Refererte eksplisitt til «the focusread output».)
ANSWER: Two assertions check that neither the endpoint nor the view_func.__name__ contain dots: `assert "." not in endpoint, "Blueprint endpoints should not contain dots"` and `assert "." not in view_func.__name__, "Blueprint view function name should not contain dots"`. The actual registration is deferred via `self.record(lambda s: s.add_url_rule(rule, endpoint, view_func, **options))`, executed later when the blueprint is registered with an app.

## m2c-flask-5063-b2-r2 (26155 tokens, 3 kall)
ANSWER: The `flask routes` command prints three columns: Endpoint, Methods, and Rule. By default, HEAD and OPTIONS HTTP methods are hidden (shown only with `--all-methods` flag). The `--sort` option accepts four values: endpoint (default), methods, rule, and match.

## m2c-sg-ttl-b2-r2 (24912 tokens, 2 kall)
ANSWER: get_tile_cache_ttl returns: grid → None (never expires), dataset → 2592000 (30 days), model → 2592000 (30 days), indicator → 1800 (30 minutes), default → 300 (5 minutes).

## m2c-sg-jwt-b2-r2 (25285 tokens, 4 kall)
ANSWER: When `expires_delta` is NOT provided, the expiry timestamp is computed as: `now_timestamp + (ACCESS_TOKEN_EXPIRE_MINUTES * 60)`, where `now_timestamp = int(time.time())` and `ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 = 1440`. The claims added are: "exp" and "iat" (Unix epoch seconds), plus claims from the original `data` dictionary.
