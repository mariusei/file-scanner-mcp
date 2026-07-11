"""M3 knock-out planter. Applies the six class-C plants to the /tmp/m3 checkouts
(clone via ../prepare_swebench.py, then `cp -R /tmp/swb/<inst> /tmp/m3/<inst>`).

Each plant removes the SOLE caller/reference of one function so it becomes
corpus-dead by construction (M3_preregistered.md, class C). Edits are plausible
maintenance edits (inline refactor / block cleanup), asserted to apply exactly
once. Idempotent: a file already carrying the new text is skipped.

Class D needs no plants — both decoys are natural, independently verified:
  D1 requests/cookies.py MockRequest.* — duck-typed for cookielib.CookieJar
     (the class docstring states the required interface)
  D2 flask examples/tutorial blog routes /update, /delete — referenced from
     templates via url_for('blog.update'/'blog.delete'); orphan flag is a
     resolver miss

Usage: uv run python experiments/benchmark/m3/plant.py
"""
from pathlib import Path

ROOT = Path("/tmp/m3")

# (repo, relpath, old, new, planted-dead "file:qual")
PLANTS = [
    # C1: helper for CLI-run explanation orphaned by a block cleanup
    ("pallets__flask-4045", "src/flask/app.py",
     '''        if os.environ.get("FLASK_RUN_FROM_CLI") == "true":
            from .debughelpers import explain_ignored_app_run

            explain_ignored_app_run()
            return
''',
     '''        if os.environ.get("FLASK_RUN_FROM_CLI") == "true":
            return
''',
     "src/flask/debughelpers.py:explain_ignored_app_run"),

    # C2a+C2b: is_ip inlined with a naive IPv4 check, import left behind removed
    ("pallets__flask-4045", "src/flask/sessions.py",
     "from .helpers import is_ip\n", "",
     None),
    ("pallets__flask-4045", "src/flask/sessions.py",
     "        ip = is_ip(rv)\n",
     '''        ip = rv.count(".") == 3 and all(p.isdigit() for p in rv.split("."))\n''',
     "src/flask/helpers.py:is_ip"),

    # C3: merge_hooks replaced by the generic merge_setting
    ("psf__requests-2674", "requests/sessions.py",
     "            hooks=merge_hooks(request.hooks, self.hooks),\n",
     "            hooks=merge_setting(request.hooks, self.hooks),\n",
     "requests/sessions.py:merge_hooks"),

    # C4a+C4b: iter_slices inlined as a generator expression, import pruned
    ("psf__requests-2674", "requests/models.py",
     "    iter_slices, guess_json_utf, super_len, to_native_string)",
     "    guess_json_utf, super_len, to_native_string)",
     None),
    ("psf__requests-2674", "requests/models.py",
     '''        # simulate reading small chunks of the content
        reused_chunks = iter_slices(self._content, chunk_size)

        stream_chunks = generate()

        chunks = reused_chunks if self._content_consumed else stream_chunks
''',
     '''        if self._content_consumed:
            # simulate reading small chunks of the content
            chunks = (self._content[i:i + chunk_size]
                      for i in range(0, len(self._content), chunk_size))
        else:
            chunks = generate()
''',
     "requests/utils.py:iter_slices"),

    # C5: resolve_from_str inlined in cache_dir_from_config, import pruned.
    # (First attempt used underscore-private targets — excluded per the
    # preregistration's verification rule: PythonLanguage.is_offgraph_reachable
    # skips ALL leading-underscore names, so private helpers can never fire.
    # Reported separately as a recall finding, not patched around.)
    ("pytest-dev__pytest-7373", "src/_pytest/cacheprovider.py",
     "from .pathlib import resolve_from_str\n", "",
     None),
    ("pytest-dev__pytest-7373", "src/_pytest/cacheprovider.py",
     '''        return resolve_from_str(config.getini("cache_dir"), config.rootdir)\n''',
     '''        cache_dir = Path(os.path.expanduser(str(config.getini("cache_dir"))))
        if cache_dir.is_absolute():
            return cache_dir
        return Path(str(config.rootdir)) / cache_dir
''',
     "src/_pytest/pathlib.py:resolve_from_str"),

    # C6: mock-argument handling dropped from getfuncargnames
    ("pytest-dev__pytest-7373", "src/_pytest/compat.py",
     '''    # Remove any names that will be replaced with mocks.
    if hasattr(function, "__wrapped__"):
        arg_names = arg_names[num_mock_patch_args(function) :]
    return arg_names
''',
     "    return arg_names\n",
     "src/_pytest/compat.py:num_mock_patch_args"),
]


def main():
    for repo, rel, old, new, target in PLANTS:
        path = ROOT / repo / rel
        text = path.read_text()
        if old not in text and (not new or new in text):
            print(f"already planted: {repo}/{rel}" + (f" -> {target}" if target else ""))
            continue
        n = text.count(old)
        assert n == 1, f"{repo}/{rel}: expected exactly 1 occurrence, found {n}"
        path.write_text(text.replace(old, new))
        print(f"planted: {repo}/{rel}" + (f" -> {target}" if target else " (import prune)"))


if __name__ == "__main__":
    main()
