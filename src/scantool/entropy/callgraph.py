"""Call graph centrality for scantool - uses languages/ for precise detection."""

import re
from pathlib import Path
from typing import Optional


def analyze_call_graph_simple(
    data: bytes, partitions: list[dict], file_path: Optional[str] = None
) -> list[float]:
    """
    Call graph analysis - returns centrality scores for partitions.

    Uses tree-sitter via languages/ for precise function detection across all
    supported languages. Falls back to regex for unsupported extensions.

    Args:
        data: Raw file bytes
        partitions: List of partition dicts with 'offset' and 'size' keys
        file_path: Optional file path to determine language (enables tree-sitter)

    Returns:
        List of centrality scores (0.0-1.0) per partition
    """
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return [0.0] * len(partitions)

    # Try tree-sitter extraction via languages/ if file_path provided
    entities = []
    if file_path:
        entities = _extract_entities_via_languages(data, file_path)

    # Fall back to regex if no entities found
    if not entities:
        entities = _extract_entities_regex(text)

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
        size = partition["size"]

        # Find entities in this partition
        for entity in entities:
            if offset <= entity["offset"] < offset + size:
                centrality = call_counts.get(entity["name"], 0)
                max_centrality = max(max_centrality, centrality)

        centrality_scores.append(float(max_centrality))

    return centrality_scores


def _extract_entities_via_languages(data: bytes, file_path: str) -> list[dict]:
    """Extract function/class entities using tree-sitter via languages/.

    Returns list of dicts with 'name' and 'offset' keys.
    """
    try:
        from ..languages import get_language

        ext = Path(file_path).suffix.lower()
        lang = get_language(ext)

        if lang is None:
            return []

        structures = lang.scan(data)
        if structures is None:
            return []

        # Convert StructureNode tree to flat entity list
        entities = []
        _flatten_structures(structures, data, entities)
        return entities

    except Exception:
        # Any error - fall back to regex
        return []


def _flatten_structures(
    structures: list, data: bytes, entities: list[dict], depth: int = 0
) -> None:
    """Recursively flatten StructureNode tree to entity list with byte offsets."""
    if not structures:
        return

    # Pre-compute line start offsets for byte offset calculation
    line_starts = _compute_line_starts(data)

    for node in structures:
        # Skip non-callable types
        if node.type in ("error", "import", "using", "namespace", "format",
                         "dimensions", "content-type", "colors", "transparency",
                         "animation", "optimization", "hint", "color"):
            continue

        # Get byte offset from line number
        if node.start_line and node.start_line <= len(line_starts):
            offset = line_starts[node.start_line - 1]  # 1-indexed to 0-indexed
        else:
            offset = 0

        entities.append({
            "name": node.name,
            "offset": offset,
            "type": node.type,
        })

        # Recurse into children
        if node.children:
            _flatten_structures(node.children, data, entities, depth + 1)


def _compute_line_starts(data: bytes) -> list[int]:
    """Compute byte offset for start of each line."""
    starts = [0]
    for i, byte in enumerate(data):
        if byte == ord(b"\n"):
            starts.append(i + 1)
    return starts


def _extract_entities_regex(text: str) -> list[dict]:
    """Fallback: extract entities using regex patterns.

    Supports Python, JavaScript/TypeScript, C/C++, Go, Rust, Java, Swift, Ruby, PHP.
    """
    entities = []

    # Python: def function_name( / class ClassName
    for match in re.finditer(r"\bdef\s+(\w+)\s*\(", text):
        entities.append({"name": match.group(1), "offset": match.start()})
    for match in re.finditer(r"\bclass\s+(\w+)", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # JavaScript/TypeScript: function name( / class Name
    for match in re.finditer(r"\bfunction\s+(\w+)\s*\(", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # Go: func name( / func (receiver) name(
    for match in re.finditer(r"\bfunc\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # Rust: fn name( / struct Name / impl Name
    for match in re.finditer(r"\bfn\s+(\w+)\s*[<(]", text):
        entities.append({"name": match.group(1), "offset": match.start()})
    for match in re.finditer(r"\bstruct\s+(\w+)", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # Java/C#: type name( (methods and functions)
    for match in re.finditer(
        r"\b(?:void|int|float|double|char|bool|boolean|auto|static|public|private|"
        r"protected|String|Object|var)\s+(\w+)\s*\(",
        text,
    ):
        entities.append({"name": match.group(1), "offset": match.start()})

    # Swift: func name( / class Name / struct Name
    for match in re.finditer(r"\bfunc\s+(\w+)\s*[<(]", text):
        entities.append({"name": match.group(1), "offset": match.start()})
    for match in re.finditer(r"\b(?:class|struct|enum|protocol)\s+(\w+)", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # Ruby: def name
    for match in re.finditer(r"\bdef\s+(\w+)", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # PHP: function name(
    for match in re.finditer(r"\bfunction\s+(\w+)\s*\(", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # Zig: fn name( / const name =
    for match in re.finditer(r"\bfn\s+(\w+)\s*\(", text):
        entities.append({"name": match.group(1), "offset": match.start()})

    # Deduplicate by name (keep first occurrence)
    seen = set()
    unique = []
    for e in entities:
        if e["name"] not in seen:
            seen.add(e["name"])
            unique.append(e)

    return unique
