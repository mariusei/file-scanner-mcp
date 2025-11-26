"""Code map orchestrator for analyzing codebase structure and relationships."""

import time
from pathlib import Path
from collections import defaultdict
from typing import Optional

from .gitignore import load_gitignore
from .analyzers import (
    get_registry,
    CodeMapResult,
    FileNode,
    EntryPointInfo,
    ImportInfo,
)
from .analyzers.generic_analyzer import GenericAnalyzer


class CodeMap:
    """
    Orchestrator for building a code map of a directory.

    Layer 1 (Milestone 1):
    - File-level import graph
    - Entry point detection
    - File clustering
    - Centrality by import count
    """

    def __init__(
        self,
        directory: str,
        respect_gitignore: bool = True,
        max_files: int = 10000,
    ):
        """
        Initialize code map analyzer.

        Args:
            directory: Root directory to analyze
            respect_gitignore: Whether to respect .gitignore patterns
            max_files: Maximum number of files to analyze (safety limit)
        """
        self.directory = Path(directory).resolve()
        self.respect_gitignore = respect_gitignore
        self.max_files = max_files

        # Load gitignore patterns
        self.gitignore = None
        if respect_gitignore:
            self.gitignore = load_gitignore(self.directory)

        # Get analyzer registry
        self.registry = get_registry()
        self.generic_analyzer = GenericAnalyzer()

    def analyze(self) -> CodeMapResult:
        """
        Perform complete code map analysis (Layer 1).

        Returns:
            CodeMapResult with file graph, entry points, and clusters
        """
        start_time = time.time()
        result = CodeMapResult()

        # Phase 1: Discover files
        files = self._discover_files()
        result.total_files = len(files)

        # Phase 2: Analyze each file
        all_imports = []
        all_entry_points = []
        file_clusters = {}

        for file_path in files:
            # Get analyzer for this file
            analyzer = self._get_analyzer(file_path)
            if not analyzer:
                continue

            # Read file content
            try:
                content = (self.directory / file_path).read_text(encoding="utf-8")
            except Exception:
                continue

            # Skip if analyzer says to skip
            if not analyzer.should_analyze(file_path):
                continue

            # Extract imports
            imports = analyzer.extract_imports(file_path, content)
            all_imports.extend(imports)

            # Find entry points
            entry_points = analyzer.find_entry_points(file_path, content)
            all_entry_points.extend(entry_points)

            # Classify file
            cluster = analyzer.classify_file(file_path, content)
            file_clusters[file_path] = cluster

        # Phase 3: Build import graph
        import_graph = self._build_import_graph(all_imports, files)
        result.import_graph = import_graph

        # Phase 4: Calculate centrality
        self._calculate_centrality(import_graph)

        # Phase 5: Cluster files
        clusters = defaultdict(list)
        for file_path, cluster in file_clusters.items():
            clusters[cluster].append(file_path)
        result.clusters = dict(clusters)

        # Phase 6: Populate result
        result.files = list(import_graph.values())
        result.entry_points = all_entry_points
        result.analysis_time = time.time() - start_time
        result.layers_analyzed = ["layer1"]

        return result

    def _discover_files(self) -> list[str]:
        """
        Discover all files in directory (respecting gitignore).

        Returns:
            List of relative file paths
        """
        files = []

        for path in self.directory.rglob("*"):
            # Only process files
            if not path.is_file():
                continue

            # Check gitignore
            if self.gitignore:
                try:
                    rel_path = str(path.relative_to(self.directory))
                except ValueError:
                    continue

                if self.gitignore.matches(rel_path, False):
                    continue
            else:
                try:
                    rel_path = str(path.relative_to(self.directory))
                except ValueError:
                    continue

            # Safety limit
            if len(files) >= self.max_files:
                break

            files.append(rel_path)

        return files

    def _get_analyzer(self, file_path: str):
        """Get appropriate analyzer for file extension."""
        ext = Path(file_path).suffix
        if not ext:
            return None

        analyzer_class = self.registry.get_analyzer(ext)
        if analyzer_class:
            return analyzer_class()
        else:
            # Use generic analyzer as fallback
            return self.generic_analyzer

    def _build_import_graph(
        self, imports: list[ImportInfo], all_files: list[str]
    ) -> dict[str, FileNode]:
        """
        Build import graph from imports.

        Args:
            imports: List of all imports
            all_files: List of all discovered files

        Returns:
            Dict mapping file path to FileNode
        """
        # Initialize nodes for all files
        graph = {}
        for file_path in all_files:
            graph[file_path] = FileNode(path=file_path)

        # Process imports
        for imp in imports:
            source_file = imp.source_file

            # Ensure source file exists in graph
            if source_file not in graph:
                graph[source_file] = FileNode(path=source_file)

            # Try to resolve target module to a file
            target_file = self._resolve_import_to_file(imp.target_module, all_files)

            if target_file and target_file in graph:
                # Add edge to graph
                if target_file not in graph[source_file].imports:
                    graph[source_file].imports.append(target_file)

                if source_file not in graph[target_file].imported_by:
                    graph[target_file].imported_by.append(source_file)

        return graph

    def _resolve_import_to_file(
        self, module: str, all_files: list[str]
    ) -> Optional[str]:
        """
        Resolve module name to file path.

        Args:
            module: Module name (e.g., "scantool.scanner")
            all_files: List of all files in project

        Returns:
            Relative file path or None
        """
        # Handle relative imports (already resolved in analyzer)
        if "/" in module:
            # Already a file path
            candidate = f"{module}.py"
            if candidate in all_files:
                return candidate
            return None

        # Convert module to file path
        parts = module.split(".")

        # Try various common patterns
        candidates = [
            "/".join(parts) + ".py",  # foo.bar.baz -> foo/bar/baz.py
            "/".join(parts[1:]) + ".py",  # scantool.foo -> foo.py
            "/".join(parts) + "/__init__.py",  # foo.bar -> foo/bar/__init__.py
        ]

        for candidate in candidates:
            if candidate in all_files:
                return candidate

        return None

    def _calculate_centrality(self, graph: dict[str, FileNode]) -> None:
        """
        Calculate centrality scores for all files.

        Centrality = (imported_by_count * 2) + imports_count

        This favors files that are imported by many others (hubs).
        """
        for node in graph.values():
            node.centrality_score = len(node.imported_by) * 2 + len(node.imports)

    def format_tree(self, result: CodeMapResult, max_entries: int = 20) -> str:
        """
        Format code map result as tree structure.

        Args:
            result: CodeMapResult to format
            max_entries: Maximum entries to show per section

        Returns:
            Formatted tree string
        """
        lines = [f"📂 {self.directory.name}/", ""]

        # Section 1: Entry Points
        if result.entry_points:
            lines.append("━━━ ENTRY POINTS ━━━")
            for ep in result.entry_points[:max_entries]:
                if ep.type == "main_function":
                    lines.append(f"  {ep.file}:main() @{ep.line}")
                elif ep.type == "if_main":
                    lines.append(f"  {ep.file}:if __name__ @{ep.line}")
                elif ep.type == "app_instance":
                    lines.append(f"  {ep.file}:{ep.framework} {ep.name} @{ep.line}")
                elif ep.type == "export":
                    lines.append(f"  {ep.file}:{ep.name}")
            lines.append("")

        # Section 2: Core Files (by centrality)
        if result.files:
            lines.append("━━━ CORE FILES (by centrality) ━━━")
            sorted_files = sorted(
                result.files, key=lambda f: f.centrality_score, reverse=True
            )
            for node in sorted_files[:max_entries]:
                if node.centrality_score > 0:
                    lines.append(
                        f"  {node.path}: "
                        f"imports {len(node.imports)}, "
                        f"used by {len(node.imported_by)} files"
                    )
            lines.append("")

        # Section 3: Architecture Clusters
        if result.clusters:
            lines.append("━━━ ARCHITECTURE ━━━")
            for cluster_name in [
                "entry_points",
                "core_logic",
                "plugins",
                "utilities",
                "config",
                "tests",
            ]:
                files = result.clusters.get(cluster_name, [])
                if files:
                    lines.append(
                        f"  {cluster_name.replace('_', ' ').title()}: {len(files)} files"
                    )
                    for f in files[:3]:
                        lines.append(f"    - {f}")
                    if len(files) > 3:
                        lines.append(f"    ... +{len(files) - 3} more")
            lines.append("")

        # Section 4: Key Dependencies
        if result.import_graph:
            lines.append("━━━ KEY DEPENDENCIES ━━━")
            sorted_files = sorted(
                result.files, key=lambda f: f.centrality_score, reverse=True
            )
            for node in sorted_files[:5]:
                if node.imports:
                    lines.append(f"  {node.path}")
                    for imp in node.imports[:3]:
                        lines.append(f"    └→ imports: {imp}")
                    if len(node.imports) > 3:
                        lines.append(f"       ... +{len(node.imports) - 3} more")
            lines.append("")

        # Footer
        lines.append(f"Analysis: {result.total_files} files in {result.analysis_time:.2f}s")

        return "\n".join(lines)
