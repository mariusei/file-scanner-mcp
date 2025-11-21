"""Simplified call graph centrality for scantool."""

import re


def analyze_call_graph_simple(data: bytes, partitions: list[dict]) -> list[float]:
    """
    Simplified call graph analysis - returns centrality scores for partitions.

    Args:
        data: Raw file bytes
        partitions: List of partition dicts

    Returns:
        List of centrality scores (0.0-1.0) per partition
    """
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return [0.0] * len(partitions)

    # Extract function/class names
    entities = []

    # Python: def function_name(
    for match in re.finditer(r"\bdef\s+(\w+)\s*\(", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # Python: class ClassName
    for match in re.finditer(r"\bclass\s+(\w+)", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # JavaScript/TypeScript: function functionName(
    for match in re.finditer(r"\bfunction\s+(\w+)\s*\(", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # C/C++: type function_name(
    for match in re.finditer(r"\b(?:void|int|float|double|char|bool|auto|static)\s+(\w+)\s*\(", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    if not entities:
        return [0.0] * len(partitions)

    # Build call graph (who calls whom)
    entity_names = {e["name"] for e in entities}
    call_counts = {name: 0 for name in entity_names}

    # Count calls
    for match in re.finditer(r"\b(\w+)\s*\(", text):
        called = match.group(1)
        if called in entity_names:
            call_counts[called] += 1

    # Assign centrality to partitions
    centrality_scores = []
    for partition in partitions:
        max_centrality = 0.0
        offset = partition["offset"]

        # Find entities in this partition
        for entity in entities:
            if entity["offset"] >= offset and entity["offset"] < offset + partition["size"]:
                centrality = call_counts.get(entity["name"], 0)
                max_centrality = max(max_centrality, centrality)

        centrality_scores.append(float(max_centrality))

    return centrality_scores
