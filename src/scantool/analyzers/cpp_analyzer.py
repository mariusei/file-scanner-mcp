"""C/C++ code analyzer for extracting imports and entry points."""

import re
from pathlib import Path
from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo


class CppAnalyzer(BaseAnalyzer):
    """
    Analyzer for C/C++ source files.

    Supports: .c, .cc, .cpp, .cxx, .h, .hpp, .hh, .hxx

    Layer 1 implementation (regex-based):
    - Import detection (#include statements - local and system)
    - Entry point detection (main functions)
    - File classification
    - Skip generated files (protobuf, Qt, etc.)

    Layer 2 (tree-sitter): Not yet implemented - uses base class defaults
    """

    @classmethod
    def get_extensions(cls) -> list[str]:
        """C/C++ file extensions."""
        return [".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".hxx"]

    @classmethod
    def get_language_name(cls) -> str:
        """Return language name."""
        return "C++"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority."""
        return 10

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip C/C++ files that should not be analyzed.

        C/C++-specific skip patterns:
        - Skip protobuf generated files (*.pb.h, *.pb.cc)
        - Skip Qt generated files (moc_*.cpp, ui_*.h, qrc_*.cpp)
        - Skip other generated files (*.gen.h, *.gen.cpp)
        """
        filename = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # Skip protobuf generated files
        if filename.endswith('.pb.h') or filename.endswith('.pb.cc') or filename.endswith('.pb.cpp'):
            return False

        # Skip Qt meta-object compiler generated files
        if filename.startswith('moc_') and (filename.endswith('.cpp') or filename.endswith('.h')):
            return False

        # Skip Qt UI generated files
        if filename.startswith('ui_') and filename.endswith('.h'):
            return False

        # Skip Qt resource compiler generated files
        if filename.startswith('qrc_') and filename.endswith('.cpp'):
            return False

        # Skip other generated files
        if filename.endswith('.gen.h') or filename.endswith('.gen.cpp'):
            return False

        # Skip if "generated" is in filename
        if 'generated' in filename and not 'generator' in filename:
            return False

        # Skip build directories (should be caught by tier 1, but double-check)
        if '/build/' in path_lower or '/cmake-build-' in path_lower:
            return False

        return True

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract #include statements from C/C++ file.

        Patterns supported:
        - #include "local.h" (local includes)
        - #include <system.h> (system includes)
        - # include (with space)
        - Handles multi-line includes with backslash continuation
        """
        imports = []

        # Pattern 1: Local includes - #include "file.h"
        local_include_pattern = r'^\s*#\s*include\s+"([^"]+)"'
        for match in re.finditer(local_include_pattern, content, re.MULTILINE):
            header = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=header,
                    line=line_num,
                    import_type="local",
                )
            )

        # Pattern 2: System includes - #include <file.h>
        system_include_pattern = r'^\s*#\s*include\s+<([^>]+)>'
        for match in re.finditer(system_include_pattern, content, re.MULTILINE):
            header = match.group(1)
            line_num = content[:match.start()].count('\n') + 1

            imports.append(
                ImportInfo(
                    source_file=file_path,
                    target_module=header,
                    line=line_num,
                    import_type="system",
                )
            )

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in C/C++ file.

        Entry points:
        - int main()
        - int main(int argc, char** argv)
        - int main(int argc, char* argv[])
        - void main() (non-standard but sometimes used)
        - WinMain for Windows applications
        """
        entry_points = []

        # Pattern 1: Standard main function
        # Matches: int main(), int main(void), int main(int argc, char** argv), etc.
        main_pattern = r'^\s*(?:extern\s+)?(?:int|void)\s+main\s*\('
        for match in re.finditer(main_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="main_function",
                    line=line_num,
                    name="main",
                )
            )

        # Pattern 2: WinMain (Windows entry point)
        # int WINAPI WinMain(HINSTANCE hInstance, ...)
        winmain_pattern = r'^\s*(?:int|DWORD)\s+(?:WINAPI|APIENTRY)\s+WinMain\s*\('
        for match in re.finditer(winmain_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="winmain_function",
                    line=line_num,
                    name="WinMain",
                )
            )

        # Pattern 3: wWinMain (Unicode Windows entry point)
        wwmain_pattern = r'^\s*(?:int|DWORD)\s+(?:WINAPI|APIENTRY)\s+wWinMain\s*\('
        for match in re.finditer(wwmain_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="winmain_function",
                    line=line_num,
                    name="wWinMain",
                )
            )

        # Pattern 4: DllMain (Windows DLL entry point)
        dllmain_pattern = r'^\s*BOOL\s+(?:WINAPI|APIENTRY)\s+DllMain\s*\('
        for match in re.finditer(dllmain_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="dllmain_function",
                    line=line_num,
                    name="DllMain",
                )
            )

        # Pattern 5: TEST macros (Google Test, Catch2, etc.)
        # TEST(TestSuite, TestName) or TEST_F(Fixture, TestName)
        test_macro_pattern = r'^\s*TEST(?:_F|_P)?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)'
        for match in re.finditer(test_macro_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            suite_name = match.group(1)
            test_name = match.group(2)
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="test",
                    line=line_num,
                    name=f"{suite_name}.{test_name}",
                )
            )

        # Pattern 6: Catch2 TEST_CASE macro
        # TEST_CASE("description", "[tag]")
        catch_test_pattern = r'^\s*TEST_CASE\s*\(\s*"([^"]+)"'
        for match in re.finditer(catch_test_pattern, content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            test_desc = match.group(1)
            entry_points.append(
                EntryPointInfo(
                    file=file_path,
                    type="test",
                    line=line_num,
                    name=test_desc,
                )
            )

        return entry_points

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify C/C++ file into architectural cluster.

        Uses base class heuristics plus C/C++-specific patterns.
        """
        name = Path(file_path).name.lower()
        path_lower = file_path.lower()

        # C/C++-specific patterns that override base classification

        # Third-party/vendor code (check first, before base class)
        if '/third_party/' in path_lower or '/vendor/' in path_lower or '/external/' in path_lower:
            return "infrastructure"

        # Entry points (main files)
        if name in ["main.cpp", "main.c", "main.cc", "main.cxx"]:
            return "entry_points"

        # Check for main function in content
        if re.search(r'^\s*(?:int|void)\s+main\s*\(', content, re.MULTILINE):
            return "entry_points"

        # Headers in public API directories
        if name.endswith(('.h', '.hpp', '.hh', '.hxx')):
            # Public API headers
            if '/include/' in path_lower:
                return "infrastructure"
            # Check if it's a config header
            if 'config' in name or 'version' in name:
                return "config"

        # Config files
        if name in ["config.h", "config.cpp", "settings.h", "settings.cpp"]:
            return "config"

        # Test files
        if any(x in name for x in ['test_', '_test.', 'unittest', 'test.cpp', 'test.c']):
            return "tests"

        # Check for test macros in content
        if re.search(r'^\s*TEST(?:_F|_P|_CASE)?\s*\(', content, re.MULTILINE):
            return "tests"

        # API directories contain core logic
        if '/api/' in path_lower:
            return "core_logic"

        # Source directories often contain core logic
        if '/src/' in path_lower:
            return "core_logic"

        # Use base class classification for remaining cases
        return super().classify_file(file_path, content)
