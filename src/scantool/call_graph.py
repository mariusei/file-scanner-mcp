"""Call graph construction and centrality analysis."""

from collections import defaultdict
from .languages import CallInfo, DefinitionInfo, CallGraphNode


def build_call_graph(
    definitions: list[DefinitionInfo], calls: list[CallInfo]
) -> dict[str, CallGraphNode]:
    """
    Build call graph from definitions and calls.

    Args:
        definitions: List of all function/class definitions
        calls: List of all function calls

    Returns:
        Dict mapping fully qualified name to CallGraphNode
    """
    # Initialize nodes for all definitions
    graph = {}
    for defn in definitions:
        # Create fully qualified name: file:name or file:class.method
        if defn.parent:
            fqn = f"{defn.file}:{defn.parent}.{defn.name}"
        else:
            fqn = f"{defn.file}:{defn.name}"

        graph[fqn] = CallGraphNode(
            name=fqn, file=defn.file, type=defn.type, callers=[], callees=[]
        )

    # Build lookup index for O(1) name resolution (instead of O(n) search)
    # Maps name suffix -> list of matching FQNs
    name_index = defaultdict(list)
    for fqn in graph:
        # Index by ":name" suffix (top-level functions)
        parts = fqn.rsplit(":", 1)
        if len(parts) == 2:
            name_index[parts[1]].append(fqn)
            # Also index by ".method" for class methods
            if "." in parts[1]:
                method_name = parts[1].rsplit(".", 1)[1]
                name_index[method_name].append(fqn)

    def resolve(name: str) -> list[str]:
        """All FQNs a name could refer to. O(1) average case."""
        return name_index.get(name) or []

    # Build edges from calls. A call resolving to k candidates is genuinely
    # ambiguous (polymorphic dispatch, overloads, repeated names) — name alone
    # cannot pick the target. Instead of arbitrarily crowning candidates[0]
    # (which made centrality depend on definition order — see
    # experiments/bucket_entropy/), split the edge credit 1/(m*k) across every
    # caller*callee pair. Distinct (caller_name, callee_name) pairs only, so
    # call frequency does not inflate centrality (matches prior semantics).
    seen_pairs: set[tuple[str, str]] = set()
    for call in calls:
        if not call.caller_name:
            continue
        pair = (call.caller_name, call.callee_name)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        callers = resolve(call.caller_name)
        callees = resolve(call.callee_name)
        if not callers or not callees:
            continue

        weight = 1.0 / (len(callers) * len(callees))
        for caller_fqn in callers:
            for callee_fqn in callees:
                if caller_fqn == callee_fqn:
                    continue
                graph[caller_fqn].out_weight += weight
                graph[callee_fqn].in_weight += weight
                if callee_fqn not in graph[caller_fqn].callees:
                    graph[caller_fqn].callees.append(callee_fqn)
                if caller_fqn not in graph[callee_fqn].callers:
                    graph[callee_fqn].callers.append(caller_fqn)

    return graph


def calculate_centrality(graph: dict[str, CallGraphNode]) -> None:
    """
    Calculate centrality scores for all nodes in the call graph.

    Uses weighted degree centrality: score = (in_weight * 2) + out_weight.
    in_weight/out_weight are the edge-credit sums from build_call_graph; for
    unambiguous names they equal the distinct caller/callee counts, so this
    matches the old len-based score wherever no name collision occurred.
    Favors functions called by many others (hub functions).

    Modifies nodes in-place.

    Args:
        graph: Call graph dict
    """
    for node in graph.values():
        # Favor functions that are called often (hubs)
        node.centrality_score = node.in_weight * 2 + node.out_weight


def find_hot_functions(
    graph: dict[str, CallGraphNode], top_n: int = 10
) -> list[CallGraphNode]:
    """
    Find the most central (hot) functions in the call graph.

    Args:
        graph: Call graph dict
        top_n: Number of top functions to return

    Returns:
        List of CallGraphNode objects sorted by centrality (descending)
    """
    # Calculate centrality if not already done
    if any(node.centrality_score == 0.0 for node in graph.values()):
        calculate_centrality(graph)

    # Sort by centrality
    sorted_nodes = sorted(
        graph.values(), key=lambda n: n.centrality_score, reverse=True
    )

    return sorted_nodes[:top_n]


