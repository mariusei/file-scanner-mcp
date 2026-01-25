"""Tests for C/C++ language."""

import pytest
from scantool.languages.cpp import CCppLanguage
from scantool.languages import ImportInfo, EntryPointInfo


@pytest.fixture
def language():
    """Create language instance."""
    return CCppLanguage()


def test_extensions(language):
    """Test that C++ analyzer supports correct extensions."""
    extensions = language.get_extensions()
    assert ".c" in extensions
    assert ".cc" in extensions
    assert ".cpp" in extensions
    assert ".cxx" in extensions
    assert ".h" in extensions
    assert ".hpp" in extensions
    assert ".hh" in extensions
    assert ".hxx" in extensions
    assert len(extensions) == 8


def test_language_name(language):
    """Test language name."""
    assert language.get_language_name() == "C/C++"


def test_extract_imports_local_headers(language):
    """Test extraction of local include statements."""
    content = """
#include "utils.h"
#include "parser/lexer.h"
#include "core/engine.hpp"
"""
    imports = language.extract_imports("test.cpp", content)

    assert len(imports) == 3
    assert any(imp.target_module == "utils.h" and imp.import_type == "local" for imp in imports)
    assert any(imp.target_module == "parser/lexer.h" and imp.import_type == "local" for imp in imports)
    assert any(imp.target_module == "core/engine.hpp" and imp.import_type == "local" for imp in imports)


def test_extract_imports_system_headers(language):
    """Test extraction of system include statements."""
    content = """
#include <iostream>
#include <vector>
#include <string>
#include <memory>
"""
    imports = language.extract_imports("test.cpp", content)

    assert len(imports) == 4
    assert any(imp.target_module == "iostream" and imp.import_type == "system" for imp in imports)
    assert any(imp.target_module == "vector" and imp.import_type == "system" for imp in imports)
    assert any(imp.target_module == "string" and imp.import_type == "system" for imp in imports)
    assert any(imp.target_module == "memory" and imp.import_type == "system" for imp in imports)


def test_extract_imports_mixed(language):
    """Test extraction of mixed local and system includes."""
    content = """
#include <iostream>
#include "my_header.h"
#include <string>
#include "utils/helper.hpp"
"""
    imports = language.extract_imports("test.cpp", content)

    assert len(imports) == 4

    system_imports = [imp for imp in imports if imp.import_type == "system"]
    local_imports = [imp for imp in imports if imp.import_type == "local"]

    assert len(system_imports) == 2
    assert len(local_imports) == 2


def test_extract_imports_with_spaces(language):
    """Test extraction of includes with spaces after #."""
    content = """
# include <stdio.h>
#  include "config.h"
#   include <stdlib.h>
"""
    imports = language.extract_imports("test.c", content)

    assert len(imports) == 3
    assert any(imp.target_module == "stdio.h" for imp in imports)
    assert any(imp.target_module == "config.h" for imp in imports)
    assert any(imp.target_module == "stdlib.h" for imp in imports)


def test_extract_imports_line_numbers(language):
    """Test that line numbers are correctly extracted."""
    content = """// Header comment
#include <iostream>
#include "utils.h"

int main() {
    return 0;
}
"""
    imports = language.extract_imports("test.cpp", content)

    # iostream should be on line 2
    iostream_import = next(imp for imp in imports if imp.target_module == "iostream")
    assert iostream_import.line == 2

    # utils.h should be on line 3
    utils_import = next(imp for imp in imports if imp.target_module == "utils.h")
    assert utils_import.line == 3


def test_find_entry_points_main_no_args(language):
    """Test detection of main() with no arguments."""
    content = """
int main() {
    return 0;
}
"""
    entry_points = language.find_entry_points("main.cpp", content)

    main_entries = [ep for ep in entry_points if ep.type == "main_function"]
    assert len(main_entries) == 1
    assert main_entries[0].name == "main"


def test_find_entry_points_main_with_args(language):
    """Test detection of main() with argc/argv."""
    content = """
int main(int argc, char** argv) {
    return 0;
}
"""
    entry_points = language.find_entry_points("main.cpp", content)

    main_entries = [ep for ep in entry_points if ep.type == "main_function"]
    assert len(main_entries) == 1
    assert main_entries[0].name == "main"


def test_find_entry_points_main_with_array_syntax(language):
    """Test detection of main() with array syntax for argv."""
    content = """
int main(int argc, char* argv[]) {
    return 0;
}
"""
    entry_points = language.find_entry_points("main.cpp", content)

    main_entries = [ep for ep in entry_points if ep.type == "main_function"]
    assert len(main_entries) == 1
    assert main_entries[0].name == "main"


def test_find_entry_points_void_main(language):
    """Test detection of void main() (non-standard but sometimes used)."""
    content = """
void main() {
    printf("Hello\\n");
}
"""
    entry_points = language.find_entry_points("main.c", content)

    main_entries = [ep for ep in entry_points if ep.type == "main_function"]
    assert len(main_entries) == 1
    assert main_entries[0].name == "main"


def test_find_entry_points_extern_main(language):
    """Test detection of extern int main()."""
    content = """
extern int main(int argc, char** argv) {
    return 0;
}
"""
    entry_points = language.find_entry_points("main.cpp", content)

    main_entries = [ep for ep in entry_points if ep.type == "main_function"]
    assert len(main_entries) == 1


def test_find_entry_points_winmain(language):
    """Test detection of WinMain entry point."""
    content = """
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow) {
    return 0;
}
"""
    entry_points = language.find_entry_points("winmain.cpp", content)

    win_entries = [ep for ep in entry_points if ep.type == "winmain_function"]
    assert len(win_entries) == 1
    assert win_entries[0].name == "WinMain"


def test_find_entry_points_wwinmain(language):
    """Test detection of wWinMain entry point."""
    content = """
int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                    LPWSTR lpCmdLine, int nCmdShow) {
    return 0;
}
"""
    entry_points = language.find_entry_points("winmain.cpp", content)

    win_entries = [ep for ep in entry_points if ep.type == "winmain_function"]
    assert len(win_entries) == 1
    assert win_entries[0].name == "wWinMain"


def test_find_entry_points_dllmain(language):
    """Test detection of DllMain entry point."""
    content = """
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    return TRUE;
}
"""
    entry_points = language.find_entry_points("dllmain.cpp", content)

    dll_entries = [ep for ep in entry_points if ep.type == "dllmain_function"]
    assert len(dll_entries) == 1
    assert dll_entries[0].name == "DllMain"


def test_find_entry_points_gtest(language):
    """Test detection of Google Test macros."""
    content = """
#include <gtest/gtest.h>

TEST(MathTest, Addition) {
    EXPECT_EQ(2 + 2, 4);
}

TEST_F(DatabaseTest, Connection) {
    EXPECT_TRUE(db.connect());
}

TEST_P(ParameterizedTest, Values) {
    EXPECT_GT(GetParam(), 0);
}
"""
    entry_points = language.find_entry_points("test.cpp", content)

    test_entries = [ep for ep in entry_points if ep.type == "test"]
    assert len(test_entries) == 3

    assert any(ep.name == "MathTest.Addition" for ep in test_entries)
    assert any(ep.name == "DatabaseTest.Connection" for ep in test_entries)
    assert any(ep.name == "ParameterizedTest.Values" for ep in test_entries)


def test_find_entry_points_catch2(language):
    """Test detection of Catch2 TEST_CASE macro."""
    content = """
#include <catch2/catch.hpp>

TEST_CASE("Vector addition works", "[vector]") {
    REQUIRE(add(1, 2) == 3);
}

TEST_CASE("String operations", "[string]") {
    REQUIRE(concat("a", "b") == "ab");
}
"""
    entry_points = language.find_entry_points("test.cpp", content)

    test_entries = [ep for ep in entry_points if ep.type == "test"]
    assert len(test_entries) == 2

    assert any(ep.name == "Vector addition works" for ep in test_entries)
    assert any(ep.name == "String operations" for ep in test_entries)


def test_find_entry_points_mixed(language):
    """Test detection of multiple entry point types in one file."""
    content = """
#include <iostream>

int main() {
    std::cout << "Hello" << std::endl;
    return 0;
}

TEST(BasicTest, Functionality) {
    EXPECT_TRUE(true);
}
"""
    entry_points = language.find_entry_points("main.cpp", content)

    assert len(entry_points) == 2

    types = {ep.type for ep in entry_points}
    assert "main_function" in types
    assert "test" in types


def test_should_analyze_normal_files(language):
    """Test that normal files should be analyzed."""
    assert language.should_analyze("src/main.cpp") == True
    assert language.should_analyze("include/utils.h") == True
    assert language.should_analyze("lib/parser.cc") == True
    assert language.should_analyze("core/engine.cxx") == True


def test_should_analyze_skip_protobuf(language):
    """Test that protobuf generated files should be skipped."""
    assert language.should_analyze("proto/messages.pb.h") == False
    assert language.should_analyze("proto/api.pb.cc") == False
    assert language.should_analyze("proto/service.pb.cpp") == False


def test_should_analyze_skip_qt_moc(language):
    """Test that Qt moc generated files should be skipped."""
    assert language.should_analyze("moc_widget.cpp") == False
    assert language.should_analyze("moc_mainwindow.h") == False
    assert language.should_analyze("generated/moc_dialog.cpp") == False


def test_should_analyze_skip_qt_ui(language):
    """Test that Qt UI generated files should be skipped."""
    assert language.should_analyze("ui_mainwindow.h") == False
    assert language.should_analyze("ui_dialog.h") == False


def test_should_analyze_skip_qt_qrc(language):
    """Test that Qt resource generated files should be skipped."""
    assert language.should_analyze("qrc_resources.cpp") == False


def test_should_analyze_skip_generated(language):
    """Test that generated files should be skipped."""
    assert language.should_analyze("parser.gen.h") == False
    assert language.should_analyze("lexer.gen.cpp") == False
    assert language.should_analyze("generated_code.h") == False


def test_should_analyze_keep_generator(language):
    """Test that generator (not generated) files should be kept."""
    # "generator" should NOT be skipped (it's the tool that generates, not generated)
    assert language.should_analyze("code_generator.cpp") == True


def test_should_analyze_skip_build_dirs(language):
    """Test that files in build directories should be skipped."""
    # Note: These paths need leading slash to match the pattern in should_analyze
    assert language.should_analyze("/build/main.cpp") == False
    assert language.should_analyze("path/build/main.cpp") == False
    assert language.should_analyze("/cmake-build-debug/foo.cpp") == False
    assert language.should_analyze("project/cmake-build-release/bar.h") == False


def test_classify_file_main_cpp(language):
    """Test classification of main.cpp as entry point."""
    content = """
int main() {
    return 0;
}
"""
    cluster = language.classify_file("src/main.cpp", content)
    assert cluster == "entry_points"


def test_classify_file_main_c(language):
    """Test classification of main.c as entry point."""
    content = """
int main(void) {
    return 0;
}
"""
    cluster = language.classify_file("main.c", content)
    assert cluster == "entry_points"


def test_classify_file_with_main_function(language):
    """Test classification by content containing main function."""
    content = """
int main(int argc, char** argv) {
    run_app();
    return 0;
}
"""
    cluster = language.classify_file("src/app.cpp", content)
    assert cluster == "entry_points"


def test_classify_file_header_in_include(language):
    """Test classification of headers in include/ as infrastructure."""
    content = """
#ifndef API_H
#define API_H

void process();

#endif
"""
    # Header in include/ directory (not named utils) -> infrastructure
    cluster = language.classify_file("project/include/api.h", content)
    assert cluster == "infrastructure"


def test_classify_file_header_in_api(language):
    """Test classification of headers in api/ as core logic (contains actual code)."""
    content = """
class ApiClient {
public:
    void connect();
};
"""
    # File in api/ directory -> core_logic
    cluster = language.classify_file("src/api/client.hpp", content)
    assert cluster == "core_logic"


def test_classify_file_config_header(language):
    """Test classification of config headers."""
    content = """
#define VERSION "1.0.0"
#define MAX_CONNECTIONS 100
"""
    cluster = language.classify_file("include/config.h", content)
    assert cluster == "config"


def test_classify_file_test_prefix(language):
    """Test classification of test_* files."""
    content = """
void test_helper() {
    // Test helper
}
"""
    cluster = language.classify_file("test_utils.cpp", content)
    assert cluster == "tests"


def test_classify_file_with_test_macro(language):
    """Test classification by content containing TEST macro."""
    content = """
TEST(MathTest, Addition) {
    EXPECT_EQ(2 + 2, 4);
}
"""
    cluster = language.classify_file("math_tests.cpp", content)
    assert cluster == "tests"


def test_classify_file_in_src(language):
    """Test classification of files in src/ as core logic."""
    content = """
void process_data() {
    // Processing logic
}
"""
    cluster = language.classify_file("src/processor.cpp", content)
    assert cluster == "core_logic"


def test_classify_file_third_party(language):
    """Test classification of third-party code as infrastructure."""
    content = """
// Third-party library code
void parse() {}
"""
    # Third-party with /third_party/ path -> infrastructure
    cluster = language.classify_file("libs/third_party/json/json.cpp", content)
    assert cluster == "infrastructure"


def test_extract_imports_complex_real_world(language):
    """Test complex real-world include patterns."""
    content = """
// System headers
#include <iostream>
#include <vector>
#include <memory>

// Third-party headers
#include <boost/asio.hpp>
#include <nlohmann/json.hpp>

// Local headers
#include "config.h"
#include "utils/logger.hpp"
#include "core/engine.h"
"""
    imports = language.extract_imports("src/main.cpp", content)

    assert len(imports) == 8

    system_imports = [imp for imp in imports if imp.import_type == "system"]
    local_imports = [imp for imp in imports if imp.import_type == "local"]

    assert len(system_imports) == 5
    assert len(local_imports) == 3

    # Check specific imports
    assert any(imp.target_module == "iostream" for imp in system_imports)
    assert any(imp.target_module == "boost/asio.hpp" for imp in system_imports)
    assert any(imp.target_module == "config.h" for imp in local_imports)
    assert any(imp.target_module == "utils/logger.hpp" for imp in local_imports)


def test_find_entry_points_comprehensive(language):
    """Test comprehensive entry point detection in realistic file."""
    content = """
#include <iostream>
#include <gtest/gtest.h>

int main(int argc, char** argv) {
    testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}

TEST(BasicTest, Initialization) {
    EXPECT_TRUE(true);
}

TEST_F(FixtureTest, Functionality) {
    EXPECT_EQ(calculate(5), 25);
}

TEST_CASE("String operations work", "[string]") {
    REQUIRE(concat("a", "b") == "ab");
}
"""
    entry_points = language.find_entry_points("test_main.cpp", content)

    # Should find: main, 2 Google Test, 1 Catch2 test
    assert len(entry_points) >= 4

    types = {ep.type for ep in entry_points}
    assert "main_function" in types
    assert "test" in types

    # Check specific tests
    test_names = {ep.name for ep in entry_points if ep.type == "test"}
    assert "BasicTest.Initialization" in test_names
    assert "FixtureTest.Functionality" in test_names
    assert "String operations work" in test_names
