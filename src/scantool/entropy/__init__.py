"""Entropy-based code saliency analysis - lightweight version for scantool."""

from .core import analyze_file_entropy, SalientPartition

__all__ = ["analyze_file_entropy", "SalientPartition"]
