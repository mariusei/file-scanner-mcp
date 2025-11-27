"""Call graph construction and centrality analysis."""

from collections import defaultdict
from .analyzers.models import CallInfo, DefinitionInfo, CallGraphNode


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

    def find_node(name: str) -> str | None:
        """Find first matching FQN for a name. O(1) average case."""
        candidates = name_index.get(name)
        return candidates[0] if candidates else None

    # Build edges from calls
    for call in calls:
        caller_fqn = find_node(call.caller_name) if call.caller_name else None
        callee_fqn = find_node(call.callee_name)

        # Add edge if both found
        if caller_fqn and callee_fqn and caller_fqn != callee_fqn:
            if callee_fqn not in graph[caller_fqn].callees:
                graph[caller_fqn].callees.append(callee_fqn)
            if caller_fqn not in graph[callee_fqn].callers:
                graph[callee_fqn].callers.append(caller_fqn)

    return graph


def calculate_centrality(graph: dict[str, CallGraphNode]) -> None:
    """
    Calculate centrality scores for all nodes in the call graph.

    Uses simple degree centrality: score = (callers_count * 2) + callees_count
    This favors functions that are called by many others (hub functions).

    Modifies nodes in-place.

    Args:
        graph: Call graph dict
    """
    for node in graph.values():
        # Favor functions that are called often (hubs)
        node.centrality_score = len(node.callers) * 2 + len(node.callees)


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


def get_call_chains(
    graph: dict[str, CallGraphNode], start_node: str, max_depth: int = 3
) -> list[list[str]]:
    """
    Find call chains starting from a node.

    Args:
        graph: Call graph dict
        start_node: Fully qualified name of starting node
        max_depth: Maximum chain depth

    Returns:
        List of call chains (each chain is a list of FQNs)
    """
    if start_node not in graph:
        return []

    chains = []

    def dfs(node_fqn: str, path: list[str], depth: int):
        if depth >= max_depth:
            if len(path) > 1:
                chains.append(path.copy())
            return

        if node_fqn not in graph:
            return

        node = graph[node_fqn]

        # Explore callees
        for callee in node.callees:
            if callee not in path:  # Avoid cycles
                path.append(callee)
                dfs(callee, path, depth + 1)
                path.pop()

        # Save chain if it has at least 2 nodes
        if len(path) > 1:
            chains.append(path.copy())

    dfs(start_node, [start_node], 0)
    return chains


def analyze_cross_file_calls(graph: dict[str, CallGraphNode]) -> dict[str, int]:
    """
    Analyze cross-file call patterns.

    Args:
        graph: Call graph dict

    Returns:
        Dict mapping (file_a, file_b) to call count
    """
    cross_file_calls = defaultdict(int)

    for node in graph.values():
        for callee_fqn in node.callees:
            if callee_fqn in graph:
                callee_node = graph[callee_fqn]
                if node.file != callee_node.file:
                    # Cross-file call
                    key = f"{node.file} → {callee_node.file}"
                    cross_file_calls[key] += 1

    return dict(cross_file_calls)
