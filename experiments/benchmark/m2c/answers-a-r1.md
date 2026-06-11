# M2c sluttmeldinger — arm A, rep 1 (kun ANSWER-linjer + relevante utdrag)

## m2c-pytest-7373-a-r1 (26113 tokens, 4 kall)
ANSWER: The cache key in `cached_eval` is the **expression string alone** (`expr`). The cache is stored in **`config._store`** (a per-config global dictionary indexed by `StoreKey`). The **evaluation dictionary `d`** (containing os, sys, platform, config, and item-specific globals) is NOT part of the cache key, which means the same expression evaluated in different global contexts will incorrectly reuse the first cached result.

## m2c-pytest-5221-a-r1 (30195 tokens, 5 kall)
ANSWER: At default verbosity (verbose <= 0), fixtures whose names start with underscore (`_`) are skipped and not displayed. When a fixture has no docstring, pytest prints `"    <location>: no docstring available"` in red color (using `tw.line(..., red=True)`), where `<location>` is the file path and line number of the fixture definition.

## m2c-requests-1963-a-r1 (25693 tokens, 2 kall)
ANSWER: The request object copied at the top of each loop iteration is `req.copy()` (stored in `prepared_request`). The three (status code, method) combinations that rewrite HTTP method to GET are: (303 See Other, non-HEAD), (302 Found, non-HEAD), and (301 Moved Permanently, POST).

## m2c-requests-2674-a-r1 (29193 tokens, 4 kall)
ANSWER (hele oppsummeringen): ProtocolError → ConnectionError; socket.error → ConnectionError; MaxRetryError/ConnectTimeoutError → ConnectTimeout; MaxRetryError/ResponseError → RetryError; MaxRetryError ellers → ConnectionError; _ProxyError → ProxyError; _SSLError → SSLError; ReadTimeoutError → ReadTimeout; _HTTPError ellers → re-raised as-is.

## m2c-flask-4045-a-r1 (30297 tokens, 4 kall)
ANSWER: Blueprint.add_url_rule asserts: (1) `assert "." not in endpoint`, (2) `assert "." not in view_func.__name__`. Registration deferred through `self.record()` wrapping lambda calling `s.add_url_rule(...)` on BlueprintSetupState.

## m2c-flask-5063-a-r1 (31141 tokens, 6 kall)
ANSWER: The routes_command prints three columns: Endpoint, Methods, and Rule. By default, HEAD and OPTIONS HTTP methods are hidden (only shown with --all-methods flag). The --sort option accepts four values: endpoint, methods, rule, and match.

*(The two sg episodes are redacted: the sg repo is a private production backend; their final messages are held privately together with the raw sg logs. See ../M2C.md.)*
