"""PHP code analyzer for extracting imports, entry points, and structure."""

import re
from pathlib import Path
from typing import Optional

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class PHPAnalyzer(BaseAnalyzer):
    """
    Analyzer for PHP source files (.php, .phtml).

    Layer 1 implementation (regex-based):
    - Import/require detection (use statements, require, include)
    - Entry point detection (index.php, Laravel routes, Symfony controllers)
    - File classification

    Layer 2: Not implemented - uses base class defaults (empty lists)
    """

    @classmethod
    def get_extensions(cls) -> list[str]:
        """PHP file extensions."""
        return [".php", ".phtml"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "PHP"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip PHP files that should not be analyzed.

        - Skip Blade cached files in Laravel storage/framework/views
        - Skip compiled PHP files (.phps is actually for syntax highlighting, not executable)
        """
        path_lower = file_path.lower()

        # Skip Laravel Blade cache files
        if 'storage/framework/views' in path_lower:
            return False

        return True

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract imports from PHP file.

        Patterns supported:
        - use Foo\\Bar\\Baz;
        - use Foo\\Bar\\Baz as Alias;
        - use Foo\\Bar\\{ClassA, ClassB};
        - require 'path/to/file.php';
        - require_once 'path/to/file.php';
        - include 'path/to/file.php';
        - include_once 'path/to/file.php';
        """
        imports = []

        # Pattern 1: use statements (namespace imports)
        # use Foo\Bar\Baz;
        # use Foo\Bar\Baz as Alias;
        use_pattern = r'^\s*use\s+([\w\\]+)(?:\s+as\s+\w+)?\s*;'
        for match in re.finditer(use_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type="use",
                )
            )

        # Pattern 2: grouped use statements
        # use Foo\Bar\{ClassA, ClassB, ClassC};
        grouped_use_pattern = r'^\s*use\s+([\w\\]+)\s*\{([^}]+)\}\s*;'
        for match in re.finditer(grouped_use_pattern, content, re.MULTILINE):
            base_namespace = match.group(1).rstrip('\\')  # Remove trailing backslash
            grouped_items_str = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            # Parse grouped items
            items = [item.strip() for item in grouped_items_str.split(',') if item.strip()]

            for item in items:
                # Remove 'as Alias' if present
                if ' as ' in item:
                    item = item.split(' as ')[0].strip()

                # Construct full namespace
                full_namespace = f"{base_namespace}\\{item}"

                imports.append(
                    ImportInfo(
                        source_file=file_path,
                        target_module=full_namespace,
                        line=line_num,
                        import_type="use_grouped",
                    )
                )

        # Pattern 3: require/include statements
        # require 'path/to/file.php';
        # require_once 'path/to/file.php';
        # include 'path/to/file.php';
        # include_once 'path/to/file.php';
        require_pattern = r'(require|require_once|include|include_once)\s*[\(\s]+[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(require_pattern, content, re.MULTILINE):
            keyword = match.group(1)
            file_path_str = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            # Determine if relative import
            is_relative = file_path_str.startswith(('./', '../', './'))
            import_type = f"{keyword}_relative" if is_relative else keyword

            # Resolve relative paths
            target_module = file_path_str
            if is_relative:
                resolved = self._resolve_relative_import(file_path, file_path_str)
                if resolved:
                    target_module = resolved

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=target_module,
                    line=line_num,
                    import_type=import_type,
                )
            )

        # Pattern 4: use function statements
        # use function App\Utils\validateEmail;
        use_function_pattern = r'^\s*use\s+function\s+([\w\\]+)\s*;'
        for match in re.finditer(use_function_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type="use_function",
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in PHP file.

        Entry points:
        - index.php files
        - Laravel Route::get/post/etc definitions
        - Symfony controller classes (class name ends with Controller)
        - public function __invoke() (single-action controllers)
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        # Pattern 1: index.php files
        if filename == "index.php":
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="entry_file",
                    name="index.php",
                    line=1,
                )
            )

        # Pattern 2: Laravel routes
        # Route::get('/path', ...);
        # Route::post('/path', ...);
        # Route::put('/path', ...);
        # Route::delete('/path', ...);
        # Route::patch('/path', ...);
        # Route::any('/path', ...);
        route_pattern = r'Route::(get|post|put|delete|patch|any|resource|group)\s*\(\s*[\'"]([^\'"]*)[\'"]'
        for match in re.finditer(route_pattern, content):
            method = match.group(1)
            route_path = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="route",
                    name=f"{method.upper()} {route_path}",
                    line=line_num,
                    framework="Laravel",
                )
            )

        # Pattern 3: Symfony/Laravel controllers
        # class UserController extends Controller
        # class SomethingController
        controller_pattern = r'^\s*(?:final\s+)?class\s+(\w*Controller)\s*(?:extends|implements|\{)'
        for match in re.finditer(controller_pattern, content, re.MULTILINE):
            controller_name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="controller",
                    name=controller_name,
                    line=line_num,
                )
            )

        # Pattern 4: Single-action controllers (__invoke)
        invoke_pattern = r'^\s*public\s+function\s+__invoke\s*\('
        for match in re.finditer(invoke_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="invokable",
                    name="__invoke",
                    line=line_num,
                )
            )

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify PHP file into architectural cluster.

        Uses base class heuristics plus PHP-specific patterns.
        """
        name = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # PHP-specific patterns (check these FIRST before base class)
        # Order matters! More specific patterns should come first

        # Views/Templates (check before index.php to avoid false positives)
        if "views/" in path_lower or "templates/" in path_lower or name.endswith(".blade.php"):
            return "presentation"

        # Config
        if "config/" in path_lower or name.startswith("config."):
            return "config"

        # Tests (check before other patterns)
        if "tests/" in path_lower or name.endswith("test.php"):
            return "tests"

        # Migrations/Seeders
        if "migrations/" in path_lower or "seeders/" in path_lower:
            return "database"

        # Entry points
        if name == "index.php":
            return "entry_points"

        # Controllers
        if "controllers/" in path_lower or name.endswith("controller.php"):
            return "entry_points"

        # Routes
        if "routes/" in path_lower or name in ["web.php", "api.php", "console.php"]:
            return "entry_points"

        # Models
        if "models/" in path_lower or "entities/" in path_lower:
            return "core_logic"

        # Services
        if "services/" in path_lower or name.endswith("service.php"):
            return "core_logic"

        # Middleware
        if "middleware/" in path_lower:
            return "core_logic"

        # Use base class classification for remaining patterns (utilities, etc.)
        return super().classify_file(file_path, content)
