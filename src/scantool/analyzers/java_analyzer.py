"""Java code analyzer for extracting imports and entry points."""

import re
from pathlib import Path
from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class JavaAnalyzer(BaseAnalyzer):
    """
    Analyzer for Java source files.

    Supports: .java

    Layer 1 implementation (regex-based):
    - Import detection (single + static imports)
    - Entry point detection (main method, Spring, Servlet annotations)
    - File classification

    Layer 2 (tree-sitter): Not yet implemented - uses base class defaults
    """

    @classmethod
    def get_extensions(cls) -> list[str]:
        """Java file extensions."""
        return [".java"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "Java"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip Java files that should not be analyzed.

        Java doesn't have many common generated file patterns like Go/Rust.
        Most generated code (like Lombok, annotation processors) is still
        valid for analysis. We skip nothing specific at this tier.

        build/ and target/ directories are already filtered by COMMON_SKIP_DIRS.
        """
        return True

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract import statements from Java file.

        Patterns supported:
        - import foo.bar.Baz;
        - import foo.bar.*;
        - import static foo.bar.Utils.*;
        - import static foo.bar.Utils.method;
        """
        imports = []

        # Pattern 1: Regular imports (import foo.bar.Baz;)
        # Matches: import foo.bar.Baz;
        # Matches: import foo.bar.*;
        regular_import_pattern = r'^\s*import\s+(?!static\s)([a-zA-Z_$][a-zA-Z0-9_.$*]*)\s*;'
        for match in re.finditer(regular_import_pattern, content, re.MULTILINE):
            package = match.group(1).strip()
            line_num = content[:match.start()].count('\n') + 1

            # Determine if wildcard import
            import_type = "wildcard" if package.endswith(".*") else "import"

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=package,
                    line=line_num,
                    import_type=import_type,
                )
            )

        # Pattern 2: Static imports (import static foo.bar.Utils.*;)
        # Matches: import static foo.bar.Utils.*;
        # Matches: import static foo.bar.Utils.method;
        static_import_pattern = r'^\s*import\s+static\s+([a-zA-Z_$][a-zA-Z0-9_.$*]*)\s*;'
        for match in re.finditer(static_import_pattern, content, re.MULTILINE):
            package = match.group(1).strip()
            line_num = content[:match.start()].count('\n') + 1

            # Extract class and member if possible
            # foo.bar.Utils.method -> Utils.method
            # foo.bar.Utils.* -> Utils.*
            parts = package.split('.')
            if len(parts) >= 2:
                imported_name = f"{parts[-2]}.{parts[-1]}"
            else:
                imported_name = package

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=package,
                    line=line_num,
                    import_type="static",
                    imported_names=[imported_name],
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in Java file.

        Entry points:
        - public static void main(String[] args)
        - @SpringBootApplication (Spring Boot entry)
        - @WebServlet (Servlet entry)
        - @RestController (Spring REST API)
        - @Controller (Spring MVC)
        """
        entry_points = []

        # Pattern 1: public static void main(String[] args)
        # Handles variations:
        # - public static void main(String[] args)
        # - public static void main(String args[])
        # - public static void main(String... args)
        main_pattern = r'public\s+static\s+void\s+main\s*\(\s*String\s*(?:\[\s*\]\s*\w+|\w+\s*\[\s*\]|\.{3}\s*\w+)\s*\)'
        for match in re.finditer(main_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Extract class name from file path
            class_name = Path(file_path).stem

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_method",
                    line=line_num,
                    name=f"{class_name}.main",
                )
            )

        # Pattern 2: @SpringBootApplication
        spring_boot_pattern = r'@SpringBootApplication'
        for match in re.finditer(spring_boot_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Find class name after annotation
            class_pattern = r'class\s+(\w+)'
            class_match = re.search(class_pattern, content[match.end():])
            class_name = class_match.group(1) if class_match else "Unknown"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="spring_boot_app",
                    line=line_num,
                    name=class_name,
                    framework="Spring Boot",
                )
            )

        # Pattern 3: @WebServlet
        # Matches: @WebServlet("/path")
        # Matches: @WebServlet(name = "MyServlet", urlPatterns = {"/path"})
        servlet_pattern = r'@WebServlet\s*(?:\([^)]*\))?'
        for match in re.finditer(servlet_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Extract servlet URL pattern if present
            url_match = re.search(r'[@(].*["\']([^"\']+)["\']', match.group(0))
            url_pattern = url_match.group(1) if url_match else None

            # Find class name after annotation
            class_pattern = r'class\s+(\w+)'
            class_match = re.search(class_pattern, content[match.end():])
            class_name = class_match.group(1) if class_match else "Unknown"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="servlet",
                    line=line_num,
                    name=f"{class_name}:{url_pattern}" if url_pattern else class_name,
                    framework="Servlet",
                )
            )

        # Pattern 4: @RestController (Spring REST API)
        rest_controller_pattern = r'@RestController'
        for match in re.finditer(rest_controller_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Find class name
            class_pattern = r'class\s+(\w+)'
            class_match = re.search(class_pattern, content[match.end():])
            class_name = class_match.group(1) if class_match else "Unknown"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="rest_controller",
                    line=line_num,
                    name=class_name,
                    framework="Spring",
                )
            )

        # Pattern 5: @Controller (Spring MVC)
        controller_pattern = r'@Controller\b'
        for match in re.finditer(controller_pattern, content):
            line_num = content[:match.start()].count('\n') + 1

            # Find class name
            class_pattern = r'class\s+(\w+)'
            class_match = re.search(class_pattern, content[match.end():])
            class_name = class_match.group(1) if class_match else "Unknown"

            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="controller",
                    line=line_num,
                    name=class_name,
                    framework="Spring",
                )
            )

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify Java file into architectural cluster.

        Uses base class heuristics plus Java-specific patterns.
        """
        # Use base class classification first
        base_cluster = super().classify_file(file_path, content)

        # Java-specific patterns
        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points - check by annotation or main method
            if any(
                pattern in content
                for pattern in [
                    "@SpringBootApplication",
                    "public static void main",
                    "@WebServlet",
                ]
            ):
                return "entry_points"

            # Controllers and REST APIs
            if any(
                pattern in content
                for pattern in ["@RestController", "@Controller", "@WebServlet"]
            ):
                return "core_logic"

            # Test files - various test frameworks
            if (
                "Test" in Path(file_path).stem
                or name.startswith("test")
                or name.endswith("test.java")
                or "@Test" in content
                or "@junit" in content.lower()
                or "import org.junit" in content
                or "import org.testng" in content
            ):
                return "tests"

            # Models/Entities/DTOs
            if (
                "/models/" in path_lower
                or "/entities/" in path_lower
                or "/dto/" in path_lower
                or "@Entity" in content
                or "@Table" in content
            ):
                return "core_logic"

            # Services
            if "/services/" in path_lower or "@Service" in content:
                return "core_logic"

            # Repositories/DAOs
            if (
                "/repositories/" in path_lower
                or "/dao/" in path_lower
                or "@Repository" in content
            ):
                return "core_logic"

            # Configuration
            if (
                "/config/" in path_lower
                or name.endswith("config.java")
                or name.endswith("configuration.java")
                or "@Configuration" in content
            ):
                return "config"

        return base_cluster
