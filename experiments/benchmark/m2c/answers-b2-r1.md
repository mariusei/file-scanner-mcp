# M2c-v2 sluttmeldinger — arm B2 (ny styringstekst), rep 1

## m2c-pytest-7373-b2-r1 (27491 tokens, 6 kall)
ANSWER: The cache key in `cached_eval()` is **only the expression string (`expr`)**. The cache is stored in `config._store[evalcache_key]` which is a `Dict[str, Any]` where keys are expression strings. Critically, the evaluation dictionary `d` (containing globals like `os`, `sys`, `platform`, `config`, and `item.obj.__globals__`) is **NOT part of the cache key**, meaning the same expression will return a cached result regardless of changes to the evaluation context.

## m2c-pytest-5221-b2-r1 (24536 tokens, 6 kall — FEILET)
Agenten fant ikke funksjonen (påsto feilaktig at _showfixtures_main ligger i
src/_pytest/fixtures.py — den ligger i python.py), brukte opp kallene og
svarte vagt fra forkunnskap:
ANSWER: In pytest's `_showfixtures_main` implementation, fixtures are typically displayed with verbosity controls where fixture scope and other metadata may be skipped at default verbosity levels. When a fixture has no docstring, pytest prints the fixture name and its scope information, typically in a plain format without additional colored output [...] The exact behavior requires examining the `_showfixtures_main` function in `src/_pytest/fixtures.py` [...]

## m2c-requests-1963-b2-r1 (30591 tokens, 4 kall)
ANSWER: The `req` object (the original request parameter) is copied at the top of each loop iteration at line 91 via `prepared_request = req.copy()`. The three (status code, method) combinations that rewrite the HTTP method to GET are: (303, any except HEAD), (302, any except HEAD), and (301, POST).

## m2c-requests-2674-b2-r1 (31409 tokens, 6 kall)
ANSWER: HTTPAdapter.send catches: (1) ProtocolError and socket.error → re-raised as ConnectionError; (2) MaxRetryError with ConnectTimeoutError reason → ConnectTimeout, with ResponseError reason → RetryError, otherwise → ConnectionError; (3) _ProxyError → ProxyError; (4) _SSLError → SSLError, _HTTPError with ReadTimeoutError → ReadTimeout, otherwise re-raised.

## m2c-flask-4045-b2-r1 (28841 tokens, 4 kall)
ANSWER: Blueprint.add_url_rule asserts that (1) if endpoint is provided, it must not contain dots ("." not in endpoint), and (2) if view_func is provided and has a __name__ attribute, it must not contain dots ("." not in view_func.__name__). The actual registration is deferred through the self.record() call, which registers a lambda function that will call s.add_url_rule() on the BlueprintSetupState object when the blueprint is registered with the app.

## m2c-flask-5063-b2-r1 (26128 tokens, 3 kall)
ANSWER: The `flask routes` command prints three columns: **Endpoint**, **Methods**, and **Rule**. By default, the **HEAD** and **OPTIONS** HTTP methods are hidden (only shown with `--all-methods` flag). The `--sort` option accepts four values: **endpoint** (default), **methods**, **rule**, and **match**.

*(The two sg episodes are redacted: the sg repo is a private production backend; their final messages are held privately together with the raw sg logs. See ../M2C.md.)*
