"""Swift code analyzer for extracting imports and entry points."""

import re
from pathlib import Path
from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class SwiftAnalyzer(BaseAnalyzer):
    """
    Analyzer for Swift source files.

    Supports: .swift

    Layer 1 implementation (regex-based):
    - Import detection (regular, @testable, selective)
    - Entry point detection (@main, main.swift, AppDelegate, etc.)
    - File classification

    Layer 2 (tree-sitter): Not yet implemented - uses base class defaults
    """

    @classmethod
    def get_extensions(cls) -> list[str]:
        """Swift file extensions."""
        return [".swift"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "Swift"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip Swift files that should not be analyzed.

        Swift-specific skip patterns:
        - Skip test files (*Tests.swift, *Test.swift) - analyzed separately
        - Skip generated files (*.generated.swift)
        - Skip Package.swift in nested directories (SPM packages)
        """
        filename = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # Skip test files (separate cluster)
        if filename.endswith('tests.swift') or filename.endswith('test.swift'):
            return True  # Keep tests, but classify separately

        # Skip generated files
        if '.generated.swift' in filename or 'generated' in filename:
            return False

        # Skip Pods directory (CocoaPods)
        if '/pods/' in path_lower:
            return False

        # Skip Carthage checkouts
        if '/carthage/checkouts/' in path_lower:
            return False

        # Skip build directories
        if '/.build/' in path_lower or '/deriveddata/' in path_lower:
            return False

        return True

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract import statements from Swift file.

        Patterns supported:
        - import ModuleName
        - @testable import ModuleName
        - import struct/class/enum/protocol ModuleName.TypeName
        - import func ModuleName.functionName
        """
        imports = []

        # Pattern 1: Regular import and @testable import
        # import Foundation
        # @testable import MyModule
        import_pattern = r'^(?:@testable\s+)?import\s+(?:(?:struct|class|enum|protocol|func|typealias|var|let)\s+)?([^\s;]+)'

        for match in re.finditer(import_pattern, content, re.MULTILINE):
            module = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            is_testable = '@testable' in match.group(0)

            # Handle selective imports like: import struct CoreGraphics.CGPoint
            import_type = "import"
            if '@testable' in match.group(0):
                import_type = "@testable import"

            # Check for specific symbol imports
            selective_match = re.search(r'import\s+(struct|class|enum|protocol|func|typealias|var|let)\s+', match.group(0))
            if selective_match:
                import_type = f"import {selective_match.group(1)}"

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=module,
                    line=line_num,
                    import_type=import_type,
                    imported_names=None,
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in Swift file.

        Entry points:
        - @main attribute on struct/class/enum
        - main.swift file (Swift Package Manager)
        - @UIApplicationMain / @NSApplicationMain (deprecated but still used)
        - AppDelegate class
        - App struct conforming to SwiftUI App protocol
        """
        entry_points = []
        filename = Path(file_path).name.lower()

        # Pattern 1: @main attribute
        main_attr_pattern = r'@main\s+(?:public\s+|internal\s+|private\s+|fileprivate\s+)*(?:struct|class|enum)\s+(\w+)'
        for match in re.finditer(main_attr_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_type",
                    line=line_num,
                    name=match.group(1),
                )
            )

        # Pattern 2: @UIApplicationMain / @NSApplicationMain (deprecated)
        app_main_pattern = r'@(?:UIApplicationMain|NSApplicationMain)\s+(?:public\s+|internal\s+|private\s+)*class\s+(\w+)'
        for match in re.finditer(app_main_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            attr = '@UIApplicationMain' if '@UIApplicationMain' in match.group(0) else '@NSApplicationMain'
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="app_delegate",
                    line=line_num,
                    name=match.group(1),
                )
            )

        # Pattern 3: main.swift file (SPM entry point)
        if filename == 'main.swift':
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_file",
                    line=1,
                    name="main.swift",
                )
            )

        # Pattern 4: AppDelegate class
        app_delegate_pattern = r'class\s+(AppDelegate|ApplicationDelegate)\s*:\s*(?:\w+,\s*)*(?:UIResponder|NSObject)'
        for match in re.finditer(app_delegate_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="app_delegate",
                    line=line_num,
                    name=match.group(1),
                )
            )

        # Pattern 5: SwiftUI App protocol conformance
        # struct MyApp: App { ... }
        swiftui_app_pattern = r'(?:struct|class)\s+(\w+)\s*:\s*(?:\w+,\s*)*App\s*\{'
        for match in re.finditer(swiftui_app_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            # Check if already detected via @main
            if not any(ep.name == match.group(1) and ep.type == "main_type" for ep in entry_points):
                entry_points.append(
                    EntryPointInfo(
                        file=file_path,
                        type="swiftui_app",
                        line=line_num,
                        name=match.group(1),
                    )
                )

        # Pattern 6: SceneDelegate
        scene_delegate_pattern = r'class\s+(SceneDelegate)\s*:\s*(?:\w+,\s*)*(?:UIResponder|NSObject)'
        for match in re.finditer(scene_delegate_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="scene_delegate",
                    line=line_num,
                    name=match.group(1),
                )
            )

        # Pattern 7: XCTestCase subclasses
        test_case_pattern = r'class\s+(\w+)\s*:\s*XCTestCase'
        for match in re.finditer(test_case_pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="test_case",
                    line=line_num,
                    name=match.group(1),
                )
            )

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify Swift file into architectural cluster.

        Uses base class heuristics plus Swift-specific patterns.
        """
        # Use base class classification (handles common patterns)
        base_cluster = super().classify_file(file_path, content)

        # Swift-specific patterns
        if base_cluster == "other":
            name = Path(file_path).name.lower()
            path_lower = file_path.lower()

            # Entry points
            if name == "main.swift":
                return "entry_points"
            if name in ("appdelegate.swift", "scenedelegate.swift"):
                return "entry_points"

            # Check for @main attribute
            if re.search(r'@main\s+(?:struct|class|enum)', content):
                return "entry_points"

            # Check for SwiftUI App
            if re.search(r'(?:struct|class)\s+\w+\s*:\s*(?:\w+,\s*)*App\s*\{', content):
                return "entry_points"

            # Test files
            if name.endswith('tests.swift') or name.endswith('test.swift'):
                return "tests"
            if 'xctest' in content.lower():
                return "tests"

            # Config files
            if name == "package.swift":
                return "config"
            if name in ("config.swift", "settings.swift", "constants.swift"):
                return "config"

            # ViewControllers
            if "viewcontroller" in name or "/viewcontrollers/" in path_lower:
                return "core_logic"

            # Views (SwiftUI and UIKit)
            if name.endswith("view.swift") or "/views/" in path_lower:
                return "core_logic"

            # Models
            if "/models/" in path_lower or name.endswith("model.swift"):
                return "core_logic"

            # ViewModels
            if "/viewmodels/" in path_lower or name.endswith("viewmodel.swift"):
                return "core_logic"

            # Services
            if "/services/" in path_lower or name.endswith("service.swift"):
                return "core_logic"

            # Managers
            if name.endswith("manager.swift") or "/managers/" in path_lower:
                return "core_logic"

            # Extensions (utility code)
            if name.endswith("+extension.swift") or "/extensions/" in path_lower:
                return "other"

            # Protocols
            if name.endswith("protocol.swift") or "/protocols/" in path_lower:
                return "core_logic"

        return base_cluster
