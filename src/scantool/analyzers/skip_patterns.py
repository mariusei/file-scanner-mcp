"""Common skip patterns for file discovery and analysis.

This module defines noise patterns that should be excluded during code analysis:
- Build artifacts
- Package manager caches
- Virtual environments
- Git internals
- IDE/editor files
"""

# Directory patterns to skip (applies to all languages)
COMMON_SKIP_DIRS = {
    # Version control
    ".git",
    ".svn",
    ".hg",

    # Package managers
    "node_modules",
    "bower_components",
    "vendor",

    # Python
    "__pycache__",
    ".venv",
    ".virtualenv",
    "venv",
    "virtualenv",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",

    # Build outputs
    "dist",
    "build",
    "out",
    "target",  # Rust, Java
    "bin",
    "obj",

    # Coverage
    "coverage",
    ".coverage",
    "htmlcov",
    ".nyc_output",

    # Frontend frameworks
    ".next",
    ".nuxt",
    ".output",
    ".cache",

    # IDEs
    ".idea",
    ".vscode",
    ".vs",

    # macOS
    ".DS_Store",
}

# File patterns to skip (applies to all languages)
COMMON_SKIP_FILES = {
    ".DS_Store",
    "Thumbs.db",
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
    ".gitkeep",
    ".npmignore",
    ".dockerignore",
}

# File extensions to skip (applies to all languages)
COMMON_SKIP_EXTENSIONS = {
    ".pyc",  # Python compiled
    ".pyo",  # Python optimized
    ".pyd",  # Python DLL
    ".so",   # Shared object (compiled)
    ".dylib",  # macOS dynamic library
    ".dll",  # Windows DLL
    ".exe",  # Windows executable
    ".bin",  # Binary
    ".o",    # Object file
    ".a",    # Static library
    ".lock", # Lock files (package-lock.json handled by exact match)
}


def should_skip_directory(dir_name: str) -> bool:
    """
    Check if directory should be skipped during discovery.

    Args:
        dir_name: Directory name (not full path)

    Returns:
        True if directory should be skipped
    """
    return dir_name in COMMON_SKIP_DIRS


def should_skip_file(file_name: str) -> bool:
    """
    Check if file should be skipped during discovery.

    Checks both exact filename matches and file extensions.

    Args:
        file_name: File name (not full path)

    Returns:
        True if file should be skipped
    """
    # Check exact filename match
    if file_name in COMMON_SKIP_FILES:
        return True

    # Check file extension
    from pathlib import Path
    ext = Path(file_name).suffix.lower()
    if ext in COMMON_SKIP_EXTENSIONS:
        return True

    return False
