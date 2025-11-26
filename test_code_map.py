"""Test code map functionality on scantool itself."""

from src.scantool.code_map import CodeMap

# Create code map for scantool src directory with Layer 2 enabled
cm = CodeMap("src/scantool", respect_gitignore=True, enable_layer2=True)

# Analyze
print("Analyzing scantool codebase with Layer 2...")
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
print(f"Layers analyzed: {result.layers_analyzed}")
print(f"Analysis time: {result.analysis_time:.3f}s")
print(f"Clusters: {list(result.clusters.keys())}")

# Layer 2 statistics
if result.definitions:
    print(f"\nLayer 2:")
    print(f"  Definitions found: {len(result.definitions)}")
    print(f"  Calls found: {len(result.calls)}")
    print(f"  Call graph nodes: {len(result.call_graph)}")
    print(f"  Hot functions: {len(result.hot_functions)}")

    # Show top 5 definitions by type
    from collections import Counter
    def_types = Counter(d.type for d in result.definitions)
    print(f"  Definition breakdown: {dict(def_types)}")
