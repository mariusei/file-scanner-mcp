"""Test code map functionality on scantool itself."""

from src.scantool.code_map import CodeMap

# Create code map for scantool src directory
cm = CodeMap("src/scantool", respect_gitignore=True)

# Analyze
print("Analyzing scantool codebase...")
result = cm.analyze()

# Print formatted tree
print(cm.format_tree(result, max_entries=20))

# Print some statistics
print("\n" + "="*80)
print("STATISTICS")
print("="*80)
print(f"Total files analyzed: {result.total_files}")
print(f"Entry points found: {len(result.entry_points)}")
print(f"Files in import graph: {len(result.import_graph)}")
print(f"Analysis time: {result.analysis_time:.3f}s")
print(f"Clusters: {list(result.clusters.keys())}")
