"""Code map orchestrator for analyzing codebase structure and relationships."""

import time
from pathlib import Path
from collections import defaultdict
from typing import Optional

from .gitignore import load_gitignore
from .languages import (
    get_registry,
    CodeMapResult,
    FileNode,
    EntryPointInfo,
    ImportInfo,
    DefinitionInfo,
    CallInfo,
)
from .languages.generic import GenericLanguage
from . import call_graph


class CodeMap:
    """
    Orchestrator for building a code map of a directory.

    Layer 1:
    - File-level import graph
    - Entry point detection
    - File clustering
    - Centrality by import count

    Layer 2 (Milestone 2):
    - Function/class definitions
    - Cross-file call graph
    - Function-level centrality
    - Hot function detection
    """

    def __init__(
        self,
        directory: str,
        respect_gitignore: bool = True,
        max_files: int = 10000,
        enable_layer2: bool = True,
    ):
        """
        Initialize code map analyzer.

        Args:
            directory: Root directory to analyze
            respect_gitignore: Whether to respect .gitignore patterns
            max_files: Maximum number of files to analyze (safety limit)
            enable_layer2: Enable Layer 2 analysis (call graphs, function centrality)
        """
        self.directory = Path(directory).resolve()
        self.respect_gitignore = respect_gitignore
        self.max_files = max_files
        self.enable_layer2 = enable_layer2

        # Load gitignore patterns
        self.gitignore = None
        if respect_gitignore:
            self.gitignore = load_gitignore(self.directory)

        # Get analyzer registry
        self.registry = get_registry()
        self.generic_language = GenericLanguage()

    def analyze(self) -> CodeMapResult:
        """
        Perform complete code map analysis (Layer 1 + Layer 2 if enabled).

        Returns:
            CodeMapResult with file graph, entry points, clusters, and optionally call graph
        """
        start_time = time.time()
        result = CodeMapResult()

        # Phase 1: Discover files
        files = self._discover_files()
        result.total_files = len(files)

        # Phase 2: Analyze each file (Layer 1 + Layer 2)
        all_imports = []
        all_entry_points = []
        all_definitions = []
        all_calls = []
        file_clusters = {}
        file_definitions = {}  # Track definitions per file
        analyzed_files = []  # Track which files were actually analyzed
        type_to_file = {}  # Map type names to files (for Swift intra-module deps)

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

            # Track that this file was analyzed
            analyzed_files.append(file_path)

            # Layer 1: Extract imports
            imports = analyzer.extract_imports(file_path, content)
            all_imports.extend(imports)

            # Layer 1: Find entry points
            entry_points = analyzer.find_entry_points(file_path, content)
            all_entry_points.extend(entry_points)

            # Layer 1: Classify file
            cluster = analyzer.classify_file(file_path, content)
            file_clusters[file_path] = cluster

            # Layer 2: Extract definitions and calls (if enabled)
            if self.enable_layer2:
                definitions = analyzer.extract_definitions(file_path, content)
                all_definitions.extend(definitions)
                file_definitions[file_path] = definitions

                # Build definitions_map: name → file_path
                # Used by analyzers for type-based import resolution
                # (Swift types, TypeScript interfaces, Go types, etc.)
                for defn in definitions:
                    # Track any named definition - first definition wins
                    if defn.name and defn.name not in type_to_file:
                        type_to_file[defn.name] = file_path

                calls = analyzer.extract_calls(file_path, content, definitions)
                all_calls.extend(calls)

        # Phase 3: Build import graph (only with analyzed files)
        import_graph = self._build_import_graph(all_imports, analyzed_files, type_to_file)
        result.import_graph = import_graph

        # Phase 4: Calculate file-level centrality
        self._calculate_centrality(import_graph)

        # Phase 5: Cluster files
        clusters = defaultdict(list)
        for file_path, cluster in file_clusters.items():
            clusters[cluster].append(file_path)
        result.clusters = dict(clusters)

        # Phase 6: Build call graph (Layer 2)
        if self.enable_layer2 and all_definitions:
            result.definitions = all_definitions
            result.calls = all_calls
            result.call_graph = call_graph.build_call_graph(all_definitions, all_calls)
            call_graph.calculate_centrality(result.call_graph)
            result.hot_functions = call_graph.find_hot_functions(result.call_graph, top_n=10)

        # Phase 7: Populate result
        result.files = list(import_graph.values())
        result.entry_points = all_entry_points
        result.analysis_time = time.time() - start_time
        result.layers_analyzed = ["layer1"]
        if self.enable_layer2:
            result.layers_analyzed.append("layer2")

        return result

    def _discover_files(self) -> list[str]:
        """
        Discover all files in directory (respecting gitignore and skip patterns).

        Uses two-tier noise reduction:
        - Tier 1: Directory/file skip patterns (fast, structural)
        - Tier 2: Language-specific skip (in analyzer.should_analyze())

        Returns:
            List of relative file paths
        """
        from .languages.skip_patterns import should_skip_directory, should_skip_file

        files = []

        for path in self.directory.rglob("*"):
            # Only process files
            if not path.is_file():
                continue

            # Tier 1: Skip common noise directories (fast check)
            # Check all parts of path for skip patterns
            if any(should_skip_directory(part) for part in path.parts):
                continue

            # Tier 1: Skip common noise files
            if should_skip_file(path.name):
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
            return self.generic_language

    def _build_import_graph(
        self, imports: list[ImportInfo], all_files: list[str], type_to_file: dict[str, str] = None
    ) -> dict[str, FileNode]:
        """
        Build import graph from imports.

        Args:
            imports: List of all imports
            all_files: List of all discovered files
            type_to_file: Optional map of type names to file paths (for Swift intra-module deps)

        Returns:
            Dict mapping file path to FileNode
        """
        import os

        now = time.time()
        type_to_file = type_to_file or {}

        # Initialize nodes for all files with metadata
        graph = {}
        for file_path in all_files:
            node = FileNode(path=file_path)

            # Collect file metadata
            try:
                full_path = self.directory / file_path
                stat = full_path.stat()
                node.mtime = stat.st_mtime
                node.size = stat.st_size
                node.age_days = (now - stat.st_mtime) / 86400  # seconds to days
            except (OSError, FileNotFoundError):
                pass

            graph[file_path] = node

        # Process imports
        for imp in imports:
            source_file = imp.source_file

            # Ensure source file exists in graph
            if source_file not in graph:
                graph[source_file] = FileNode(path=source_file)

            # Try to resolve target module to a file
            target_file = self._resolve_import_to_file(imp, all_files, type_to_file)

            if target_file and target_file in graph:
                # Skip self-references
                if target_file == source_file:
                    continue

                # Add edge to graph
                if target_file not in graph[source_file].imports:
                    graph[source_file].imports.append(target_file)

                if source_file not in graph[target_file].imported_by:
                    graph[target_file].imported_by.append(source_file)

        return graph

    def _resolve_import_to_file(
        self,
        imp: ImportInfo,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> Optional[str]:
        """
        Resolve import to file path by delegating to language-specific analyzer.

        Args:
            imp: ImportInfo object containing source file and target module
            all_files: List of all files in project
            definitions_map: Map of type/definition names to file paths

        Returns:
            Relative file path or None
        """
        analyzer = self._get_analyzer(imp.source_file)
        if analyzer:
            return analyzer.resolve_import_to_file(
                imp.target_module, imp.source_file, all_files, definitions_map
            )
        return None

    def _calculate_centrality(self, graph: dict[str, FileNode]) -> None:
        """
        Calculate centrality scores for all files.

        Centrality = (imported_by_count * 2) + imports_count

        This favors files that are imported by many others (hubs).
        """
        for node in graph.values():
            node.centrality_score = len(node.imported_by) * 2 + len(node.imports)

    def _build_directory_structure(self, files: list[str]) -> dict:
        """
        Build directory structure from analyzed files.

        Returns:
            Dict with top-level dirs, their subdirs, and file type info
        """
        structure = defaultdict(lambda: {
            "subdirs": set(),
            "extensions": defaultdict(int),
            "file_count": 0
        })

        for file_path in files:
            parts = file_path.split("/")
            if len(parts) == 1:
                # Root file
                structure["(root)"]["file_count"] += 1
                ext = Path(file_path).suffix or "(no ext)"
                structure["(root)"]["extensions"][ext] += 1
            else:
                top_dir = parts[0]
                structure[top_dir]["file_count"] += 1

                # Track immediate subdirs
                if len(parts) > 2:
                    structure[top_dir]["subdirs"].add(parts[1])

                # Track extensions
                ext = Path(file_path).suffix or "(no ext)"
                structure[top_dir]["extensions"][ext] += 1

        return structure

    def _format_language_tag(self, extensions: dict) -> str:
        """Format dominant language/file type as compact tag."""
        if not extensions:
            return ""

        # Map extensions to language names
        lang_map = {
            ".py": "Python",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".rb": "Ruby",
            ".php": "PHP",
            ".cs": "C#",
            ".c": "C",
            ".cpp": "C++",
            ".h": "C/C++",
            ".sql": "SQL",
            ".md": "Markdown",
            ".json": "JSON",
            ".yaml": "YAML",
            ".yml": "YAML",
        }

        # Find dominant extension
        sorted_exts = sorted(extensions.items(), key=lambda x: x[1], reverse=True)
        if sorted_exts:
            top_ext = sorted_exts[0][0]
            return lang_map.get(top_ext, top_ext)
        return ""

    def _format_age(self, days: float) -> str:
        """Format age in days as human-readable string."""
        if days < 1:
            hours = int(days * 24)
            return f"{hours}h ago" if hours > 0 else "just now"
        elif days < 7:
            return f"{int(days)}d ago"
        elif days < 30:
            weeks = int(days / 7)
            return f"{weeks}w ago"
        elif days < 365:
            months = int(days / 30)
            return f"{months}mo ago"
        else:
            years = days / 365
            return f"{years:.1f}y ago"

    def _format_file_size(self, size: int) -> str:
        """Format file size as human-readable string."""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        else:
            return f"{size / (1024 * 1024):.1f}MB"

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

        # Section 0: Directory Structure (NEW!)
        all_file_paths = [f.path for f in result.files] if result.files else []
        if all_file_paths:
            structure = self._build_directory_structure(all_file_paths)

            # Sort by file count (most files first), exclude (root)
            sorted_dirs = sorted(
                [(k, v) for k, v in structure.items() if k != "(root)"],
                key=lambda x: x[1]["file_count"],
                reverse=True
            )

            if sorted_dirs:
                lines.append("━━━ STRUCTURE ━━━")
                for dir_name, info in sorted_dirs[:8]:  # Show top 8 dirs
                    subdirs = sorted(info["subdirs"])[:3]
                    subdirs_str = ", ".join(subdirs) if subdirs else ""
                    if len(info["subdirs"]) > 3:
                        subdirs_str += f" +{len(info['subdirs']) - 3}"

                    lang_tag = self._format_language_tag(info["extensions"])
                    lang_str = f"[{lang_tag}]" if lang_tag else ""

                    # Format: dirname/    subdirs    [Language]
                    line = f"  {dir_name + '/':<14}"
                    if subdirs_str:
                        line += f" {subdirs_str:<20}"
                    else:
                        line += f" {'(' + str(info['file_count']) + ' files)':<20}"
                    line += f" {lang_str}"
                    lines.append(line)

                # Show root files if any
                if "(root)" in structure:
                    root_info = structure["(root)"]
                    lang_tag = self._format_language_tag(root_info["extensions"])
                    lines.append(f"  (root files)     {root_info['file_count']} files            [{lang_tag}]" if lang_tag else f"  (root files)     {root_info['file_count']} files")

                lines.append("")

        # Section 0b: File Archetypes (multi-signal classification)
        if result.files:
            files_with_meta = [f for f in result.files if f.mtime > 0]

            if files_with_meta:
                # Calculate project's timeline thresholds
                ages = [f.age_days for f in files_with_meta]
                sizes = [f.size for f in files_with_meta if f.size > 0]

                min_age = min(ages)
                max_age = max(ages)
                age_span = max_age - min_age if max_age > min_age else 1
                median_size = sorted(sizes)[len(sizes) // 2] if sizes else 1000

                # Thresholds (relative to project)
                recent_threshold = min_age + (age_span * 0.25)  # Top 25% newest
                old_threshold = min_age + (age_span * 0.50)     # Older than median
                large_threshold = max(median_size, 2000)        # Larger than median or 2KB

                # Classify each file into archetypes
                archetypes = {
                    "core_infrastructure": [],  # 🏛️ old + central + stable
                    "active_core": [],          # 🔧 central + recently changed
                    "active_development": [],   # 🚀 recent + large + not central
                    "stable_utilities": [],     # 📦 central + small + old
                    "potentially_stale": [],    # 💤 old + small + not central + not recent
                }

                for f in files_with_meta:
                    is_recent = f.age_days <= recent_threshold
                    is_old = f.age_days >= old_threshold
                    is_central = len(f.imported_by) > 0
                    is_large = f.size >= large_threshold
                    is_small = f.size < 1000

                    # Classification logic (order matters - first match wins)
                    if is_central and is_recent:
                        archetypes["active_core"].append(f)
                    elif is_central and is_old and not is_recent:
                        if is_small:
                            archetypes["stable_utilities"].append(f)
                        else:
                            archetypes["core_infrastructure"].append(f)
                    elif is_recent and is_large and not is_central:
                        archetypes["active_development"].append(f)
                    elif is_old and is_small and not is_central and not is_recent:
                        archetypes["potentially_stale"].append(f)

                # Format output
                archetype_config = [
                    ("core_infrastructure", "🏛️", "Core Infrastructure", "old + central + stable"),
                    ("active_core", "🔧", "Active Core", "central + recently changed"),
                    ("active_development", "🚀", "Active Development", "recent + large"),
                    ("stable_utilities", "📦", "Stable Utilities", "central + small + old"),
                    ("potentially_stale", "💤", "Potentially Stale", "old + small + unused"),
                ]

                has_any = any(archetypes[key] for key, _, _, _ in archetype_config)
                if has_any:
                    lines.append("━━━ FILE ARCHETYPES ━━━")
                    lines.append(f"  (project span: {self._format_age(min_age)} - {self._format_age(max_age)})")
                    lines.append("")

                    for key, emoji, label, description in archetype_config:
                        files_in_archetype = archetypes[key]
                        if files_in_archetype:
                            # Sort by relevance within archetype
                            if key in ["core_infrastructure", "active_core", "stable_utilities"]:
                                # Sort by centrality (most imported first)
                                files_in_archetype.sort(key=lambda f: len(f.imported_by), reverse=True)
                            elif key == "active_development":
                                # Sort by recency (newest first)
                                files_in_archetype.sort(key=lambda f: f.age_days)
                            else:
                                # Sort by age (oldest first for stale)
                                files_in_archetype.sort(key=lambda f: f.age_days, reverse=True)

                            lines.append(f"  {emoji} {label} ({description}):")
                            for f in files_in_archetype[:4]:
                                age_str = self._format_age(f.age_days)
                                size_str = self._format_file_size(f.size)
                                used_by = f"used by {len(f.imported_by)}" if len(f.imported_by) > 0 else ""
                                lines.append(f"     {f.path:<45} {age_str:<8} {size_str:<8} {used_by}")
                            if len(files_in_archetype) > 4:
                                lines.append(f"     ... +{len(files_in_archetype) - 4} more")
                            lines.append("")

        # Section 1: Entry Points
        if result.entry_points:
            lines.append("━━━ ENTRY POINTS ━━━")
            # Deduplicate entry points by (file, name) - keep highest line number
            # (lower line numbers are often in comments/documentation)
            seen = {}
            for ep in result.entry_points:
                key = (ep.file, ep.name)
                if key not in seen or ep.line > seen[key].line:
                    seen[key] = ep
            deduped_entry_points = list(seen.values())

            for ep in deduped_entry_points[:max_entries]:
                # Delegate formatting to language-specific analyzer
                analyzer = self._get_analyzer(ep.file)
                if analyzer:
                    lines.append(analyzer.format_entry_point(ep))
                else:
                    # Fallback for unknown file types
                    line_str = f" @{ep.line}" if ep.line else ""
                    lines.append(f"  {ep.file}:{ep.name or ep.type}{line_str}")
            lines.append("")

        # Section 2: Core Files (by centrality) with their contents
        if result.files:
            lines.append("━━━ CORE FILES (by centrality) ━━━")
            sorted_files = sorted(
                result.files, key=lambda f: f.centrality_score, reverse=True
            )

            # Build a map of file -> definitions for quick lookup
            file_defs = {}
            if result.definitions:
                for defn in result.definitions:
                    if defn.file not in file_defs:
                        file_defs[defn.file] = []
                    file_defs[defn.file].append(defn)

            shown = 0
            for node in sorted_files:
                if node.centrality_score > 0 and shown < max_entries:
                    # Show file header with import stats
                    lines.append(
                        f"  {node.path}: "
                        f"imports {len(node.imports)}, "
                        f"used by {len(node.imported_by)} files"
                    )

                    # Show what's inside this file (functions, classes)
                    defs_in_file = file_defs.get(node.path, [])
                    if defs_in_file:
                        # Group by type for better readability
                        classes = [d for d in defs_in_file if d.type == "class"]
                        functions = [d for d in defs_in_file if d.type == "function"]
                        methods = [d for d in defs_in_file if d.type == "method"]

                        # Sort functions by centrality (most called first)
                        # Build FQN for each definition to look up in call graph
                        def get_centrality(defn):
                            fqn = f"{defn.file}:{defn.name}"
                            if fqn in result.call_graph:
                                return result.call_graph[fqn].centrality_score
                            return 0

                        classes.sort(key=get_centrality, reverse=True)
                        functions.sort(key=get_centrality, reverse=True)

                        # Show classes first (sorted by centrality)
                        if classes:
                            for cls in classes[:4]:  # Top 4 classes
                                sig = f"({cls.signature})" if cls.signature else ""
                                centrality = get_centrality(cls)
                                # Show centrality if significant
                                cent_str = f" [called by {int(centrality)}]" if centrality > 0 else ""
                                lines.append(f"     class {cls.name}{sig}{cent_str}")

                        # Show top-level functions (sorted by centrality)
                        if functions:
                            for func in functions[:5]:  # Top 5 functions
                                # func.signature might be "name(args)" or just "(args)"
                                if func.signature and not func.signature.startswith('('):
                                    sig = func.signature
                                elif func.signature:
                                    sig = f"{func.name}{func.signature}"
                                else:
                                    sig = f"{func.name}()"

                                centrality = get_centrality(func)
                                cent_str = f" [called by {int(centrality)}]" if centrality > 0 else ""
                                lines.append(f"     def {sig}{cent_str}")

                        # Show count if more exist
                        total = len(classes) + len(functions) + len(methods)
                        shown_count = min(4, len(classes)) + min(5, len(functions))
                        if total > shown_count:
                            lines.append(f"     ... +{total - shown_count} more")

                    shown += 1

            lines.append("")

        # Section 3: Architecture Clusters (with contents for key clusters)
        if result.clusters:
            lines.append("━━━ ARCHITECTURE ━━━")

            # Build file -> definitions map (reuse from above if needed)
            if not file_defs and result.definitions:
                file_defs = {}
                for defn in result.definitions:
                    if defn.file not in file_defs:
                        file_defs[defn.file] = []
                    file_defs[defn.file].append(defn)

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

                    # For important clusters, show file contents
                    show_contents = cluster_name in ["entry_points", "core_logic", "plugins"]
                    files_to_show = files[:3] if show_contents else files[:3]

                    for f in files_to_show:
                        lines.append(f"    - {f}")

                        # Show what's in this file (for key clusters only)
                        if show_contents and f in file_defs:
                            defs = file_defs[f]
                            classes = [d for d in defs if d.type == "class"]
                            functions = [d for d in defs if d.type == "function"]

                            # Sort by centrality (most called first)
                            def get_centrality_arch(defn):
                                fqn = f"{defn.file}:{defn.name}"
                                if fqn in result.call_graph:
                                    return result.call_graph[fqn].centrality_score
                                return 0

                            classes.sort(key=get_centrality_arch, reverse=True)
                            functions.sort(key=get_centrality_arch, reverse=True)

                            # Show top classes/functions
                            shown_items = 0
                            for cls in classes[:2]:
                                cent = get_centrality_arch(cls)
                                cent_str = f" [×{int(cent)}]" if cent > 0 else ""
                                lines.append(f"       class {cls.name}{cent_str}")
                                shown_items += 1
                            for func in functions[:2]:
                                # func.signature might be "name(args)" or just "(args)"
                                if func.signature and not func.signature.startswith('('):
                                    sig = func.signature
                                elif func.signature:
                                    sig = f"{func.name}{func.signature}"
                                else:
                                    sig = f"{func.name}()"

                                cent = get_centrality_arch(func)
                                cent_str = f" [×{int(cent)}]" if cent > 0 else ""
                                lines.append(f"       def {sig}{cent_str}")
                                shown_items += 1

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

        # Section 5: Hot Functions (Layer 2)
        if result.hot_functions:
            lines.append("━━━ HOT FUNCTIONS (most called) ━━━")
            for func in result.hot_functions[:max_entries]:
                if func.centrality_score > 0:
                    # Parse FQN: file:name or file:class.method
                    parts = func.name.split(":")
                    display_name = parts[1] if len(parts) > 1 else func.name
                    lines.append(
                        f"  {display_name} ({func.type}): "
                        f"called by {len(func.callers)}, "
                        f"calls {len(func.callees)} @{parts[0] if len(parts) > 1 else 'unknown'}"
                    )
            lines.append("")

        # Section 6: File Inventory (compact list of all files)
        if result.files:
            lines.append("━━━ FILE INVENTORY ━━━")

            # Build set of "important" files that must be shown regardless
            important_files = set()

            # Files with centrality > 0
            for f in result.files:
                if f.centrality_score > 0 or len(f.imported_by) > 0:
                    important_files.add(f.path)

            # Files in hot functions
            if result.hot_functions:
                for func in result.hot_functions:
                    parts = func.name.split(":")
                    if len(parts) > 1:
                        important_files.add(parts[0])

            # Group files by top-level directory
            dir_files = defaultdict(list)
            for f in result.files:
                if "/" in f.path:
                    parts = f.path.split("/")
                    # Use first two levels for grouping: "backend/app/core" -> "backend/app/"
                    if len(parts) >= 2:
                        dir_key = f"{parts[0]}/{parts[1]}/"
                    else:
                        dir_key = f"{parts[0]}/"
                else:
                    dir_key = "(root)"
                dir_files[dir_key].append(f)

            # Get analyzers for filtering
            from .languages import get_registry
            registry = get_registry()

            # Sort directories by file count
            sorted_dirs = sorted(dir_files.items(), key=lambda x: len(x[1]), reverse=True)

            for dir_path, files in sorted_dirs[:12]:  # Top 12 directories
                # Filter files: keep important ones, filter low-value ones
                filtered_files = []
                for f in files:
                    # Always include important files
                    if f.path in important_files:
                        filtered_files.append(f)
                        continue

                    # Check if low-value via analyzer
                    ext = Path(f.path).suffix
                    analyzer_class = registry.get_analyzer(ext)
                    if analyzer_class and analyzer_class().is_low_value_for_inventory(f.path, f.size):
                        continue

                    filtered_files.append(f)

                if not filtered_files:
                    continue

                # Sort by centrality/importance
                filtered_files.sort(key=lambda x: (x.path in important_files, x.centrality_score), reverse=True)

                # Format: directory (N files)
                #   file1.py, file2.py, file3.py, ...
                file_names = [Path(f.path).name for f in filtered_files[:8]]
                hidden_count = len(filtered_files) - len(file_names)

                files_str = ", ".join(file_names)
                if hidden_count > 0:
                    files_str += f", +{hidden_count}"

                lines.append(f"  {dir_path:<24} {files_str}")

            # Show count of hidden low-value files
            total_shown = sum(len([f for f in files if f.path in important_files or not (
                (analyzer_cls := registry.get_analyzer(Path(f.path).suffix)) and
                analyzer_cls().is_low_value_for_inventory(f.path, f.size)
            )]) for _, files in dir_files.items())
            total_files = len(result.files)
            if total_files > total_shown:
                lines.append(f"  ({total_files - total_shown} low-value files hidden: __init__.py, configs, etc.)")

            lines.append("")

        # Section 7: Next Steps (contextual recommendations)
        lines.append("━━━ NEXT STEPS ━━━")

        # Build smart recommendations based on what we found
        recommendations = []

        # Recommend exploring active development areas
        if result.files:
            files_with_meta = [f for f in result.files if f.mtime > 0]
            if files_with_meta:
                ages = [f.age_days for f in files_with_meta]
                min_age = min(ages)
                max_age = max(ages)
                age_span = max_age - min_age if max_age > min_age else 1
                recent_threshold = min_age + (age_span * 0.25)

                # Find active directories
                active_dirs = set()
                for f in files_with_meta:
                    if f.age_days <= recent_threshold and "/" in f.path:
                        top_dir = f.path.split("/")[0]
                        active_dirs.add(top_dir)

                if active_dirs:
                    top_active = sorted(active_dirs)[:2]
                    for d in top_active:
                        recommendations.append(
                            f'scan_directory("{d}/")  → see code structure inside active area'
                        )

        # Recommend looking at core files
        if result.files:
            central_files = [f for f in result.files if len(f.imported_by) >= 2]
            if central_files:
                top_central = sorted(central_files, key=lambda f: len(f.imported_by), reverse=True)[0]
                recommendations.append(
                    f'scan_file("{top_central.path}")  → see functions/classes in core file'
                )

        # Recommend hot function deep-dive
        if result.hot_functions:
            top_func = result.hot_functions[0]
            parts = top_func.name.split(":")
            file_path = parts[0] if len(parts) > 1 else "unknown"
            func_name = parts[1] if len(parts) > 1 else top_func.name
            recommendations.append(
                f'Read("{file_path}", offset=N)  → read {func_name}() implementation'
            )

        # Default recommendations if nothing specific
        if not recommendations:
            recommendations = [
                'scan_directory("src/")  → see all functions/classes in src/',
                'scan_file("main.py")  → see structure of a specific file',
            ]

        # Add workflow explanation
        lines.append("  Drill down: overview → structure → code")
        lines.append("")
        for rec in recommendations[:3]:
            lines.append(f"    {rec}")
        lines.append("")
        lines.append("  What each tool gives you:")
        lines.append("    scan_directory  → functions, classes, line numbers per file")
        lines.append("    scan_file       → full structure + signatures + entropy-based code snippets")
        lines.append("    Read(offset=N)  → actual source code at specific lines")
        lines.append("")

        # Footer
        layers_str = "+".join(result.layers_analyzed)
        lines.append(f"Analysis: {result.total_files} files in {result.analysis_time:.2f}s ({layers_str})")

        return "\n".join(lines)
