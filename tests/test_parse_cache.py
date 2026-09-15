"""The parse cache (brief §5.1 item 8): the same blob is parsed once across
calls, callers and processes, and nothing a caller sees changes."""

import pickle
import shutil
import subprocess

import pytest

from scantool import parse_cache
from scantool.languages import get_registry
from scantool.scanner import FileScanner

SOURCE = (
    b"def alpha(x):\n    return x + 1\n\n\nclass Box:\n    def open(self):\n        return True\n"
)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv(parse_cache.CACHE_DIR_ENV, str(tmp_path / "cache"))
    monkeypatch.delenv(parse_cache.NO_CACHE_ENV, raising=False)
    parse_cache.clear()
    yield tmp_path / "cache"
    parse_cache.clear()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_blob_id_is_gits_object_id(tmp_path):
    path = tmp_path / "f.py"
    path.write_bytes(SOURCE)
    expected = subprocess.run(
        ["git", "hash-object", str(path)], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert parse_cache.blob_id(SOURCE) == expected


def test_memo_computes_once_and_never_aliases(cache):
    calls = []

    def compute():
        calls.append(1)
        return {"nodes": [1, 2, 3]}

    first = parse_cache.memo(("k", 1), compute)
    first["nodes"].append(99)  # a caller may mutate what it gets
    second = parse_cache.memo(("k", 1), compute)
    assert calls == [1] and second == {"nodes": [1, 2, 3]} and second is not first


def test_scan_content_parses_once_per_blob(cache, monkeypatch):
    scanner = FileScanner()
    language = get_registry().get(".py")
    parses = []
    original = type(language).scan

    def spy(self, data):
        parses.append(len(data))
        return original(self, data)

    monkeypatch.setattr(type(language), "scan", spy)
    a = scanner.scan_content(SOURCE, "mod.py", budget=300)
    b = scanner.scan_content(SOURCE, "mod.py", budget=300)
    c = scanner.scan_content(SOURCE, "mod.py", budget=None)  # another budget: same parse
    assert len(parses) == 1, parses
    assert a == b and a is not b and [n.name for n in c] == [n.name for n in a]
    a[0].name = "mutated"
    assert scanner.scan_content(SOURCE, "mod.py", budget=300)[0].name == "alpha"


def test_per_line_edits_are_not_cached(cache):
    """A result carrying "[N edits/90d]" labels belongs to one checkout, not
    to the blob: it is computed every time and never written under the key."""
    scanner = FileScanner()
    language_class = type(get_registry().get(".py"))
    directory = cache / f"parse-{_version()}"
    scanner._scan_source(language_class, SOURCE, "mod.py", budget=None, mode="balanced")
    before = {p.name for p in directory.glob("*.pkl")}
    for _ in range(2):
        edited = scanner._scan_source(
            language_class,
            SOURCE,
            "mod.py",
            budget=None,
            mode="balanced",
            line_edits={1: "abc1234"},
        )
        assert edited is not None
    assert {p.name for p in directory.glob("*.pkl")} == before


def test_the_disk_layer_serves_a_new_process(cache):
    scanner = FileScanner()
    first = scanner.scan_content(SOURCE, "mod.py")
    assert list((cache / f"parse-{_version()}").glob("*.pkl")), "nothing written to disk"
    parse_cache.clear()  # a fresh process starts with an empty memory layer
    calls = []
    parse_cache.memo(("probe",), lambda: calls.append(1) or "value")
    parse_cache.clear()
    assert parse_cache.memo(("probe",), lambda: calls.append(2) or "other") == "value"
    assert calls == [1]  # the second answer came from disk
    parse_cache.clear()
    assert scanner.scan_content(SOURCE, "mod.py") == first


def test_no_cache_env_turns_the_disk_layer_off(cache, monkeypatch):
    monkeypatch.setenv(parse_cache.NO_CACHE_ENV, "1")
    FileScanner().scan_content(SOURCE, "mod.py")
    assert not cache.exists()


def test_a_torn_file_is_a_miss(cache):
    scanner = FileScanner()
    scanner.scan_content(SOURCE, "mod.py")
    directory = cache / f"parse-{_version()}"
    for path in directory.glob("*.pkl"):
        path.write_bytes(b"not a pickle")
    parse_cache.clear()
    structures = scanner.scan_content(SOURCE, "mod.py")
    assert structures and structures[0].name == "alpha"
    assert all(pickle.loads(p.read_bytes()) is not None for p in directory.glob("*.pkl"))


def test_memory_layer_is_bounded(cache, monkeypatch):
    monkeypatch.setattr(parse_cache, "_MEMORY_ENTRIES", 3)
    for i in range(6):
        parse_cache.memo(("bounded", i), lambda i=i: i)
    assert len(parse_cache._memory) == 3


def _version() -> str:
    from scantool import __version__

    return __version__
