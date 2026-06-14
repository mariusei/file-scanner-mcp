"""Tests for call graph analysis."""

import pytest
from scantool.call_graph import (
    build_call_graph,
    calculate_centrality,
    find_hot_functions,
)
from scantool.languages import DefinitionInfo, CallInfo, CallGraphNode


@pytest.fixture
def sample_definitions():
    """Create sample definitions for testing."""
    return [
        DefinitionInfo(file="a.py", type="function", name="foo", line=1),
        DefinitionInfo(file="a.py", type="function", name="bar", line=5),
        DefinitionInfo(file="b.py", type="function", name="baz", line=1),
        DefinitionInfo(file="b.py", type="class", name="MyClass", line=10),
        DefinitionInfo(file="b.py", type="method", name="method1", line=11, parent="MyClass"),
    ]


@pytest.fixture
def sample_calls():
    """Create sample calls for testing."""
    return [
        CallInfo(caller_file="a.py", caller_name="foo", callee_name="bar", line=2),
        CallInfo(caller_file="a.py", caller_name="foo", callee_name="baz", line=3),
        CallInfo(caller_file="b.py", caller_name="baz", callee_name="foo", line=2),
        CallInfo(caller_file="b.py", caller_name="method1", callee_name="bar", line=12),
    ]


def test_build_call_graph(sample_definitions, sample_calls):
    """Test building call graph from definitions and calls."""
    graph = build_call_graph(sample_definitions, sample_calls)

    # Should have nodes for all definitions
    assert len(graph) == 5

    # Check FQN format
    assert "a.py:foo" in graph
    assert "a.py:bar" in graph
    assert "b.py:baz" in graph
    assert "b.py:MyClass" in graph
    assert "b.py:MyClass.method1" in graph


def test_build_call_graph_edges(sample_definitions, sample_calls):
    """Test that call graph edges are correctly built."""
    graph = build_call_graph(sample_definitions, sample_calls)

    # foo calls bar and baz
    foo_node = graph["a.py:foo"]
    assert "a.py:bar" in foo_node.callees
    assert "b.py:baz" in foo_node.callees

    # bar is called by foo and method1
    bar_node = graph["a.py:bar"]
    assert "a.py:foo" in bar_node.callers
    assert "b.py:MyClass.method1" in bar_node.callers


def test_calculate_centrality(sample_definitions, sample_calls):
    """Test centrality calculation."""
    graph = build_call_graph(sample_definitions, sample_calls)
    calculate_centrality(graph)

    # bar is called by 2 functions (foo, method1) and calls 0
    # centrality = 2 * 2 + 0 = 4
    bar_node = graph["a.py:bar"]
    assert bar_node.centrality_score == 4

    # foo is called by 1 function (baz) and calls 2 (bar, baz)
    # centrality = 1 * 2 + 2 = 4
    foo_node = graph["a.py:foo"]
    assert foo_node.centrality_score == 4


def test_find_hot_functions(sample_definitions, sample_calls):
    """Test finding hot functions."""
    graph = build_call_graph(sample_definitions, sample_calls)
    calculate_centrality(graph)

    hot_funcs = find_hot_functions(graph, top_n=3)

    # Should return top 3 functions
    assert len(hot_funcs) <= 3

    # Should be sorted by centrality (descending)
    for i in range(len(hot_funcs) - 1):
        assert hot_funcs[i].centrality_score >= hot_funcs[i + 1].centrality_score


def test_empty_graph():
    """Test handling of empty graph."""
    graph = build_call_graph([], [])
    assert len(graph) == 0

    calculate_centrality(graph)  # Should not crash

    hot_funcs = find_hot_functions(graph, top_n=10)
    assert len(hot_funcs) == 0


def test_no_calls():
    """Test graph with definitions but no calls."""
    definitions = [
        DefinitionInfo(file="test.py", type="function", name="foo", line=1),
        DefinitionInfo(file="test.py", type="function", name="bar", line=5),
    ]

    graph = build_call_graph(definitions, [])

    # Should have nodes
    assert len(graph) == 2

    # But no edges
    for node in graph.values():
        assert len(node.callers) == 0
        assert len(node.callees) == 0


def test_self_call_ignored():
    """Test that self-calls are ignored."""
    definitions = [
        DefinitionInfo(file="test.py", type="function", name="recursive", line=1),
    ]

    calls = [
        # Function calling itself
        CallInfo(caller_file="test.py", caller_name="recursive", callee_name="recursive", line=2),
    ]

    graph = build_call_graph(definitions, calls)
    node = graph["test.py:recursive"]

    # Should not have self-reference
    assert "test.py:recursive" not in node.callers
    assert "test.py:recursive" not in node.callees


def test_ambiguous_call_splits_credit():
    """A call resolving to k candidates splits edge credit 1/k.

    Name alone cannot pick between two same-named functions, so neither is
    crowned — each gets half the credit. See experiments/bucket_entropy/.
    """
    definitions = [
        DefinitionInfo(file="x.py", type="function", name="target", line=1),
        DefinitionInfo(file="y.py", type="function", name="target", line=1),
        DefinitionInfo(file="c.py", type="function", name="caller", line=1),
    ]
    calls = [
        CallInfo(caller_file="c.py", caller_name="caller", callee_name="target", line=2),
    ]

    graph = build_call_graph(definitions, calls)
    assert graph["x.py:target"].in_weight == pytest.approx(0.5)
    assert graph["y.py:target"].in_weight == pytest.approx(0.5)
    assert graph["c.py:caller"].out_weight == pytest.approx(1.0)

    calculate_centrality(graph)
    assert graph["x.py:target"].centrality_score == pytest.approx(1.0)
    assert graph["y.py:target"].centrality_score == pytest.approx(1.0)


def test_centrality_is_order_invariant():
    """Per-node centrality must not depend on definition order.

    Regression for the candidates[0] defect: the old tie-break gave ALL the
    credit to whichever same-named definition was seen first, so reversing the
    definition order moved a function in/out of the hot list. Distribute makes
    each node's score independent of order.
    """
    definitions = [
        DefinitionInfo(file="x.py", type="function", name="target", line=1),
        DefinitionInfo(file="y.py", type="function", name="target", line=1),
        DefinitionInfo(file="c.py", type="function", name="caller", line=1),
        DefinitionInfo(file="d.py", type="function", name="caller2", line=1),
    ]
    calls = [
        CallInfo(caller_file="c.py", caller_name="caller", callee_name="target", line=2),
        CallInfo(caller_file="d.py", caller_name="caller2", callee_name="target", line=2),
    ]

    def scores(defs):
        graph = build_call_graph(defs, calls)
        calculate_centrality(graph)
        return {name: node.centrality_score for name, node in graph.items()}

    assert scores(definitions) == scores(list(reversed(definitions)))
