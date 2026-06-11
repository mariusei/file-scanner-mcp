# M2c sluttmeldinger — arm B, rep 1

## m2c-pytest-7373-b-r1 (27727 tokens, 6 kall)
ANSWER: The cache key in cached_eval is ONLY the expression string (`expr`). The cache is stored in `config._store` via a `StoreKey[Dict[str, object]]` object named `evalcache_key`. The `d` parameter passed to cached_eval (which contains config options, sys.modules variables, and test item globals from `_getglobals()`) is NOT part of the cache key, meaning different evaluation contexts can incorrectly return cached results meant for different global variable contexts.
(Notat: mellomtekst påsto d inneholder "config.option.__dict__/sys.modules" — upresist, men sluttlinjen nevner _getglobals/test item globals.)

## m2c-pytest-5221-b-r1 (29433 tokens, 6 kall)
ANSWER: At default verbosity, fixtures starting with underscore (`argname[0] == "_"`) are skipped. When a fixture has no docstring, the string `"    {location}: no docstring available"` is printed in RED color.

## m2c-requests-1963-b-r1 (29349 tokens, 4 kall)
ANSWER: The request object `req` is copied at line 91 with `prepared_request = req.copy()`. The three (status code, method) combinations that rewrite to GET are: (303, non-HEAD), (302, non-HEAD), and (301, POST).

## m2c-requests-2674-b-r1 (29130 tokens, 5 kall)
ANSWER: HTTPAdapter.send catches six low-level exception types and re-raises them as requests exceptions: (1) socket.error → ConnectionError; (2) ProtocolError (urllib3) → ConnectionError; (3) MaxRetryError (urllib3) → ConnectTimeout (if reason is ConnectTimeoutError), RetryError (if reason is ResponseError), or ConnectionError (default); (4) ProxyError (urllib3, aliased _ProxyError) → ProxyError; (5) SSLError (urllib3, aliased _SSLError) → SSLError; (6) HTTPError (urllib3, aliased _HTTPError) → ReadTimeout (if ReadTimeoutError) or re-raised as-is (otherwise).

## m2c-flask-4045-b-r1 (28908 tokens, 5 kall)
ANSWER: Blueprint.add_url_rule asserts that neither the endpoint nor the view function name contain dots ("." characters) — `assert "." not in endpoint` and `assert "." not in view_func.__name__`. The actual registration is deferred through `self.record(lambda s: s.add_url_rule(rule, endpoint, view_func, **options))`, which stores the registration call to be executed later when the blueprint is registered with the Flask app.

## m2c-flask-5063-b-r1 (28976 tokens, 4 kall)
ANSWER: The routes_command prints three columns: Endpoint, Methods, and Rule. By default, HEAD and OPTIONS HTTP methods are hidden (shown only when --all-methods flag is used). The --sort option accepts four values: endpoint (default), methods, rule, and match.

*(The two sg episodes are redacted: the sg repo is a private production backend; their final messages are held privately together with the raw sg logs. See ../M2C.md.)*
