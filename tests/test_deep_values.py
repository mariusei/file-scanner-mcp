"""Deep is "everything", values included. A module-level value never competes
for the excerpt tiers (entropy._SKIP_TYPES), so a budgeted scan shows only
its width-cut signature — `['base', 'bases', 'data', …`. For a module whose
surface IS a list, the list is the content: with no budget it is shown whole,
a single-line value in the signature and a multi-line one as a verbatim,
line-numbered excerpt. Only an explicit depth="deep" asks for it: budgeted
scans and the flag-less default (no budget, no depth — the frozen contract)
are unchanged.
"""

import io

from scantool import cli, server
from scantool.scanner import FileScanner

# Twelve names long enough that the rendered list exceeds every width the
# handler's renderer allows before it cuts (short lists already fit whole)
NAMES = [
    "base_language",
    "bases_registry",
    "data_records",
    "delta_memory",
    "entropy_core",
    "focus_reader",
    "formatter_tree",
    "golden_samples",
    "handler_python",
    "index_surface",
    "json_output",
    "keys_ordering",
]
SOURCE = (
    '"""A module whose surface is a list."""\n'
    "\n"
    f"__all__ = {NAMES!r}\n"
    "\n"
    "_LAT = {\n"
    '    "python": ".py",\n'
    '    "typescript": ".ts",\n'
    '    "go": ".go",\n'
    '    "rust": ".rs",\n'
    "}\n"
    "\n"
    "\n"
    "def run() -> None:\n"
    "    return None\n"
)
DICT_LINES = [f"{n} | {line}" for n, line in enumerate(SOURCE.split("\n")[4:10], start=5)]


def _text(result) -> str:
    return "".join(part.text for part in result)


def _by_name(nodes):
    return {node.name: node for node in nodes}


def test_deep_shows_values_whole():
    nodes = _by_name(FileScanner().scan_content(SOURCE.encode(), "mod.py", expand_values=True))
    assert nodes["__all__"].signature == f"= {NAMES!r}"
    assert nodes["__all__"].code_excerpt is None  # one line: the signature carries it
    assert nodes["_LAT"].code_excerpt == SOURCE.split("\n")[4:10]
    assert nodes["_LAT"].signature is not None and nodes["_LAT"].signature.startswith("= {")


def test_budgeted_and_default_scans_keep_the_width_cut():
    for budget in (300, 1500, None):
        nodes = _by_name(FileScanner().scan_content(SOURCE.encode(), "mod.py", budget=budget))
        assert nodes["__all__"].signature is not None
        assert nodes["__all__"].signature.endswith("…")
        assert "'keys_ordering'" not in nodes["__all__"].signature
        assert nodes["_LAT"].code_excerpt is None


def test_depth_deep_renders_the_dict_verbatim_and_normal_does_not():
    deep = _text(server.scan_file_content(content=SOURCE, filename="mod.py", depth="deep"))
    normal = _text(server.scan_file_content(content=SOURCE, filename="mod.py", depth="normal"))
    default = _text(server.scan_file_content(content=SOURCE, filename="mod.py"))
    assert f"- __all__ = {NAMES!r} @3" in deep
    assert all(line in deep for line in DICT_LINES)
    for text in (normal, default):
        assert "'keys_ordering'" not in text
        assert not any(line in text for line in DICT_LINES)


def test_cli_deep_scan_of_stdin_shows_the_full_list(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(SOURCE))
    code = cli.main(["scan", "-", "--as", "mod.py", "--depth", "deep"])
    out = capsys.readouterr().out
    assert code == 0
    assert f"- __all__ = {NAMES!r} @3" in out
    assert all(line in out for line in DICT_LINES)

    monkeypatch.setattr("sys.stdin", io.StringIO(SOURCE))
    code = cli.main(["scan", "-", "--as", "mod.py"])  # flag-less: the frozen contract
    out = capsys.readouterr().out
    assert code == 0
    assert "'keys_ordering'" not in out and not any(line in out for line in DICT_LINES)
