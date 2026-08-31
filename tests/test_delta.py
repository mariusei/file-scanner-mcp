"""Tests for delta mode: re-scans deliver only what changed since the
session's previous scan. Contract: first scan is always full, suppressed
content is always recoverable (delta=False), structure headers survive."""

import pytest

from scantool.delta import FULL_DETAIL, GIST_DETAIL, ScanMemory
from scantool.languages.models import StructureNode
from scantool.server import scan_directory, scan_file, scan_memory

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
        assert "unchanged since" not in first

    def test_unchanged_file_collapses_to_one_line(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)

        _scan(path)
        second = _scan(path)

        assert "unchanged since last scan" in second
        assert "delta=False" in second
        assert second.count("\n") == 0          # literally one line
        assert "alpha" not in second            # no structure is repeated

    def test_modified_node_detailed_others_suppressed(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)
        _scan(path)
        path.write_text(SOURCE_V2)

        out = _scan(path)

        assert "[changed]" in out
        assert "1 changed/new, 1 unchanged" in out
        # changed node shows its body, unchanged node only its header
        assert "i.weight" in out
        assert "alpha" in out                      # header survives
        assert "mode=\"alpha\"" not in out.replace("mode='alpha'", 'mode="alpha"') \
            or "summarize" not in out              # the alpha body is suppressed

    def test_removed_node_listed(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)
        _scan(path)
        path.write_text(SOURCE_V1.split("\n\n\n")[0] + "\n")  # remove beta

        out = _scan(path)

        assert "removed: beta" in out

    def test_delta_false_gives_full_output(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)
        _scan(path)

        full = _scan(path, delta=False)

        assert "unchanged since" not in full
        assert "alpha" in full and "beta" in full


class TestMemoryTTL:
    """A long-lived server crosses conversations — delta must never refer to
    output a new conversation has not seen. Memory older than TTL = first scan."""

    @staticmethod
    def _age_memory(seconds: float):
        for path, (fp, hashes, ts, detail) in list(scan_memory._files.items()):
            scan_memory._files[path] = (fp, hashes, ts - seconds, detail)

    def test_expired_memory_gives_full_rescan(self, tmp_path):
        from scantool.delta import _MEMORY_TTL_SECONDS

        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)
        _scan(path)
        self._age_memory(_MEMORY_TTL_SECONDS + 1)

        second = _scan(path)

        assert "unchanged since" not in second
        assert "alpha" in second and "beta" in second  # full output

    def test_expired_memory_never_ghost_diffs(self, tmp_path):
        """Changed file + expired memory: full scan, not a node diff against a
        state the consumer never saw."""
        from scantool.delta import _MEMORY_TTL_SECONDS

        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)
        _scan(path)
        self._age_memory(_MEMORY_TTL_SECONDS + 1)
        path.write_text(SOURCE_V2)

        out = _scan(path)

        assert "[changed]" not in out
        assert "delta since last scan" not in out

    def test_unchanged_message_includes_age(self, tmp_path):
        path = tmp_path / "mod.py"
        path.write_text(SOURCE_V1)
        _scan(path)

        second = _scan(path)

        assert "sec ago" in second or "min ago" in second


class TestDetailGating:
    """A delta shortcut may only replace output the consumer has already seen
    at AT LEAST the requested detail: a scan_directory gist never suppresses a
    scan_file, and a shallow budget never suppresses a deeper one."""

    @staticmethod
    def _record(memory, path, detail):
        structures = [StructureNode(type="function", name="foo",
                                    start_line=1, end_line=2)]
        lines = path.read_text().split("\n")
        return memory.diff_and_record(str(path), structures, lines, detail)

    @pytest.fixture
    def sample(self, tmp_path):
        path = tmp_path / "sample.py"
        path.write_text("def foo():\n    return 1\n")
        return path

    def test_gist_record_never_suppresses_full_scan(self, sample):
        memory = ScanMemory()
        self._record(memory, sample, GIST_DETAIL)

        assert memory.file_unchanged(str(sample), FULL_DETAIL) is None
        assert memory.file_unchanged(str(sample), GIST_DETAIL) is not None

    def test_full_record_suppresses_all_levels(self, sample):
        memory = ScanMemory()
        self._record(memory, sample, FULL_DETAIL)

        assert memory.file_unchanged(str(sample), FULL_DETAIL) is not None
        assert memory.file_unchanged(str(sample), 300) is not None
        assert memory.file_unchanged(str(sample), GIST_DETAIL) is not None

    def test_shallow_budget_never_suppresses_deeper_budget(self, sample):
        memory = ScanMemory()
        self._record(memory, sample, 300)

        assert memory.file_unchanged(str(sample), 1500) is None
        assert memory.file_unchanged(str(sample), FULL_DETAIL) is None
        assert memory.file_unchanged(str(sample), 300) is not None

    def test_diff_treats_shallower_record_as_first_scan(self, sample):
        memory = ScanMemory()
        self._record(memory, sample, GIST_DETAIL)

        # Node suppression against a gist record would hide detail the
        # consumer never saw — must behave like a first scan instead
        assert self._record(memory, sample, FULL_DETAIL) is None
        # ... and the record is upgraded: full detail has now been shown
        assert memory.file_unchanged(str(sample), FULL_DETAIL) is not None

    def test_deeper_record_still_gives_node_diff(self, sample):
        memory = ScanMemory()
        self._record(memory, sample, FULL_DETAIL)

        diff = self._record(memory, sample, FULL_DETAIL)
        assert diff is not None
        assert diff.unchanged == {"/function:foo"}


class TestCrossToolDelta:
    """The observed failure end to end: scan_directory gists a file, a later
    scan_file must still deliver the full structure."""

    def test_scan_directory_does_not_poison_scan_file(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text(SOURCE_V1)

        scan_directory.fn(str(tmp_path), pattern="**/*.py")
        out = _scan(path)

        assert "unchanged since last scan" not in out
        assert "alpha" in out and "beta" in out

    def test_max_files_reports_and_enforces_scan_limit(self, tmp_path):
        for name in ("a.py", "b.py", "c.py"):
            (tmp_path / name).write_text(SOURCE_V1)

        out = scan_directory.fn(
            str(tmp_path), pattern="**/*.py", max_files=2, delta=False,
        )[0].text

        assert "Limited to first 2 files" in out
        assert "a.py" in out and "b.py" in out
        assert "c.py" not in out

    def test_scan_file_then_scan_directory_aggregates(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text(SOURCE_V1)

        _scan(path)  # full detail seen — a gist view reveals nothing new
        out = scan_directory.fn(str(tmp_path), pattern="**/*.py")[0].text

        assert "all 1 files unchanged" in out

    def test_shallow_budget_then_full_scan_is_full(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text(SOURCE_V1)

        _scan(path, budget=300)
        out = _scan(path)

        assert "unchanged since last scan" not in out
        assert "alpha" in out and "beta" in out

    def test_full_scan_then_shallow_budget_is_one_liner(self, tmp_path):
        path = tmp_path / "app.py"
        path.write_text(SOURCE_V1)

        _scan(path)
        out = _scan(path, budget=300)

        assert "unchanged since last scan" in out


class TestScanDirectoryDelta:
    def test_all_unchanged_aggregates(self, tmp_path):
        (tmp_path / "a.py").write_text(SOURCE_V1)
        (tmp_path / "b.py").write_text("def gamma():\n    return fetch_thing()\n")

        scan_directory.fn(str(tmp_path), pattern="**/*.py")
        second = scan_directory.fn(str(tmp_path), pattern="**/*.py")[0].text

        assert "all 2 files unchanged" in second
        assert "delta=False" in second

    def test_partial_change_shows_only_changed_file(self, tmp_path):
        a, b = tmp_path / "a.py", tmp_path / "b.py"
        a.write_text(SOURCE_V1)
        b.write_text("def gamma():\n    return fetch_thing()\n")
        scan_directory.fn(str(tmp_path), pattern="**/*.py")
        a.write_text(SOURCE_V2)

        out = scan_directory.fn(str(tmp_path), pattern="**/*.py")[0].text

        assert "a.py" in out.split("unchanged since")[0]   # changed file shown in full
        assert "unchanged since last scan (1 files): b.py" in out

    def test_delta_false_full(self, tmp_path):
        (tmp_path / "a.py").write_text(SOURCE_V1)
        scan_directory.fn(str(tmp_path), pattern="**/*.py")

        out = scan_directory.fn(str(tmp_path), pattern="**/*.py", delta=False)[0].text

        assert "unchanged since" not in out
        assert "alpha" in out
