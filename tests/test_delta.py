"""Tests for delta mode: re-scans deliver only what changed since the
session's previous scan. Contract: first scan is always full, suppressed
content is always recoverable (delta=False), structure headers survive."""

import pytest

from scantool.server import scan_file, scan_directory, scan_memory

SOURCE_V1 = '''\
def alpha(items):
    kept = [i for i in items if i.valid]
    return summarize(kept, mode="alpha")


def beta(items):
    counts = {}
    for i in items:
        counts[i.kind] = counts.get(i.kind, 0) + 1
    return counts
'''

SOURCE_V2 = SOURCE_V1.replace(
    "counts[i.kind] = counts.get(i.kind, 0) + 1",
    "counts[i.kind] = counts.get(i.kind, 0) + i.weight",
)


@pytest.fixture(autouse=True)
def fresh_memory():
    scan_memory.clear()
    yield
    scan_memory.clear()


def _scan(path, **kwargs) -> str:
    return scan_file.fn(str(path), **kwargs)[0].text


class TestScanFileDelta:
    def test_first_scan_is_full(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)

        first = _scan(path)

        assert "alpha" in first and "beta" in first
        assert "uendret siden" not in first

    def test_unchanged_file_collapses_to_one_line(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)

        _scan(path)
        second = _scan(path)

        assert "uendret siden forrige scan" in second
        assert "delta=False" in second
        assert second.count("\n") == 0          # bokstavelig én linje
        assert "alpha" not in second            # ingen struktur gjentas

    def test_modified_node_detailed_others_suppressed(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)
        _scan(path)
        path.write_text(SOURCE_V2)

        out = _scan(path)

        assert "[endret]" in out
        assert "1 endret/ny, 1 uendret" in out
        # endret node viser kropp, uendret node kun header
        assert "i.weight" in out
        assert "alpha" in out                      # header overlever
        assert "mode=\"alpha\"" not in out.replace("mode='alpha'", 'mode="alpha"') \
            or "summarize" not in out              # alpha-kroppen er undertrykt

    def test_removed_node_listed(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)
        _scan(path)
        path.write_text(SOURCE_V1.split("\n\n\n")[0] + "\n")  # fjern beta

        out = _scan(path)

        assert "fjernet: beta" in out

    def test_delta_false_gives_full_output(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)
        _scan(path)

        full = _scan(path, delta=False)

        assert "uendret siden" not in full
        assert "alpha" in full and "beta" in full


class TestScanDirectoryDelta:
    def test_all_unchanged_aggregates(self, tmp_path):
        (tmp_path / "a.py").write_text(SOURCE_V1)
        (tmp_path / "b.py").write_text("def gamma():\n    return fetch_thing()\n")

        scan_directory.fn(str(tmp_path), pattern="**/*.py")
        second = scan_directory.fn(str(tmp_path), pattern="**/*.py")[0].text

        assert "alle 2 filer uendret" in second
        assert "delta=False" in second

    def test_partial_change_shows_only_changed_file(self, tmp_path):
        a, b = tmp_path / "a.py", tmp_path / "b.py"
        a.write_text(SOURCE_V1)
        b.write_text("def gamma():\n    return fetch_thing()\n")
        scan_directory.fn(str(tmp_path), pattern="**/*.py")
        a.write_text(SOURCE_V2)

        out = scan_directory.fn(str(tmp_path), pattern="**/*.py")[0].text

        assert "a.py" in out.split("uendret siden")[0]   # endret fil vises fullt
        assert "uendret siden forrige scan (1 filer): b.py" in out

    def test_delta_false_full(self, tmp_path):
        (tmp_path / "a.py").write_text(SOURCE_V1)
        scan_directory.fn(str(tmp_path), pattern="**/*.py")

        out = scan_directory.fn(str(tmp_path), pattern="**/*.py", delta=False)[0].text

        assert "uendret siden" not in out
        assert "alpha" in out
