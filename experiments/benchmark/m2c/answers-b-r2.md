# M2c sluttmeldinger — arm B, rep 2

## m2c-pytest-7373-b-r2 (29090 tokens, 9 kall — AVVIK: >6 kall)
ANSWER: In cached_eval, the cache key is the expression string (`expr`) alone. The cache is stored as a dictionary in `config._store` (accessed via `evalcache_key`). Data NOT part of the key but affecting evaluation: the dictionary `d` containing all variables (os, sys, platform, config, and item.obj.__globals__) - different variable contexts with the same expression string return the same cached result. Additionally, MarkEvaluator._istrue caches results per instance via a `self.result` attribute.

## m2c-pytest-5221-b-r2 (25826 tokens, 8 kall — AVVIK: >6 kall)
ANSWER: At default verbosity (0), fixtures starting with underscore (`_`) are skipped. When a fixture has no docstring, pytest prints "    <location>: no docstring available" in red color.

## m2c-requests-1963-b-r2 (29773 tokens, 5 kall)
ANSWER: The request object copied at the top of each loop iteration is `req` (line 91: `prepared_request = req.copy()`). The three (status code, method) combinations that rewrite HTTP method to GET are: (1) 303 See Other with non-HEAD method, (2) 302 Found with non-HEAD method, (3) 301 Moved Permanently with POST method.

## m2c-requests-2674-b-r2 (30591 tokens, 6 kall)
ANSWER: In HTTPAdapter.send, the caught low-level (urllib3/socket) exceptions and their re-raised requests exceptions are: (1) `ProtocolError` and `socket.error` → `ConnectionError`; (2) `MaxRetryError` (with `ConnectTimeoutError` reason) → `ConnectTimeout`, (with `ResponseError` reason) → `RetryError`, (with other reasons) → `ConnectionError`; (3) `_ProxyError` → `ProxyError`; (4) `_SSLError` → `SSLError`, `ReadTimeoutError` → `ReadTimeout`, others → re-raised as-is.

## m2c-flask-4045-b-r2 (30873 tokens, 5 kall)
(Brukte focusread eksplisitt — refererte til «focusread output showing lines 353-369».)
ANSWER: Blueprint.add_url_rule asserts that (1) the endpoint parameter does not contain dots ("Blueprint endpoints should not contain dots"), and (2) if view_func is provided and has a __name__ attribute, that the view function name does not contain dots ("Blueprint view function name should not contain dots"). The actual registration is deferred through the `self.record(lambda s: s.add_url_rule(...))` call, which appends a lambda to the blueprint's deferred_functions list.

## m2c-flask-5063-b-r2 (30041 tokens, 6 kall)
ANSWER: The routes_command prints three columns: Endpoint, Methods, and Rule. By default, HEAD and OPTIONS HTTP methods are hidden (filtered out). The --sort option accepts four values: endpoint, methods, rule, and match.

## m2c-sg-ttl-b-r2 (25100 tokens, 3 kall)
ANSWER: `get_tile_cache_ttl` returns: grid = None (never expires), dataset = 2592000 seconds (30 days), model = 2592000 seconds (30 days), indicator = 1800 seconds (30 minutes), default case = 300 seconds (5 minutes).

## m2c-sg-jwt-b-r2 (24687 tokens, 5 kall)
(Notat: ett focusread-kall feilet på sti — agenten svarte fra searchname-output.)
ANSWER: When expires_delta is NOT provided, the expiry timestamp is computed as: `now_timestamp + ACCESS_TOKEN_EXPIRE_MINUTES * 60` (current Unix timestamp plus a fixed duration in seconds). Two claims are added to the payload: 'exp' (expiry timestamp) and 'iat' (issued-at timestamp).
