"""TypeScript/JavaScript code analyzer for extracting imports and entry points."""

import re
from pathlib import Path
from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class TypeScriptAnalyzer(BaseAnalyzer):
    """
    Analyzer for TypeScript and JavaScript source files.

    Supports: .ts, .tsx, .mts, .cts, .js, .jsx, .mjs, .cjs

    Layer 1 implementation (regex-based):
    - Import/export detection
    - Entry point detection (main exports, app instances)
    - File classification

    Layer 2 (tree-sitter): Not yet implemented - uses base class defaults (empty lists)
    """

    @classmethod
    def get_extensions(cls) -> list[str]:
        """TypeScript and JavaScript file extensions."""
        return [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "TypeScript/JavaScript"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip TypeScript/JavaScript files that should not be analyzed.

        Matches TypeScriptScanner.should_skip() logic:
        - Skip minified files (.min.js, .min.mjs, .min.cjs)
        - Skip TypeScript declaration files (.d.ts) - type-only, no implementation
        - Skip webpack/rollup bundles (bundle/chunk in filename)
        - node_modules is already filtered by COMMON_SKIP_DIRS
        """
        filename = Path(file_path).name.lower()

        # Skip minified files
        if filename.endswith(('.min.js', '.min.mjs', '.min.cjs')):
            return False

        # Skip TypeScript declaration files
        if filename.endswith('.d.ts'):
            return False

        # Skip webpack/rollup bundles
        if 'bundle' in filename or 'chunk' in filename:
            return False

        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """
        Identify low-value TypeScript/JavaScript files for inventory listing.

        Low-value files (unless central):
        - index.ts/index.js that only re-export (small size)
        - Type declaration files (.d.ts) - already skipped by should_analyze
        - Config files (vite.config.ts, etc.) unless large
        - Test setup files (setupTests.ts, etc.)
        """
        filename = Path(file_path).name.lower()

        # Small index files are usually just re-exports
        if filename in ("index.ts", "index.js", "index.tsx", "index.jsx") and size < 200:
            return True

        # Test setup files
        if filename in ("setuptests.ts", "setuptests.js", "jest.setup.ts", "jest.setup.js") and size < 300:
            return True

        # Very small config files
        config_files = ("vite.config.ts", "vitest.config.ts", "jest.config.ts",
                       "tsconfig.json", "tsconfig.node.json")
        if filename in config_files and size < 500:
            return True

        # Fall back to base class
        return super().is_low_value_for_inventory(file_path, size)

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract import/require statements from TypeScript/JavaScript file.

        Patterns supported:
        - import x from 'module'
        - import { x, y } from 'module'
        - import * as x from 'module'
        - const x = require('module')
        - export { x } from 'module'
        - import('module') (dynamic import)
        """
        imports = []

        # Pattern 1: import ... from 'module'
        import_from_pattern = r'^\s*import\s+(?:(?:\{[^}]+\}|\*\s+as\s+\w+|\w+)(?:\s*,\s*\{[^}]+\})?)\s+from\s+[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(import_from_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            # Determine if relative import
            is_relative = module.startswith('./')
            import_type = "relative" if is_relative else "es6_import"

            # Resolve relative imports
            target_module = module
            if is_relative:
                resolved = self._resolve_relative_import(file_path, module)
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

        # Pattern 2: import 'module' (side-effect import)
        import_pattern = r'^\s*import\s+[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(import_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            is_relative = module.startswith('./')
            import_type = "relative" if is_relative else "es6_import"

            target_module = module
            if is_relative:
                resolved = self._resolve_relative_import(file_path, module)
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

        # Pattern 3: require('module')
        require_pattern = r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
        for match in re.finditer(require_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            is_relative = module.startswith('./')
            import_type = "relative" if is_relative else "require"

            target_module = module
            if is_relative:
                resolved = self._resolve_relative_import(file_path, module)
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

        # Pattern 4: export ... from 'module'
        export_from_pattern = r'^\s*export\s+(?:\{[^}]+\}|\*(?:\s+as\s+\w+)?)\s+from\s+[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(export_from_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            is_relative = module.startswith('./')
            import_type = "relative" if is_relative else "export_from"

            target_module = module
            if is_relative:
                resolved = self._resolve_relative_import(file_path, module)
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

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in TypeScript/JavaScript file.

        Entry points:
        - export default (main export)
        - Framework app instances (Express, Fastify, Next.js, etc.)
        - export { ... } with main exports
        """
        entry_points = []

        # Pattern 1: export default
        default_export_pattern = r'^\s*export\s+default\s+(\w+)'
        for match in re.finditer(default_export_pattern, content, re.MULTILINE):
            name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="export",
                    line=line_num,
                    name=name,
                )
            )

        # Pattern 2: Framework app instances
        # Express: const app = express()
        # Fastify: const app = fastify()
        # Next.js: export default function App()
        framework_patterns = [
            (r'const\s+(\w+)\s*=\s*express\s*\(', "Express"),
            (r'const\s+(\w+)\s*=\s*fastify\s*\(', "Fastify"),
            (r'const\s+(\w+)\s*=\s*new\s+Hono\s*\(', "Hono"),
            (r'export\s+default\s+function\s+(\w+)\s*\(', "React/Next.js"),
        ]

        for pattern, framework in framework_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                name = match.group(1)
                line_num = content[:match.start()].count('\n') + 1
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="app_instance",
                        line=line_num,
                        name=name,
                        framework=framework,
                    )
                )

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify TypeScript/JavaScript file into architectural cluster.

        Uses base class heuristics plus TypeScript-specific patterns.
        """
        # Use base class classification (handles common patterns)
        base_cluster = super().classify_file(file_path, content)

        # TypeScript-specific patterns
        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points
            if name in ["index.ts", "index.tsx", "main.ts", "app.ts", "app.tsx", "server.ts"]:
                return "entry_points"

            # Config
            if name in ["config.ts", "settings.ts", "env.ts"]:
                return "config"

            # Types
            if "/types/" in path_lower or name.endswith(".types.ts"):
                return "utilities"

            # Components (React/Vue)
            if "/components/" in path_lower:
                return "core_logic"

            # Routes/Controllers
            if "/routes/" in path_lower or "/controllers/" in path_lower:
                return "core_logic"

        return base_cluster
