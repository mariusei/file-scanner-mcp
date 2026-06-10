"""Tests for excerpt condensation (PythonLanguage.condense_excerpt).

The skeleton must keep the information-bearing parts (control flow,
calls, arithmetic, return/raise) and fold trivial statements to "…".
See experiments/condensation/ for the measurements behind the design.
"""

import pytest

from scantool.languages.python import PythonLanguage
from scantool.languages.models import StructureNode
from scantool.formatter import TreeFormatter


@pytest.fixture
def lang():
    return PythonLanguage()


class TestCondenseExcerpt:
    def test_keeps_control_flow_and_calls(self, lang):
        excerpt = '''\
def format_extensions(self, max_types: int = 3) -> str:
    """Format top file extensions as compact string."""
    if not self.extensions:
        return ""

    # Sort by count, descending
    sorted_exts = sorted(self.extensions.items(), key=lambda x: x[1], reverse=True)
    top_exts = sorted_exts[:max_types]

    parts = [f"{ext}:{count}" for ext, count in top_exts]

    if len(sorted_exts) > max_types:
        parts.append("...")

    return " ".join(parts)'''.split("\n")

        skeleton = lang.condense_excerpt(excerpt)

        assert skeleton is not None
        text = "\n".join(skeleton)
        # control flow with conditions survives
        assert "if not self.extensions:" in text
        assert "if len(sorted_exts) > max_types:" in text
        # calls survive
        assert "sorted(" in text
        assert "parts.append('...')" in text
        assert "' '.join(parts)" in text
        # returns survive
        assert "return ''" in text
        # comments and blank lines do not
        assert "Sort by count" not in text
        # trivial subscript assignment is folded
        assert "sorted_exts[:max_types]" not in text
        assert "…" in text

    def test_header_and_docstring_excluded(self, lang):
        excerpt = '''\
def connect(self):
    """Establish database connection."""
    self.conn = driver.connect(self.connection_string)'''.split("\n")

        skeleton = lang.condense_excerpt(excerpt)

        assert skeleton is not None
        text = "\n".join(skeleton)
        # header line and docstring live in the structure tree, not the skeleton
        assert "def connect" not in text
        assert "Establish database" not in text
        assert "driver.connect(self.connection_string)" in text

    def test_indented_method_dedents(self, lang):
        excerpt = [
            "    def query(self, sql):",
            "        return self.cursor.execute(sql).fetchall()",
        ]

        skeleton = lang.condense_excerpt(excerpt)

        assert skeleton == ["return self.cursor.execute(sql).fetchall()"]

    def test_broken_code_falls_back_to_none(self, lang):
        excerpt = ["def broken(:", "    return ???"]

        assert lang.condense_excerpt(excerpt) is None

    def test_literal_only_body_folds_to_none_or_ellipsis(self, lang):
        excerpt = [
            "def __init__(self):",
            "    self.count = 0",
            "    self.name = 'x'",
        ]

        skeleton = lang.condense_excerpt(excerpt)

        # all statements trivial → either fully folded or a single "…"
        assert skeleton is None or skeleton == ["…"]

    def test_try_except_and_loops(self, lang):
        excerpt = '''\
def load(self, paths):
    results = []
    for path in paths:
        try:
            with open(path) as f:
                results.append(parse(f.read()))
        except OSError as e:
            log.warning(e)
            continue
    return results'''.split("\n")

        skeleton = lang.condense_excerpt(excerpt)

        assert skeleton is not None
        text = "\n".join(skeleton)
        assert "for path in paths:" in text
        assert "try:" in text
        assert "except OSError as e:" in text
        assert "with open(path) as f:" in text
        assert "continue" in text
        assert "return results" in text

    def test_long_expression_elides_but_keeps_call_names(self, lang):
        excerpt = '''\
def rank(self, partitions):
    score = compute_weighted_score(shannon_entropy(data), compression_ratio(data), structural_uniqueness(idx, partitions, cache))
    return score'''.split("\n")

        skeleton = lang.condense_excerpt(excerpt)

        assert skeleton is not None
        text = "\n".join(skeleton)
        # outer and nested call names all survive elision
        for name in ("compute_weighted_score", "shannon_entropy",
                     "compression_ratio", "structural_uniqueness"):
            assert name in text

    def test_base_language_default_is_none(self):
        from scantool.languages.generic import GenericLanguage

        assert GenericLanguage().condense_excerpt(["some line"]) is None


class TestGenericStrategies:
    """Generic tree-sitter condensation (BaseLanguage.condense_excerpt).

    skeleton = fold-by-default (imperative flow)
    compact  = keep-by-default (declarative — content must survive)
    """

    def test_typescript_skeleton_keeps_flow_and_calls(self):
        from scantool.languages.typescript import TypeScriptLanguage

        excerpt = '''\
function login(username: string): User | null {
  // look up the user
  const user = users.get(username);
  if (!user) {
    return null;
  }
  log.info("ok");
  return user;
}'''.split("\n")

        skeleton = TypeScriptLanguage().condense_excerpt(excerpt)

        assert skeleton is not None
        text = "\n".join(skeleton)
        assert "const user = users.get(username);" in text
        assert "if (!user) {" in text
        assert 'log.info("ok");' in text
        assert "return user;" in text
        # comment folds, closing braces drop silently
        assert "look up the user" not in text
        assert not any(line.strip() == "}" for line in skeleton)

    def test_go_skeleton_keeps_defer_and_branches(self):
        from scantool.languages.go import GoLanguage

        excerpt = '''\
func Get(index int) (int, bool) {
\tmu.Lock()
\tdefer mu.Unlock()
\t// bounds check
\tif index >= 0 && index < len(items) {
\t\treturn items[index], true
\t}
\treturn 0, false
}'''.split("\n")

        skeleton = GoLanguage().condense_excerpt(excerpt)

        assert skeleton is not None
        text = "\n".join(skeleton)
        assert "defer mu.Unlock()" in text
        assert "if index >= 0 && index < len(items) {" in text
        assert "return items[index], true" in text
        assert "bounds check" not in text

    def test_php_fragment_prefix_enables_parsing(self):
        from scantool.languages.php import PHPLanguage

        excerpt = '''\
function login($user) {
    if (!$user) {
        return null;
    }
    return validate($user);
}'''.split("\n")

        skeleton = PHPLanguage().condense_excerpt(excerpt)

        # without the <?php prefix this parses as HTML text → None
        assert skeleton is not None
        text = "\n".join(skeleton)
        assert "if (!$user) {" in text
        assert "return validate($user);" in text

    def test_sql_compact_keeps_columns(self):
        from scantool.languages.sql import SQLLanguage

        excerpt = '''\
-- Users table for auth
CREATE TABLE users (
    id BIGINT PRIMARY KEY,

    name VARCHAR(50) NOT NULL
);'''.split("\n")

        skeleton = SQLLanguage().condense_excerpt(excerpt)

        assert skeleton is not None
        text = "\n".join(skeleton)
        # declarative content survives — columns ARE the content
        assert "id BIGINT PRIMARY KEY," in text
        assert "name VARCHAR(50) NOT NULL" in text
        # comment folds to …, blank line and ");" drop silently
        assert "Users table" not in text
        assert "…" in text
        assert ");" not in text

    def test_css_compact_keeps_declarations(self):
        from scantool.languages.css import CSSLanguage

        excerpt = '''\
.button {
    /* primary color */
    color: red;

    background: blue;
}'''.split("\n")

        skeleton = CSSLanguage().condense_excerpt(excerpt)

        assert skeleton is not None
        text = "\n".join(skeleton)
        assert "color: red;" in text
        assert "background: blue;" in text
        assert "primary color" not in text

    def test_compact_with_nothing_to_fold_returns_none(self):
        from scantool.languages.sql import SQLLanguage

        excerpt = [
            "SELECT id, name FROM users",
            "WHERE active = 1",
            "ORDER BY name",
        ]

        # nothing folded → verbatim with line numbers is strictly better
        assert SQLLanguage().condense_excerpt(excerpt) is None

    def test_language_without_parser_returns_none(self):
        from scantool.languages.config import ConfigLanguage

        excerpt = ["[server]", "port = 8080", "host = 'localhost'"]

        assert ConfigLanguage().condense_excerpt(excerpt) is None

    def test_markdown_strategy_is_verbatim(self):
        from scantool.languages.markdown import MarkdownLanguage

        # prose: every line is content, no condensation strategy
        assert MarkdownLanguage.CONDENSE_STRATEGY is None


class TestFormatterRendering:
    def _node(self, **kwargs) -> StructureNode:
        return StructureNode(
            type="function", name="foo", start_line=10, end_line=12, **kwargs
        )

    def test_skeleton_preferred_over_excerpt(self):
        node = self._node(
            code_excerpt=["def foo():", "    return bar()"],
            code_skeleton=["return bar()"],
        )

        output = TreeFormatter().format("x.py", [node])

        # skjelett vises som ren pseudokode uten linjenumre
        assert "return bar()" in output
        assert "10 | def foo():" not in output

    def test_condense_false_renders_verbatim(self):
        node = self._node(
            code_excerpt=["def foo():", "    return bar()"],
            code_skeleton=["return bar()"],
        )

        output = TreeFormatter(condense=False).format("x.py", [node])

        assert "10 | def foo():" in output
        assert "11 |     return bar()" in output

    def test_verbatim_fallback_without_skeleton(self):
        node = self._node(code_excerpt=["def foo():", "    return 1 + 1"])

        output = TreeFormatter().format("x.py", [node])

        assert "10 | def foo():" in output


class TestScannerIntegration:
    def test_salient_python_nodes_get_skeleton(self, tmp_path):
        """End-to-end: salient nodes in a real file get code_skeleton."""
        from scantool.scanner import FileScanner

        # entropy analysis needs enough material to find salient partitions
        source = "\n".join(
            f'''\
def transform_{i}(items, threshold):
    """Transform items above threshold."""
    results = []
    for item in items:
        if item.score > threshold * {i + 1}:
            results.append(normalize(item, mode="strict_{i}"))
        else:
            results.append(item)
    return aggregate(results, weights=[0.{i}1, 0.{i}2, 0.{i}3])
'''
            for i in range(8)
        )
        path = tmp_path / "sample.py"
        path.write_text(source)

        structures = FileScanner().scan_file(str(path))

        assert structures is not None
        annotated = [
            n for n in structures
            if n.code_excerpt is not None
        ]
        # every excerpt on a parseable function must have been condensed
        for node in annotated:
            assert node.code_excerpt is not None
            assert node.code_skeleton is not None, f"{node.name} lacks skeleton"
            assert len("\n".join(node.code_skeleton)) < len("\n".join(node.code_excerpt))
