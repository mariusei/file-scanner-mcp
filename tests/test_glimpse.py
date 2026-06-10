"""Tests for the directory glimpse: one line per file with the most salient
node's depth-1 skeleton gist. Measured at 57 facts/1k tokens — the most
fact-dense representation in the pipeline."""

import re

from scantool.scanner import FileScanner
from scantool.directory_formatter import DirectoryFormatter


def fmt(tmp_path, files: dict[str, str], **formatter_kwargs):
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    results = FileScanner().scan_directory(str(tmp_path), pattern="**/*")
    formatter = DirectoryFormatter(include_structures=True,
                                   flatten_structures=True, **formatter_kwargs)
    return formatter.format(str(tmp_path), results)


PY_FILE = '''\
def reconcile(ledger, txns, fx_rates):
    drift = sum(t.amount * fx_rates[t.ccy] for t in txns) - ledger.total
    buckets = {}
    for t in sorted(txns, key=lambda t: abs(t.amount), reverse=True):
        buckets.setdefault(t.ccy, []).append(t)
    return drift, buckets
'''

GO_FILE = '''\
package main

func ClampValue(value, low, high int) int {
\tif value < low {
\t\treturn low
\t}
\tif value > high {
\t\treturn high
\t}
\treturn value
}
'''


class TestGlimpse:
    def test_python_glimpse_shows_body_gist(self, tmp_path):
        output = fmt(tmp_path, {"core.py": PY_FILE})

        glimpse = next(l for l in output.split("\n") if "> reconcile:" in l)
        assert "drift = sum(" in glimpse

    def test_go_declaration_line_skipped(self, tmp_path):
        """Generic skeletons keep the signature line — the glimpse drops it
        since the tree already names the node."""
        output = fmt(tmp_path, {"util.go": GO_FILE})

        glimpse = next(l for l in output.split("\n") if "> ClampValue:" in l)
        assert "func ClampValue" not in glimpse
        assert "if value < low {" in glimpse

    def test_glimpse_capped_at_one_line(self, tmp_path):
        output = fmt(tmp_path, {"core.py": PY_FILE})

        glimpse_lines = [l for l in output.split("\n") if re.search(r"> \w+:", l)]
        assert len(glimpse_lines) == 1
        assert len(glimpse_lines[0].strip()) <= DirectoryFormatter.GLIMPSE_MAX_CHARS + 20

    def test_docs_only_has_no_glimpse(self, tmp_path):
        output = fmt(tmp_path, {"README.md": "# Tittel\n\nBare prosa her.\n"})

        assert not any(re.search(r"> \w+:", l) for l in output.split("\n"))

    def test_opt_out(self, tmp_path):
        output = fmt(tmp_path, {"core.py": PY_FILE}, include_glimpse=False)

        assert not any(re.search(r"> \w+:", l) for l in output.split("\n"))
