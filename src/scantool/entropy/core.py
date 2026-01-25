"""Lightweight entropy-based code saliency analysis for scantool.

Stripped-down version - no semantic classification, optional centrality.
"""

import zlib
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class SalientPartition:
    """A salient code segment with line information."""

    start_line: int
    end_line: int
    saliency: float
    data: bytes

    @property
    def line_range(self) -> tuple[int, int]:
        return (self.start_line, self.end_line)


def analyze_file_entropy(
    filepath: str,
    top_percent: float = 0.20,
    use_centrality: bool = True,
) -> list[SalientPartition]:
    """
    Analyze file and return top N% most salient partitions.

    Args:
        filepath: Path to file
        top_percent: Return top N% (0.2 = top 20%)
        use_centrality: Enable call graph centrality scoring

    Returns:
        List of salient partitions sorted by importance
    """
    with open(filepath, "rb") as f:
        data = f.read()

    if len(data) == 0:
        return []

    # Discover patterns (indentation-based for code)
    patterns = _find_indentation_blocks(data)
    if not patterns:
        patterns = _find_line_boundaries(data)

    # Partition by patterns
    partitions = _partition_by_patterns(data, patterns)

    if not partitions:
        return []

    # Rank by entropy + uniqueness (+ optional centrality)
    _rank_partitions(data, partitions, use_centrality, filepath)

    # Sort and take top N%
    ranked = sorted(partitions, key=lambda p: p["saliency"], reverse=True)
    count = max(1, int(len(ranked) * top_percent))
    top_partitions = ranked[:count]

    # Convert to SalientPartition with line numbers
    result = []
    for part in top_partitions:
        start_line = _bytes_to_line_number(data, part["offset"])
        end_line = _bytes_to_line_number(data, part["offset"] + part["size"])
        result.append(
            SalientPartition(
                start_line=start_line,
                end_line=end_line,
                saliency=part["saliency"],
                data=part["data"],
            )
        )

    return result


def _bytes_to_line_number(data: bytes, offset: int) -> int:
    """Convert byte offset to line number (1-indexed)."""
    return data[:offset].count(b"\n") + 1


def _find_indentation_blocks(data: bytes) -> list[dict]:
    """Find structural blocks based on indentation."""
    patterns = []

    if len(data) == 0:
        return patterns

    lines = data.split(b"\n")
    positions = []
    offset = 0
    prev_base_indent = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        if len(stripped) == 0:  # Skip blank lines
            offset += len(line) + 1
            continue

        # Measure indentation
        indent = len(line) - len(line.lstrip(b" \t"))

        # Detect change in BASE indentation level
        base_indent = (indent // 4) * 4

        if prev_base_indent is not None and base_indent != prev_base_indent:
            positions.append(offset)

        prev_base_indent = base_indent
        offset += len(line) + 1

    if positions:
        patterns.append({"type": "indentation_block", "positions": positions})

    return patterns


def _find_line_boundaries(data: bytes) -> list[dict]:
    """Find newline boundaries - universal text pattern."""
    patterns = []
    positions = []

    for i, byte in enumerate(data):
        if byte == ord(b"\n"):
            positions.append(i + 1)

    if positions:
        patterns.append({"type": "line_boundary", "positions": positions})

    return patterns


def _partition_by_patterns(data: bytes, patterns: list[dict], min_size: int = 32) -> list[dict]:
    """Split file at discovered pattern boundaries."""
    boundaries = {0, len(data)}

    for pattern in patterns:
        if "positions" in pattern:
            boundaries.update(pattern["positions"])

    # Sort and create partitions
    boundaries_list = sorted(boundaries)
    partitions = []

    for i in range(len(boundaries_list) - 1):
        start = boundaries_list[i]
        end = boundaries_list[i + 1]

        if end - start < min_size:
            continue  # Skip tiny partitions

        partition_data = data[start:end]

        partitions.append(
            {
                "data": partition_data,
                "offset": start,
                "size": end - start,
                "saliency": 0.0,
            }
        )

    # Fallback if no partitions
    if not partitions:
        partitions.append({"data": data, "offset": 0, "size": len(data), "saliency": 0.0})

    return partitions


def _rank_partitions(
    data: bytes,
    partitions: list[dict],
    use_centrality: bool,
    file_path: Optional[str] = None,
):
    """Rank partitions by information-theoretic metrics."""
    if not partitions:
        return

    # Cache entropy calculations
    entropy_cache = {i: _shannon_entropy(p["data"]) for i, p in enumerate(partitions)}

    # Compute metrics
    shannon_scores = []
    compression_scores = []
    uniqueness_scores = []

    for i, partition in enumerate(partitions):
        shannon_scores.append(entropy_cache[i])
        compression_scores.append(_compression_ratio(partition["data"]))
        uniqueness_scores.append(_structural_uniqueness(i, partitions, entropy_cache))

    # Normalize to [0, 1]
    def normalize(scores):
        arr = np.array(scores)
        if arr.max() > arr.min():
            return (arr - arr.min()) / (arr.max() - arr.min())
        return np.zeros_like(arr)

    shannon_norm = normalize(shannon_scores)
    compression_norm = normalize(compression_scores)
    uniqueness_norm = normalize(uniqueness_scores)

    # Optional centrality
    if use_centrality:
        try:
            from .callgraph import analyze_call_graph_simple

            centrality_scores = analyze_call_graph_simple(data, partitions, file_path)
            centrality_norm = normalize(centrality_scores)

            # Weighted combination with centrality
            for i, partition in enumerate(partitions):
                partition["saliency"] = (
                    0.30 * shannon_norm[i]
                    + 0.20 * compression_norm[i]
                    + 0.30 * uniqueness_norm[i]
                    + 0.20 * centrality_norm[i]
                )
        except Exception:
            # Fallback if centrality unavailable
            use_centrality = False

    if not use_centrality:
        # Without centrality
        for i, partition in enumerate(partitions):
            partition["saliency"] = (
                0.35 * shannon_norm[i] + 0.25 * compression_norm[i] + 0.40 * uniqueness_norm[i]
            )


def _shannon_entropy(data: bytes) -> float:
    """Compute Shannon entropy: H(X) = -Σ p(x) log₂ p(x)"""
    if len(data) == 0:
        return 0.0

    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    probs = counts[counts > 0] / len(data)
    return float(-np.sum(probs * np.log2(probs)))


def _compression_ratio(data: bytes) -> float:
    """Compression ratio as proxy for Kolmogorov complexity."""
    if len(data) == 0:
        return 0.0

    try:
        compressed = zlib.compress(data, level=9)
        return len(compressed) / len(data)
    except Exception:
        return 1.0  # Incompressible


def _structural_uniqueness(idx: int, partitions: list[dict], entropy_cache: dict) -> float:
    """How unique is this partition compared to others?"""
    if len(partitions) <= 1:
        return 1.0

    partition = partitions[idx]
    similar_count = 0
    p_entropy = entropy_cache[idx]

    for i, other in enumerate(partitions):
        if i == idx:
            continue

        # Consider similar if size within 20% and entropy within 10%
        size_ratio = min(partition["size"], other["size"]) / max(partition["size"], other["size"])
        o_entropy = entropy_cache[i]

        if o_entropy > 0:
            entropy_ratio = min(p_entropy, o_entropy) / max(p_entropy, o_entropy)
        else:
            entropy_ratio = 1.0 if p_entropy == 0 else 0.0

        if size_ratio > 0.8 and entropy_ratio > 0.9:
            similar_count += 1

    return 1.0 / (1.0 + similar_count)
