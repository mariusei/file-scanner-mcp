"""Tests for code_health: unreferenced/duplicate flagging.

The flagging must be language-agnostic by construction (text-occurrence
counting, not call graphs) — verified here on Go (which has NO extract_calls
implementation), Swift, Python, and a docs-only markdown project. False
flags are worse than no flags, so every root-guard has its own test.
"""

from scantool.code_health import analyze_health
from scantool.scanner import FileScanner


def scan_dir(tmp_path, files: dict[str, str], pattern="**/*"):
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return FileScanner().scan_directory(str(tmp_path), pattern=pattern)


GO_FILES = {
    "util.go": '''\
package util

func ClampValue(value, low, high int) int {
\tif value < low {
\t\treturn low
\t}
\tif value > high {
\t\treturn high
\t}
\treturn value
}

func forgottenHelper(items []int) int {
\ttotal := 0
\tfor _, item := range items {
\t\ttotal += item
\t}
\treturn total
}
''',
    "app.go": '''\
package util

func RunPipeline(values []int) []int {
\tresult := make([]int, 0)
\tfor _, v := range values {
\t\tresult = append(result, ClampValue(v, 0, 100))
\t}
\treturn result
}
''',
}


class TestUnreferencedLanguageAgnostic:
    def test_go_without_extract_calls(self, tmp_path):
        """Go has no extract_calls — text-occurrence counting must work anyway."""
        results = scan_dir(tmp_path, GO_FILES)

        section = analyze_health(results)

        assert "forgottenHelper" in section
        assert "ClampValue" not in section  # called from app.go

    def test_swift(self, tmp_path):
        results = scan_dir(tmp_path, {
            "Badge.swift": '''\
func formatBadgeText(count: Int) -> String {
    if count > 99 {
        return "99+"
    }
    return String(count)
}

func renderTitleBar(title: String) -> String {
    return "== \\(title) =="
}
''',
            "Screen.swift": '''\
func buildScreen(title: String) -> String {
    return renderTitleBar(title: title)
}
''',
        })

        section = analyze_health(results)

        assert "formatBadgeText" in section
        assert "renderTitleBar" not in section

    def test_markdown_only_project_is_silent(self, tmp_path):
        results = scan_dir(tmp_path, {
            "README.md": "# Prosjekt\n\n## Bakgrunn\n\nTekst her.\n",
            "docs/guide.md": "# Guide\n\nMer tekst.\n",
        })

        assert analyze_health(results) == ""


class TestRootGuards:
    def test_decorated_definitions_never_flagged(self, tmp_path):
        results = scan_dir(tmp_path, {"tools.py": '''\
import framework

@framework.tool()
def exposed_endpoint(request):
    payload = framework.parse(request)
    return framework.respond(payload)
'''})

        assert "exposed_endpoint" not in analyze_health(results)

    def test_string_reference_suppresses_flag(self, tmp_path):
        """Registry patterns reference classes by name in strings."""
        results = scan_dir(tmp_path, {
            "handler.py": '''\
class LegacyHandler:
    def handle(self, event):
        return process(event, mode="legacy")
''',
            "registry.py": 'REGISTRY = {"legacy": "LegacyHandler"}\n',
        })

        assert "LegacyHandler" not in analyze_health(results)

    def test_main_and_tests_never_flagged(self, tmp_path):
        results = scan_dir(tmp_path, {"prog.py": '''\
def main():
    value = compute_something(42)
    print(value)

def test_compute_behaviour():
    assert compute_something(1) == 2
'''})

        section = analyze_health(results)

        assert "main" not in section
        assert "test_compute_behaviour" not in section

    def test_container_classes_never_flagged(self, tmp_path):
        """Registries/DI instantiate classes dynamically — a class with
        members must not be flagged even when its name never appears."""
        results = scan_dir(tmp_path, {"plugin.py": '''\
class ObscurePluginImpl:
    def execute(self, payload):
        return transform_payload(payload)
'''})

        assert "ObscurePluginImpl" not in analyze_health(results)

    def test_subclass_methods_never_flagged(self, tmp_path):
        """Visitor/override/hook methods are dispatched dynamically."""
        results = scan_dir(tmp_path, {"visitor.py": '''\
import ast

class LiteralShortener(ast.NodeTransformer):
    def visit_Lambda_custom(self, node):
        return rewrite_lambda(node)
'''})

        assert "visit_Lambda_custom" not in analyze_health(results)

    def test_shared_names_not_flagged(self, tmp_path):
        """Same name defined twice (overrides/interface impls) is exempt."""
        results = scan_dir(tmp_path, {
            "a.py": "class A:\n    def render_widget(self):\n        return 1\n",
            "b.py": "class B:\n    def render_widget(self):\n        return 2\n",
        })

        assert "render_widget" not in analyze_health(results)


class TestDuplicates:
    def test_identical_blocks_across_go_files(self, tmp_path):
        block = '''\
func normalizeScores(scores []float64) []float64 {
\tresult := make([]float64, len(scores))
\tfor i, s := range scores {
\t\tresult[i] = s / 100.0
\t}
\treturn result
}
'''
        results = scan_dir(tmp_path, {
            "a.go": "package a\n\n" + block + "\nfunc UseA() { normalizeScores(nil) }\n",
            "b.go": "package b\n\n" + block + "\nfunc UseB() { normalizeScores(nil) }\n",
        })

        section = analyze_health(results)

        assert "DUPLICATE (2x identical" in section
        assert "normalizeScores" in section

    def test_short_blocks_not_flagged(self, tmp_path):
        results = scan_dir(tmp_path, {
            "a.py": "def tiny_fn():\n    return shared_call()\n",
            "b.py": "def tiny_fn():\n    return shared_call()\n",
        })

        assert "DUPLICATE" not in analyze_health(results)

    def test_duplicates_within_same_file(self, tmp_path):
        block = '''\
def scale_values(values):
    result = []
    for v in values:
        result.append(v * 2.5)
    return result
'''
        results = scan_dir(tmp_path, {
            "a.py": block + "\n" + block + "\nX = scale_values([1])\n",
        })

        # two identical definitions in the same file — still a duplicate fact
        section = analyze_health(results)

        assert "DUPLICATE (2x identical" in section
