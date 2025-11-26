"""C# code analyzer for extracting imports and entry points."""

import re
from pathlib import Path
from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class CSharpAnalyzer(BaseAnalyzer):
    """
    Analyzer for C# source files.

    Supports: .cs

    Layer 1 implementation (regex-based):
    - Import detection (using directives, static usings)
    - Entry point detection (Main methods, ASP.NET controllers)
    - File classification

    Layer 2 (tree-sitter): Not yet implemented - uses base class defaults
    """

    @classmethod
    def get_extensions(cls) -> list[str]:
        """C# file extensions."""
        return [".cs"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "C#"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip C# files that should not be analyzed.

        C#-specific skip patterns:
        - Skip designer files (*.Designer.cs, *.designer.cs)
        - Skip generated files (*.g.cs, *.generated.cs)
        - Skip XAML code-behind if generated (*.xaml.cs with matching .xaml)
        - bin/ and obj/ are already filtered by COMMON_SKIP_DIRS
        """
        filename = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # Skip designer files
        if '.designer.cs' in filename:
            return False

        # Skip generated files
        if filename.endswith('.g.cs') or filename.endswith('.generated.cs'):
            return False

        # Skip auto-generated AssemblyInfo files
        if filename == 'assemblyinfo.cs':
            return False

        # Skip bin/obj (should be caught by COMMON_SKIP_DIRS, but double-check)
        if '/bin/' in path_lower or '/obj/' in path_lower:
            return False

        return True

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract using directives from C# file.

        Patterns supported:
        - using System.Collections;
        - using System.Collections.Generic;
        - using static System.Math;
        - using Alias = System.Collections.Generic.List<int>;
        """
        imports = []

        # Pattern 1: Standard using directives
        # using System.Collections.Generic;
        using_pattern = r'^\s*using\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;'
        for match in re.finditer(using_pattern, content, re.MULTILINE):
            namespace = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=namespace,
                    line=line_num,
                    import_type="using",
                )
            )

        # Pattern 2: Static using directives
        # using static System.Math;
        static_using_pattern = r'^\s*using\s+static\s+([A-Za-z_][A-Za-z0-9_.]*)\s*;'
        for match in re.finditer(static_using_pattern, content, re.MULTILINE):
            namespace = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=namespace,
                    line=line_num,
                    import_type="static_using",
                )
            )

        # Pattern 3: Alias using directives
        # using MyList = System.Collections.Generic.List<int>;
        # Note: Allow full type syntax including generics with commas and spaces
        alias_using_pattern = r'^\s*using\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_.<>,\s]+?)\s*;'
        for match in re.finditer(alias_using_pattern, content, re.MULTILINE):
            alias = match.group(1)
            namespace = match.group(2)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=namespace,
                    line=line_num,
                    import_type="alias_using",
                    imported_names=[alias],
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in C# file.

        Entry points:
        - static void Main(string[] args)
        - static async Task Main(string[] args)
        - static int Main()
        - [ApiController] or [Controller] attributes (ASP.NET)
        - [HttpGet], [HttpPost], etc. (ASP.NET action methods)
        """
        entry_points = []

        # Pattern 1: Main methods (various signatures)
        # static void Main(), static int Main(string[] args), static async Task Main()
        main_patterns = [
            r'^\s*(?:public\s+|private\s+|internal\s+)?static\s+(?:async\s+)?(?:void|int|Task(?:<int>)?)\s+Main\s*\(',
        ]
        for pattern in main_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                line_num = content[:match.start()].count('\n') + 1
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="main_function",
                        line=line_num,
                        name="Main",
                    )
                )

        # Pattern 2: ASP.NET Controllers (class-level attributes)
        # [ApiController], [Controller]
        controller_pattern = r'^\s*\[(?:Api)?Controller\]'
        for match in re.finditer(controller_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1

            # Try to find the class name following the attribute
            remaining_content = content[match.end():]
            class_match = re.search(r'\s*(?:public\s+|internal\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)', remaining_content)
            class_name = class_match.group(1) if class_match else "Controller"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="controller",
                    line=line_num,
                    name=class_name,
                    framework="ASP.NET",
                )
            )

        # Pattern 3: ASP.NET Action methods (HTTP verb attributes)
        # [HttpGet], [HttpPost], [HttpPut], [HttpDelete], etc.
        http_verb_pattern = r'^\s*\[Http(?:Get|Post|Put|Delete|Patch|Head|Options)\]'
        for match in re.finditer(http_verb_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1

            # Try to find the method name following the attribute
            remaining_content = content[match.end():]
            method_match = re.search(
                r'\s*(?:public\s+|private\s+|protected\s+|internal\s+)?(?:async\s+)?(?:Task<?[^>]*>?|ActionResult<?[^>]*>?|IActionResult|[A-Za-z_][A-Za-z0-9_.<>]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(',
                remaining_content
            )
            method_name = method_match.group(1) if method_match else "ActionMethod"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="http_handler",
                    line=line_num,
                    name=method_name,
                    framework="ASP.NET",
                )
            )

        # Pattern 4: Startup class (ASP.NET Core convention)
        # public class Startup
        startup_pattern = r'^\s*(?:public\s+)?class\s+Startup\s*(?::|{)'
        for match in re.finditer(startup_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="startup_class",
                    line=line_num,
                    name="Startup",
                    framework="ASP.NET Core",
                )
            )

        # Pattern 5: Program class (ASP.NET Core 6+ minimal API)
        # Look for WebApplication.CreateBuilder or WebApplicationBuilder
        minimal_api_pattern = r'(?:WebApplication\.CreateBuilder|WebApplicationBuilder)'
        for match in re.finditer(minimal_api_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="minimal_api",
                    line=line_num,
                    name="Program",
                    framework="ASP.NET Core",
                )
            )
            break  # Only report once per file

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify C# file into architectural cluster.

        Uses base class heuristics plus C#-specific patterns.
        """
        # Use base class classification (handles common patterns like test_)
        base_cluster = super().classify_file(file_path, content)

        # C#-specific patterns
        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points (Program.cs, Startup.cs)
            if name in ["program.cs", "startup.cs"]:
                return "entry_points"

            # Check for Main method
            if re.search(r'^\s*static\s+(?:async\s+)?(?:void|int|Task)\s+Main\s*\(', content, re.MULTILINE):
                return "entry_points"

            # Controllers
            if "/controllers/" in path_lower or name.endswith("controller.cs"):
                return "core_logic"

            # ASP.NET Controller attribute
            if re.search(r'^\s*\[(?:Api)?Controller\]', content, re.MULTILINE):
                return "core_logic"

            # Models
            if "/models/" in path_lower or name.endswith("model.cs"):
                return "core_logic"

            # Services
            if "/services/" in path_lower or name.endswith("service.cs"):
                return "core_logic"

            # Repositories
            if "/repositories/" in path_lower or name.endswith("repository.cs"):
                return "core_logic"

            # Config files
            if name in ["appsettings.cs", "config.cs", "configuration.cs"]:
                return "config"

            # Extensions (helper methods)
            if name.endswith("extensions.cs"):
                return "utilities"

            # Tests (NUnit, xUnit, MSTest patterns)
            if "test" in name or "/tests/" in path_lower:
                return "tests"

        return base_cluster
