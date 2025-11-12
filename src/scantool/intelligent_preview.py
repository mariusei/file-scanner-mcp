"""Intelligent directory preview using Ollama for smart file sampling."""

import json
import re
import asyncio
from pathlib import Path
from collections import defaultdict
from typing import Optional
import httpx

from .scanner import FileScanner
from .gitignore import load_gitignore

# Constants
NOISE_PATTERNS = [
    "node_modules/", ".venv/", "dist/", "build/",
    ".git/", "__pycache__/", "logs/", ".cache/",
    ".DS_Store", "trash/", ".bmad-core/", ".claude/",
    ".github/", ".playwright-mcp/", "test_data/", "test_artifacts/",
    "real_test_data/", "tests/", "test_data_samples/"
]

ENTRY_POINT_FILES = ["main.py", "app.tsx", "index.ts"]
CACHE_DIRS = [".pytest_cache", ".cache", "__pycache__"]
SOURCE_EXTENSIONS = [".py", ".ts", ".js", ".rs", ".go"]
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif")

# Directory classification rules: (keywords, file_count_range, priority)
DIR_CLASSIFICATIONS = [
    # (keywords, min_files, max_files, category, priority)
    (CACHE_DIRS, 0, float('inf'), "test", 5),
    (["database", "migration"], 0, float('inf'), "database", 70),
    (["docs", "documentation"], 0, float('inf'), "docs", 60),
    (["data", "rådata", "basisdata"], 0, float('inf'), "data", 10),
    (["backup"], 0, float('inf'), "backup", 5),
    (["test"], 0, float('inf'), "test", 15),
    (["api", "core", "services", "components", "hooks", "models"], 3, 100, "core_logic", 80),
]

OLLAMA_BASE_URL = "http://localhost:11434/api/generate"
OLLAMA_TIMEOUT = 90.0


def classify_directory(dir_name: str, stats: dict) -> tuple[str, int]:
    """Classify directory by type/importance. Returns: (category, priority_score)"""
    file_count = stats["count"]
    size_mb = stats["total_size"] / 1024 / 1024
    filenames = [Path(f["path"]).name for f in stats["files"][:10]]
    filenames_str = " ".join(filenames).lower()
    dir_lower = dir_name.lower()

    # Special case: Root directory
    if dir_name == "_root":
        return ("entry_point", 95)

    # Special case: Entry points (small directories with key files)
    if file_count <= 3:
        if any(name in filenames_str for name in ENTRY_POINT_FILES):
            return ("entry_point", 100)
        if "readme" in filenames_str and file_count == 1:
            return ("docs", 60)

    # Special case: src/ directories with source code
    if "/src/" in dir_name or dir_name.startswith("src/"):
        if any(ext in filenames_str for ext in SOURCE_EXTENSIONS):
            return ("core_logic", 85)

    # Special case: Very large directories
    if size_mb > 1000:
        return ("backup", 5)

    # Rule-based classification
    for keywords, min_files, max_files, category, priority in DIR_CLASSIFICATIONS:
        if any(kw in dir_lower for kw in keywords):
            if min_files <= file_count <= max_files:
                return (category, priority)

    # Default: utility
    return ("utility", 40)


def group_by_category(dir_stats: dict) -> dict:
    """Group directories by category."""
    groups = defaultdict(list)

    for dir_name, stats in dir_stats.items():
        category, priority = classify_directory(dir_name, stats)

        # Get representative files
        samples = [Path(f["path"]).name for f in stats["files"][:3]]
        if stats["count"] > 3:
            samples.append(f"... +{stats['count'] - 3}")

        groups[category].append({
            "dir": dir_name,
            "files": stats["count"],
            "size_kb": stats["total_size"] / 1024,
            "samples": samples,
            "priority": priority
        })

    # Sort within each category by priority
    for category in groups:
        groups[category].sort(key=lambda x: x["priority"], reverse=True)

    return groups


async def _call_ollama(prompt: str, model: str, timeout: float = OLLAMA_TIMEOUT, num_predict: int = 500) -> Optional[list]:
    """Helper function to call Ollama API and extract JSON array from response."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OLLAMA_BASE_URL,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": num_predict}
                }
            )

        output = response.json()["response"]
        json_match = re.search(r'\[.*?\]', output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                return None
        return None
    except Exception:
        return None


async def stage1_select_directories(
    dir_stats: dict,
    target_dirs: int,
    model: str = "qwen2.5-coder:1.5b"
) -> list[str]:
    """Stage 1: Ask Ollama to identify most important directories.

    target_dirs should be computed adaptively based on repository size.
    """

    groups = group_by_category(dir_stats)

    sections = []

    if "entry_point" in groups:
        sections.append("🚀 ENTRY POINTS (1-3 files, main.py/App.tsx/README):")
        for d in groups["entry_point"][:10]:
            samples = ", ".join(d["samples"][:5])
            sections.append(f"  • {d['dir']} ({d['files']} files) → {samples}")
        sections.append("")

    if "core_logic" in groups:
        sections.append("⚙️ CORE LOGIC (api, core, services, components, hooks):")
        for d in groups["core_logic"][:15]:
            samples = ", ".join(d["samples"][:5])
            sections.append(f"  • {d['dir']} ({d['files']} files) → {samples}")
        sections.append("")

    if "database" in groups:
        sections.append("🗄️ DATABASE:")
        for d in groups["database"][:10]:
            samples = ", ".join(d["samples"][:5])
            sections.append(f"  • {d['dir']} ({d['files']} files) → {samples}")
        sections.append("")

    if "docs" in groups:
        sections.append("📚 DOCS:")
        for d in groups["docs"][:10]:
            samples = ", ".join(d["samples"][:5])
            sections.append(f"  • {d['dir']} ({d['files']} files) → {samples}")
        sections.append("")

    prompt_body = "\n".join(sections)

    # Get all available directory names for the constraint
    all_dir_names = sorted(dir_stats.keys())
    dir_list_str = '", "'.join(all_dir_names[:20])  # Show first 20 as examples

    prompt = f"""Select the {target_dirs} most important directories from the list below.

AVAILABLE DIRECTORIES ({len(all_dir_names)} total):
{prompt_body}

INSTRUCTIONS:
1. Focus on 🚀 ENTRY POINTS and ⚙️ CORE LOGIC directories
2. Include 🗄️ DATABASE and 📚 DOCS if relevant
3. You MUST ONLY select from the directories listed above
4. Return EXACTLY {target_dirs} directory names (or fewer if less available)

Return ONLY a JSON array with directory names from the list above:
["{all_dir_names[0] if all_dir_names else '_root'}", ...]

IMPORTANT: Select ONLY from these exact directory names shown above. Do not invent new directory names."""

    selected = await _call_ollama(prompt, model, timeout=90.0, num_predict=500)

    if selected:
        # Filter to only include directories that actually exist
        valid_dirs = [d for d in selected if d in dir_stats]
        if valid_dirs:
            return valid_dirs

    # Fallback: return top N directories by file count
    if dir_stats:
        sorted_dirs = sorted(dir_stats.items(), key=lambda x: x[1]["count"], reverse=True)
        return [d[0] for d in sorted_dirs[:min(target_dirs, len(sorted_dirs))]]

    return []


async def stage2_select_files(
    dir_name: str,
    files: list,
    top_n: int,
    model: str = "qwen2.5-coder:1.5b"
) -> dict:
    """Stage 2: Ask Ollama to select important files from a directory."""

    # Use explicit bullet-point prompt (validated to work with small models)
    prompt = f"""Select {top_n} most important files from "{dir_name}/".

Files ({len(files)} files):
{json.dumps(files, indent=2)}

Prioritize:
- Entry points (main.py, App.tsx)
- Large files (5-40KB) = logic
- Recent (1 week ago) = active
- Core business logic

Avoid:
- Test files
- Very small/large files

Return ONLY JSON array of exact paths:
["path/to/file.ext", ...]"""

    selected = await _call_ollama(prompt, model, timeout=60.0, num_predict=1000)

    if selected:
        # Strip leading slashes from paths
        cleaned = [p.lstrip('/') for p in selected]
        return {"directory": dir_name, "selected": cleaned}

    return {"directory": dir_name, "selected": []}


async def stage2_parallel_sampling(
    selected_dirs: list[str],
    dir_stats: dict,
    model: str = "qwen2.5-coder:1.5b"
) -> list[dict]:
    """Stage 2: Parallel sampling of files from selected directories."""

    tasks = []

    for dir_name in selected_dirs:
        if dir_name not in dir_stats:
            continue

        files = dir_stats[dir_name]["files"]
        file_count = len(files)

        # Adaptive top_n based on directory type
        if dir_name == "_root":
            top_n = min(6, file_count)
        elif "api" in dir_name.lower():
            top_n = min(15, file_count)  # Get ALL api files!
        elif "core" in dir_name.lower():
            top_n = min(10, file_count)
        elif "components" in dir_name.lower():
            top_n = min(12, file_count)
        elif "hooks" in dir_name.lower():
            top_n = min(8, file_count)
        elif file_count > 50:
            top_n = 10
        elif file_count > 20:
            top_n = 8
        elif file_count > 10:
            top_n = 6
        else:
            top_n = file_count  # Take ALL if small

        tasks.append(stage2_select_files(dir_name, files, top_n, model))

    results = await asyncio.gather(*tasks)
    return results


def format_structure_compact(structures: list, max_items: int = 10) -> str:
    """
    Format StructureNode list as compact token-efficient string.

    Returns format like:
    funksjoner: foo(), bar(x, y), baz() [+5 more]
    klasser: MyClass, OtherClass
    """
    if not structures:
        return ""

    # Group by type
    by_type = defaultdict(list)
    for node in structures:
        if node.type == "file-info":
            continue
        by_type[node.type].append(node.name)

    # Format each type compactly
    parts = []

    # Code structures (prioritized first)
    code_types = ["class", "function", "method", "interface", "type", "const", "variable"]
    # Markdown structures
    markdown_types = ["heading-1", "heading-2", "heading-3", "code-block"]

    all_types = code_types + markdown_types

    for type_name in all_types:
        if type_name in by_type:
            items = by_type[type_name]

            # Norwegian plural forms
            label_map = {
                "class": "klasser",
                "function": "funksjoner",
                "method": "metoder",
                "interface": "interfaces",
                "type": "typer",
                "const": "konstanter",
                "variable": "variabler",
                "heading-1": "hovedoverskrifter",
                "heading-2": "underoverskrifter",
                "heading-3": "seksjoner",
                "code-block": "kodeblokker"
            }
            label = label_map.get(type_name, type_name)

            if len(items) <= max_items:
                parts.append(f"{label}: {', '.join(items[:max_items])}")
            else:
                parts.append(f"{label}: {', '.join(items[:max_items])} [+{len(items) - max_items} more]")

    return " | ".join(parts) if parts else "ingen struktur funnet"


def intelligent_preview(
    directory: str,
    ollama_model: str = "qwen2.5-coder:1.5b",
    max_depth: Optional[int] = 5,
    respect_gitignore: bool = True
) -> str:
    """
    Intelligent preview using Ollama for smart file sampling.

    Returns directory overview + code structure for ~100-150 intelligently sampled files.

    Args:
        directory: Root directory to scan
        ollama_model: Ollama model to use (default: qwen2.5-coder:1.5b)
        max_depth: Max directory depth
        respect_gitignore: Respect .gitignore patterns

    Returns:
        Formatted preview string with code structure
    """

    # Collect all files with proper directory grouping
    root_path = Path(directory).resolve()
    gitignore = load_gitignore(root_path) if respect_gitignore else None

    # Walk directory and collect all files
    all_files = []
    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue

        try:
            rel_path = str(file_path.relative_to(root_path))

            # Skip noise patterns
            if any(n in rel_path for n in NOISE_PATTERNS):
                continue

            # Respect gitignore
            if gitignore and gitignore.matches(rel_path, is_dir=False):
                continue

            # Get file stats
            stat = file_path.stat()

            # Skip images and very small files
            if rel_path.endswith(IMAGE_EXTENSIONS) or stat.st_size < 100:
                continue

            all_files.append({
                "path": rel_path,
                "size": stat.st_size,
                "modified_ago": "recently"
            })
        except (OSError, PermissionError):
            continue

    # Group files by directory (same logic as test files)
    dir_stats = defaultdict(lambda: {"files": [], "count": 0, "total_size": 0})

    for f in all_files:
        filepath = Path(f["path"])
        parent_dir = str(filepath.parent)

        if parent_dir == ".":
            key = "_root"
        else:
            parts = parent_dir.split("/")
            # Group by top 3 levels (e.g., "src/scantool/scanners")
            if len(parts) >= 3:
                key = "/".join(parts[:3])
            else:
                key = parent_dir

        dir_stats[key]["files"].append(f)
        dir_stats[key]["count"] += 1
        dir_stats[key]["total_size"] += f["size"]

    # Convert defaultdict to regular dict
    dir_stats = dict(dir_stats)

    total_files = len(all_files)
    total_dirs = len(dir_stats)

    # Adaptive target_dirs based on repository size
    if total_dirs < 10:
        target_dirs = total_dirs  # Small repos: all directories
    elif total_dirs < 30:
        target_dirs = int(total_dirs * 0.7)  # Medium repos: 70%
    elif total_dirs < 60:
        target_dirs = int(total_dirs * 0.5)  # Large repos: 50%
    else:
        target_dirs = 30  # Very large repos: fixed minimum

    # Run Ollama-based sampling (async)
    try:
        loop = asyncio.get_running_loop()
        # Already in async context
        import nest_asyncio
        nest_asyncio.apply()
    except RuntimeError:
        # No event loop running, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Stage 1: Select directories
    selected_dirs = loop.run_until_complete(
        stage1_select_directories(dir_stats, target_dirs=target_dirs, model=ollama_model)
    )

    if not selected_dirs:
        # Fallback if Ollama fails
        return f"📂 {directory}\n   {total_files} files found\n\n⚠️  Ollama unavailable or returned no directories"

    # Stage 2: Select files from chosen directories
    results = loop.run_until_complete(
        stage2_parallel_sampling(selected_dirs, dir_stats, model=ollama_model)
    )

    # Collect selected files
    selected_files = []
    for result in results:
        if result.get("selected"):
            selected_files.extend(result["selected"])

    # Scan selected files for code structure
    scanner = FileScanner(show_errors=False)
    file_structures = {}

    for file_path in selected_files[:150]:  # Limit to 150 files max
        full_path = Path(directory) / file_path
        if not full_path.is_file():
            continue
        try:
            structures = scanner.scan_file(str(full_path), include_file_metadata=False)
            if structures:
                file_structures[file_path] = structures
        except Exception:
            pass

    # Check if we got enough meaningful results
    # If intelligent mode found very few files with structure, raise exception to trigger fallback
    coverage_ratio = len(file_structures) / total_files if total_files > 0 else 0
    min_files_threshold = min(20, total_files * 0.1)  # At least 20 files or 10% of total

    if len(file_structures) < min_files_threshold:
        raise RuntimeError(
            f"Intelligent mode found structure in only {len(file_structures)}/{total_files} files "
            f"({coverage_ratio*100:.1f}%). This may indicate mostly non-code files (markdown, text, etc). "
            f"Falling back to fast mode for better overview."
        )

    # Format output - minimal, token-efficient
    lines = [f"📂 {directory} ({len(file_structures)}/{total_files} files)\n"]

    # Group by directory
    by_dir = defaultdict(list)
    for file_path in sorted(file_structures.keys()):
        dir_name = str(Path(file_path).parent) if Path(file_path).parent != Path('.') else "_root"
        by_dir[dir_name].append(file_path)

    for dir_name in sorted(by_dir.keys()):
        lines.append(f"📁 {dir_name}/")
        for file_path in by_dir[dir_name]:
            filename = Path(file_path).name
            structures = file_structures[file_path]
            compact = format_structure_compact(structures, max_items=8)
            lines.append(f"  {filename}: {compact}")

    return "\n".join(lines)
