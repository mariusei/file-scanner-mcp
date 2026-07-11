# M3 answers — batch 4 (r1): N2/N3/N4 × A/B (full final messages, verbatim)

## m3-N2-a-r1 [tool_uses=4 tokens=32668]
Based on my exploration of the HTTPAdapter.send method, I can identify the exception mapping:

**Exception Mapping in HTTPAdapter.send:**

1. `socket.error` + `ProtocolError` (urllib3) → `ConnectionError` (requests)
2. `MaxRetryError` with reason `ConnectTimeoutError` → `ConnectTimeout` (requests)
3. `MaxRetryError` with reason `ResponseError` → `RetryError` (requests)
4. `MaxRetryError` (other reasons) → `ConnectionError` (requests)
5. `_ProxyError` (urllib3.exceptions.ProxyError) → `ProxyError` (requests)
6. `_SSLError` (urllib3.exceptions.SSLError) → `SSLError` (requests)
7. `_HTTPError` if it's `ReadTimeoutError` → `ReadTimeout` (requests)
8. `_HTTPError` (other types) → re-raised as-is

ANSWER: /tmp/m3/psf__requests-2674/requests/adapters.py :: HTTPAdapter.send (lines 324-429) :: socket.error and urllib3 exceptions (ProtocolError, MaxRetryError, ProxyError, SSLError, HTTPError) are caught and re-raised as requests exceptions (ConnectionError, ConnectTimeout, RetryError, ProxyError, SSLError, ReadTimeout)

## m3-N2-b-r1 [tool_uses=5 tokens=40086]
Based on my exploration of the HTTPAdapter.send method in requests/adapters.py, I've identified all the exception handling. The method catches low-level urllib3 and socket exceptions and re-raises them as requests exceptions.

**Low-level exceptions caught and re-raised:**

1. **socket.error** (Python socket module) → **ConnectionError** (line 412-413)
2. **ProtocolError** (urllib3) → **ConnectionError** (line 412-413)
3. **MaxRetryError** (urllib3):
   - When reason is **ConnectTimeoutError** → **ConnectTimeout** (line 416-417)
   - When reason is **ResponseError** → **RetryError** (line 419-420)
   - Default case → **ConnectionError** (line 422)
4. **ProxyError** (urllib3, aliased as _ProxyError) → **ProxyError** (line 424-425)
5. **SSLError** (urllib3, aliased as _SSLError) → **SSLError** (line 428-429)
6. **ReadTimeoutError** (urllib3) → **ReadTimeout** (line 430-431)
7. **HTTPError** (urllib3, aliased as _HTTPError, non-ReadTimeout) → re-raised unchanged (line 433)

ANSWER: /tmp/m3/psf__requests-2674/requests/adapters.py :: HTTPAdapter.send (lines 412-433) :: Catches 8 urllib3/socket exception types and re-raises as 6 requests exceptions via nested try-except blocks—socket.error and ProtocolError→ConnectionError; MaxRetryError branching on reason type to ConnectTimeout/RetryError/ConnectionError; ProxyError/SSLError mapped 1:1; ReadTimeoutError→ReadTimeout; HTTPError re-raised.

## m3-N3-a-r1 [tool_uses=4 tokens=33252]
Based on my exploration of the pytest codebase, I have identified the cache mechanism in the skipif/xfail evaluation:

**Cache Key:** Just the `expr` (expression string) - at line 26, `evalcache[expr]` uses only the expression as the key.

**Cache Storage:** The cache is stored in `config._store` (a Config object's internal store) with `evalcache_key` as the dictionary key. Retrieved at line 24-25:
```python
evalcache_key = StoreKey[Dict[str, Any]]()
evalcache = config._store.setdefault(evalcache_key, default)
```

**Non-keyed Data Affecting Results:** The `d` parameter (globals dictionary) passed to `cached_eval` at line 30 in `_istrue()`:
- `cached_eval(self.item.config, expr, d)` at line 101
- `eval(exprcode, d)` at line 30 uses this dictionary for evaluation
- The `d` comes from `_getglobals()` (lines 76-80) which includes `os`, `sys`, `platform`, `config`, and crucially `self.item.obj.__globals__`
- Since `d` is NOT part of the cache key, the same expression cached with one globals dict will return the wrong result if called with different globals

ANSWER: /tmp/m3/pytest-dev__pytest-7373/src/_pytest/mark/evaluate.py :: cached_eval (line 21) and MarkEvaluator._istrue (line 82) :: Cache key is expr string only (line 26: evalcache[expr]); stored in config._store with evalcache_key (lines 17,24-25); the globals dictionary d passed to eval (line 30) is NOT in the key, so different globals for the same expr return stale cached results.

## m3-N3-b-r1 [tool_uses=6 tokens=33317]
Based on my exploration, I can now provide the answer.

**ANSWER:** `/tmp/m3/pytest-dev__pytest-7373/src/_pytest/mark/evaluate.py` :: `cached_eval()` (line 21) and `MarkEvaluator._istrue()` (line 82) :: The cache key is the expression string `expr` alone, stored in `config._store[evalcache_key]` (a per-config dict). The namespace dict `d` (containing test globals and configuration variables) is passed to `eval()` but NOT included in the cache key—meaning different namespaces can return cached results that don't match their actual namespace, creating a correctness bug.

## m3-N4-a-r1 [tool_uses=5 tokens=35543]
Based on my exploration of the code, I can now answer all three parts of the question.

From the `resolve_redirects` method in `/tmp/m3/psf__requests-1963/requests/sessions.py` (lines 84-184):

**Request object copied:** At line 91, `prepared_request = req.copy()` shows that `req` (the parameter passed to the method) is the request object that is copied at the top of each loop iteration.

**Three (status_code, method) combinations that rewrite HTTP method to GET:**

Looking at lines 124-136, the three conditions that trigger a rewrite to GET are:

1. **Line 124-126**: `codes.see_other` (HTTP 303) with `method != 'HEAD'` → method becomes `'GET'`
2. **Line 130-131**: `codes.found` (HTTP 302) with `method != 'HEAD'` → method becomes `'GET'`
3. **Line 135-136**: `codes.moved` (HTTP 301) with `method == 'POST'` → method becomes `'GET'`

The specific combinations are: **(303, POST)**, **(302, POST)**, and **(301, POST)** - though 303 and 302 actually apply to any non-HEAD method.

ANSWER: /tmp/m3/psf__requests-1963/requests/sessions.py :: resolve_redirects :: req is copied at line 91; (303, non-HEAD), (302, non-HEAD), (301, POST) rewrite method to GET at lines 124-126, 130-131, 135-136

## m3-N4-b-r1 [tool_uses=5 tokens=38147]
Based on my exploration of the `Session.resolve_redirects` method in `/tmp/m3/psf__requests-1963/requests/sessions.py`, I can now provide the answer.

Looking at line 91, the request object copied at the top of each loop iteration is **`req`** (accessed via `prepared_request = req.copy()`).

The three (status code, method) combinations that rewrite the HTTP method to GET are found in the code:

1. **Status code 303 (see_other) with method != 'HEAD'** (lines 124-126) → method becomes GET
2. **Status code 302 (found) with method != 'HEAD'** (lines 130-131) → method becomes GET
3. **Status code 301 (moved) with method == 'POST'** (lines 135-136) → method becomes GET

These represent three distinct redirect behaviors documented in the comments with RFC and issue references.

ANSWER: /tmp/m3/psf__requests-1963/requests/sessions.py :: SessionRedirectMixin.resolve_redirects :: Object copied is `req` (via `prepared_request = req.copy()` at line 91); three (status_code, method) combinations rewriting to GET are: (303, non-HEAD), (302, non-HEAD), (301, POST)
