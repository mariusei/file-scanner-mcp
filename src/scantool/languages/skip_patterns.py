"""Skip patterns for file discovery and analysis.

Organized by category for maintainability. Each category can be
independently toggled or extended.

Categories:
- VERSION_CONTROL: Git, SVN, Mercurial internals
- IDE_DIRS: Editor/IDE configuration
- PYTHON_DIRS: Python-specific artifacts and environments
- NODE_DIRS: Node.js/JavaScript ecosystem
- DOTNET_DIRS: .NET/C# artifacts
- JAVA_DIRS: Java/Kotlin/Gradle/Maven
- RUST_DIRS: Rust/Cargo artifacts
- GO_DIRS: Go modules and vendor
- RUBY_DIRS: Ruby/Bundler
- PHP_DIRS: PHP/Composer
- BUILD_DIRS: Generic build outputs
- CACHE_DIRS: Various tool caches
- COVERAGE_DIRS: Test coverage outputs
- FRONTEND_DIRS: Frontend framework outputs
"""

# =============================================================================
# DIRECTORY PATTERNS BY CATEGORY
# =============================================================================

# Version control internals
VERSION_CONTROL_DIRS = {
    ".git",
    ".svn",
    ".hg",
    ".fossil",
}

# IDE/Editor configuration
IDE_DIRS = {
    ".idea",      # JetBrains
    ".vscode",    # VS Code
    ".vs",        # Visual Studio
    ".eclipse",   # Eclipse
    ".settings",  # Eclipse
}

# Python
PYTHON_DIRS = {
    "__pycache__",
    ".venv",
    ".virtualenv",
    "venv",
    "virtualenv",
    ".python_packages",  # Azure Functions
    "site-packages",     # Installed packages
    ".eggs",
    ".pixi",             # Pixi package manager
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".ipynb_checkpoints",
}

# Node.js / JavaScript / TypeScript
NODE_DIRS = {
    "node_modules",
    "bower_components",
    ".npm",
    ".yarn",
    ".pnpm-store",
}

# .NET / C#
DOTNET_DIRS = {
    "bin",
    "obj",
    "packages",      # NuGet (legacy)
    ".nuget",
}

# Java / Kotlin / Scala
JAVA_DIRS = {
    "target",        # Maven
    ".gradle",
    ".m2",           # Maven local repo
    "build",         # Gradle
}

# Rust
RUST_DIRS = {
    "target",        # Cargo build output
    ".cargo",        # Cargo cache
}

# Go
GO_DIRS = {
    "vendor",        # Go vendor (also used by PHP)
}

# Ruby
RUBY_DIRS = {
    ".bundle",
    "vendor/bundle",
}

# PHP
PHP_DIRS = {
    "vendor",        # Composer (shared with Go)
}

# Generic build outputs
BUILD_DIRS = {
    "dist",
    "build",
    "out",
    "_build",        # Elixir, some C projects
    "release",
}

# Cache directories
CACHE_DIRS = {
    ".cache",
    ".parcel-cache",
    ".turbo",
    ".nx",
}

# Test coverage
COVERAGE_DIRS = {
    "coverage",
    ".coverage",
    "htmlcov",
    ".nyc_output",
    "lcov-report",
}

# Frontend frameworks
FRONTEND_DIRS = {
    ".next",         # Next.js
    ".nuxt",         # Nuxt.js
    ".output",       # Nuxt 3
    ".svelte-kit",   # SvelteKit
    ".angular",      # Angular
    ".expo",         # Expo (React Native)
}

# OS-specific
OS_DIRS = {
    ".DS_Store",     # macOS
    ".Trash-*",      # Linux trash
}

# =============================================================================
# COMBINED SETS (for convenience)
# =============================================================================

# All directory patterns combined
COMMON_SKIP_DIRS = (
    VERSION_CONTROL_DIRS
    | IDE_DIRS
    | PYTHON_DIRS
    | NODE_DIRS
    | DOTNET_DIRS
    | JAVA_DIRS
    | RUST_DIRS
    | GO_DIRS
    | RUBY_DIRS
    | PHP_DIRS
    | BUILD_DIRS
    | CACHE_DIRS
    | COVERAGE_DIRS
    | FRONTEND_DIRS
    | OS_DIRS
)

# =============================================================================
# FILE PATTERNS
# =============================================================================

# Exact filenames to skip
COMMON_SKIP_FILES = {
    # OS
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    # Git
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
    ".gitkeep",
    # Other VCS
    ".hgignore",
    # Package managers
    ".npmignore",
    ".dockerignore",
    ".prettierignore",
    ".eslintignore",
}

# File extensions to skip (compiled/binary)
COMMON_SKIP_EXTENSIONS = {
    # Python compiled
    ".pyc",
    ".pyo",
    ".pyd",
    # Native compiled
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".o",
    ".a",
    ".lib",
    # Lock files
    ".lock",
    # Other binary
    ".class",    # Java compiled
    ".jar",      # Java archive
    ".war",      # Java web archive
    ".wasm",     # WebAssembly
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

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
