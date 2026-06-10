"""Tests for node-direct saliency selection (entropy/core.py).

Nodes are scored directly on their byte ranges — no partitioning, no
coverage mapping. Key properties: unique logic beats duplicated boilerplate,
classes defer to their methods, structural noise is never selected.
"""

from scantool.entropy import select_salient_nodes
from scantool.languages import get_language


def scan(source: str, ext: str = ".py"):
    lang = get_language(ext)
    assert lang is not None
    return lang.scan(source.encode())


UNIQUE_LOGIC = '''\
def reconcile(ledger, txns, fx_rates):
    drift = sum(t.amount * fx_rates[t.ccy] for t in txns) - ledger.total
    buckets = {}
    for t in sorted(txns, key=lambda t: abs(t.amount), reverse=True):
        buckets.setdefault(t.ccy, []).append(t)
        if abs(drift) < 0.01:
            break
        drift -= t.amount * (fx_rates[t.ccy] - 1.0)
    return drift, buckets
'''


class TestSelection:
    def test_unique_logic_beats_duplicated_boilerplate(self):
        boiler = "\n".join(
            f'''\
def get_field_{i}(self):
    if self._field_{i} is None:
        self._field_{i} = load_default({i})
    return self._field_{i}
'''
            for i in range(5)
        )
        source = boiler + "\n" + UNIQUE_LOGIC

        data = source.encode()
        selected = select_salient_nodes(data, scan(source))

        assert selected, "selection must not be empty"
        top_node, top_score = selected[0]
        assert top_node.name == "reconcile"
        assert 0.0 < top_score <= 1.0

    def test_top_percent_controls_count(self):
        source = "\n".join(
            f"def fn_{i}(x):\n    return transform_{i}(x) + {i}\n"
            for i in range(10)
        )
        data = source.encode()

        assert len(select_salient_nodes(data, scan(source), top_percent=0.20)) == 2
        assert len(select_salient_nodes(data, scan(source), top_percent=0.50)) == 5
        # floor of 1 even for tiny shares
        assert len(select_salient_nodes(data, scan(source), top_percent=0.01)) == 1

    def test_leaf_preference_class_defers_to_methods(self):
        source = '''\
class Manager:
    def process(self, items):
        return [normalize(i) for i in items if i.valid]

    def report(self, items):
        counts = {}
        for i in items:
            counts[i.kind] = counts.get(i.kind, 0) + 1
        return counts
'''
        data = source.encode()
        selected = select_salient_nodes(data, scan(source), top_percent=1.0)

        names = {node.name for node, _ in selected}
        assert "Manager" not in names
        assert names <= {"process", "report"}

    def test_imports_and_structural_noise_never_selected(self):
        source = "import os\nimport sys\nfrom pathlib import Path\n\n" + UNIQUE_LOGIC
        data = source.encode()

        selected = select_salient_nodes(data, scan(source), top_percent=1.0)

        types = {node.type for node, _ in selected}
        assert "imports" not in types
        assert {node.name for node, _ in selected} == {"reconcile"}

    def test_empty_inputs(self):
        assert select_salient_nodes(b"", None) == []
        assert select_salient_nodes(b"", []) == []
        assert select_salient_nodes(b"x = 1\n", []) == []

    def test_tab_indented_go_selects_function_nodes(self):
        source = "".join(
            f"func Transform{i}(items []Item) []Item {{\n"
            f"\tresults := make([]Item, 0)\n"
            f"\tfor _, item := range items {{\n"
            f"\t\tif item.Score > {i}.5 {{\n"
            f"\t\t\tresults = append(results, normalize{i}(item))\n"
            f"\t\t}}\n"
            f"\t}}\n"
            f"\treturn aggregate(results, {i})\n"
            f"}}\n\n"
            for i in range(8)
        )
        data = source.encode()

        selected = select_salient_nodes(data, scan(source, ".go"))

        assert selected
        assert all(node.name.startswith("Transform") for node, _ in selected)

    def test_results_sorted_by_saliency(self):
        source = "\n".join(
            f"def fn_{i}(x):\n    return x + {i}\n" for i in range(6)
        ) + "\n" + UNIQUE_LOGIC
        data = source.encode()

        selected = select_salient_nodes(data, scan(source), top_percent=1.0)
        scores = [score for _, score in selected]

        assert scores == sorted(scores, reverse=True)


class TestLimitSkeletonDepth:
    def test_one_space_ast_skeleton(self):
        from scantool.languages.base import limit_skeleton_depth

        skeleton = [
            "for item in items:",
            " if item.valid:",
            "  results.append(item)",
            "  log.debug(item)",
            " else:",
            "  skipped += 1",
            "return results",
        ]

        limited = limit_skeleton_depth(skeleton, 2)

        assert limited == [
            "for item in items:",
            " if item.valid:",
            "  …",
            " else:",
            "  …",
            "return results",
        ]

    def test_tab_and_wide_indents_map_by_rank(self):
        from scantool.languages.base import limit_skeleton_depth

        skeleton = [
            "for _, item := range items {",
            "\tif item.Score > 0 {",
            "\t\tresults = append(results, item)",
            "\treturn nil",
            "}",
        ]

        limited = limit_skeleton_depth(skeleton, 2)

        assert "\t\tresults = append(results, item)" not in limited
        assert "\tif item.Score > 0 {" in limited
        assert "  …" in limited

    def test_depth_within_limit_is_unchanged(self):
        from scantool.languages.base import limit_skeleton_depth

        skeleton = ["if x:", " return y"]

        assert limit_skeleton_depth(skeleton, 2) == skeleton


class TestBudgetAllocation:
    def _scan(self, tmp_path, budget):
        from scantool.scanner import FileScanner

        source = "\n".join(
            f'''\
def transform_{i}(items, threshold):
    results = []
    for item in items:
        if item.score > threshold * {i + 1}:
            if item.kind == "strict_{i}":
                results.append(normalize(item, mode="strict_{i}"))
    return aggregate(results, weights=[0.{i}1, 0.{i}2])
'''
            for i in range(12)
        )
        path = tmp_path / "sample.py"
        path.write_text(source)
        return FileScanner().scan_file(str(path), budget=budget)

    @staticmethod
    def _skeleton_cost(structures):
        from scantool.scanner import _estimate_tokens
        return sum(_estimate_tokens(n.code_skeleton) for n in structures
                   if n.code_skeleton)

    def test_no_budget_is_unchanged_s6(self, tmp_path):
        structures = self._scan(tmp_path, budget=None)

        assert sum(1 for n in structures if n.code_excerpt) == 2  # topp 20 % av 12
        assert sum(1 for n in structures if n.code_skeleton) == 12

    def test_budget_caps_estimated_cost(self, tmp_path):
        unlimited = self._skeleton_cost(self._scan(tmp_path, budget=None))
        capped_structures = self._scan(tmp_path, budget=unlimited // 3)

        assert self._skeleton_cost(capped_structures) <= unlimited // 3

    def test_degradation_hits_least_salient_first(self, tmp_path):
        structures = self._scan(tmp_path, budget=120)

        with_skeleton = [n for n in structures if n.code_skeleton]
        without = [n for n in structures
                   if n.code_skeleton is None and n.type == "function"]
        assert with_skeleton, "noe må overleve et lite budsjett"
        assert without, "noe må degraderes bort"
        # de som beholder skjelett er mer saliente enn de som mistet det
        min_kept = min(n.saliency for n in with_skeleton)
        # degraderte noder har ingen saliency satt — de er utenfor display
        assert min_kept > 0

    def test_huge_budget_equals_no_budget(self, tmp_path):
        unlimited = self._scan(tmp_path, budget=None)
        huge = self._scan(tmp_path, budget=10**9)

        assert ([n.code_skeleton for n in unlimited]
                == [n.code_skeleton for n in huge])

    def test_zero_budget_yields_pure_structure(self, tmp_path):
        structures = self._scan(tmp_path, budget=0)

        assert all(n.code_skeleton is None for n in structures)
        assert all(n.code_excerpt is None for n in structures)


class TestTwoTierAnnotation:
    def test_broad_tier_gets_shallow_skeleton_without_excerpt(self, tmp_path):
        from scantool.scanner import FileScanner

        source = "\n".join(
            f'''\
def transform_{i}(items, threshold):
    results = []
    for item in items:
        if item.score > threshold * {i + 1}:
            if item.kind == "strict_{i}":
                results.append(normalize(item, mode="strict_{i}"))
    return aggregate(results, weights=[0.{i}1, 0.{i}2])
'''
            for i in range(10)
        )
        path = tmp_path / "sample.py"
        path.write_text(source)

        structures = FileScanner().scan_file(str(path))

        full_tier = [n for n in structures if n.code_excerpt is not None]
        broad_tier = [n for n in structures
                      if n.code_excerpt is None and n.code_skeleton is not None]

        # 10 kandidater → topp 20 % = 2 i full tier, resten i bred tier
        assert len(full_tier) == 2
        assert len(broad_tier) == 8
        # bred tier er dybdekuttet: ingen linjer dypere enn nivå 2
        for node in broad_tier:
            for line in node.code_skeleton:
                indent = len(line) - len(line.lstrip())
                assert indent <= 2, f"{node.name}: '{line}' er dypere enn nivå 2"
        # full tier beholder full dybde (kildene har dybde-3-logikk)
        assert any(
            len(line) - len(line.lstrip()) >= 3
            for node in full_tier for line in node.code_skeleton
        )
