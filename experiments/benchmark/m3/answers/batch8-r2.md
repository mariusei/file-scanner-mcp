# M3 answers — batch 8 (r2): N1/N2/N3 × A/B (full final messages, verbatim)

## m3-N1-a-r2 [tool_uses=5 tokens=35982]
(fulltekst i episodens sluttmelding; ANSWER-linje:)
ANSWER: /tmp/m3/pallets__flask-4045/src/flask/blueprints.py :: Blueprint.add_url_rule (lines 353-369) :: Endpoint and view_func.__name__ must not contain dots (assertions lines 364 and 367); deferred registration via self.record(lambda s: s.add_url_rule(...)) calling BlueprintSetupState.add_url_rule
Body noted: assert "." not in endpoint ("Blueprint endpoints should not contain dots"); assert "." not in view_func.__name__; self.record(lambda s: s.add_url_rule(rule, endpoint, view_func, **options)).

## m3-N1-b-r2 [tool_uses=4 tokens=41330]
ANSWER: /tmp/m3/pallets__flask-4045/src/flask/blueprints.py :: Blueprint.add_url_rule :: Asserts that endpoint and view_func.__name__ must not contain dots (lines 364, 367); defers registration via self.record() lambda that calls BlueprintSetupState.add_url_rule (line 369)
Body noted: both assertion messages verbatim; BlueprintSetupState.add_url_rule → self.app.add_url_rule (line 99); name-prefix rationale.

## m3-N2-a-r2 [tool_uses=3 tokens=34608]
ANSWER: /tmp/m3/psf__requests-2674/requests/adapters.py :: HTTPAdapter.send (lines 324-435) :: socket.error→ConnectionError; ProtocolError→ConnectionError; MaxRetryError(ConnectTimeoutError)→ConnectTimeout; MaxRetryError(ResponseError)→RetryError; MaxRetryError→ConnectionError; _ProxyError→ProxyError; _SSLError→SSLError; ReadTimeoutError→ReadTimeout; _HTTPError→re-raised
Body: full mapping enumerated with line numbers.

## m3-N2-b-r2 [tool_uses=6 tokens=38238]
ANSWER: /tmp/m3/psf__requests-2674/requests/adapters.py :: HTTPAdapter.send() :: Socket and urllib3 low-level exceptions (ProtocolError, MaxRetryError, _ProxyError, _SSLError, _HTTPError, socket.error) are caught in separate except blocks and re-raised as requests-specific exceptions (ConnectionError, ConnectTimeout, RetryError, ProxyError, SSLError, ReadTimeout) with request context attached.
Body: full mapping enumerated (9 entries incl. MaxRetryError reason-branching and _HTTPError re-raise).

## m3-N3-a-r2 [tool_uses=5 tokens=32703]
ANSWER: /tmp/m3/pytest-dev__pytest-7373/src/_pytest/mark/evaluate.py :: cached_eval (line 21) and MarkEvaluator._istrue (line 78) :: Cache key is `expr` string only; stored in `config._store[evalcache_key]`; missing from key: the dictionary `d` from `_getglobals()`, especially `item.obj.__globals__` which varies per test item
Body: evalcache[expr]; StoreKey; d not in key → stale reuse across items.

## m3-N3-b-r2 [tool_uses=5 tokens=33811]
ANSWER: /tmp/m3/pytest-dev__pytest-7373/src/_pytest/mark/evaluate.py :: cached_eval (line 21-31) and MarkEvaluator._istrue (line 82-115) :: Cache key is expr string only; stored in config._store[evalcache_key]; globals dict (d parameter affecting result) is NOT in key, causing cross-test cache collisions when same expression is used with different module contexts.
Body: full mechanism incl. os/sys/platform/config + item.obj.__globals__.
