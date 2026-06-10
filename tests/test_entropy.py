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
