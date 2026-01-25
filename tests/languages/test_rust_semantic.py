"""Tests for Rust language."""

import pytest
from scantool.languages.rust import RustLanguage
from scantool.languages import ImportInfo, EntryPointInfo


@pytest.fixture
def language():
    """Create language instance."""
    return RustLanguage()


def test_extensions(language):
    """Test that Rust analyzer supports correct extensions."""
    extensions = language.get_extensions()
    assert ".rs" in extensions
    assert len(extensions) == 1


def test_language_name(language):
    """Test language name."""
    assert language.get_language_name() == "Rust"


def test_extract_imports_simple_use(language):
    """Test extraction of simple use statements."""
    content = """
use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
"""
    imports = language.extract_imports("test.rs", content)

    assert len(imports) == 3
    assert any(imp.target_module == "std::collections::HashMap" for imp in imports)
    assert any(imp.target_module == "std::fs::File" for imp in imports)
    assert any(imp.target_module == "std::io::Read" for imp in imports)
    assert all(imp.import_type == "std" for imp in imports)


def test_extract_imports_crate(language):
    """Test extraction of crate-relative imports."""
    content = """
use crate::module::Type;
use crate::utils::helper;
"""
    imports = language.extract_imports("test.rs", content)

    assert len(imports) == 2
    assert any(imp.target_module == "crate::module::Type" for imp in imports)
    assert any(imp.target_module == "crate::utils::helper" for imp in imports)
    assert all(imp.import_type == "crate" for imp in imports)


def test_extract_imports_relative(language):
    """Test extraction of relative imports (super, self)."""
    content = """
use super::parent;
use self::current;
use super::super::grandparent;
"""
    imports = language.extract_imports("src/foo/bar.rs", content)

    assert len(imports) == 3
    assert any(imp.target_module == "super::parent" for imp in imports)
    assert any(imp.target_module == "self::current" for imp in imports)
    assert any(imp.target_module == "super::super::grandparent" for imp in imports)
    assert all(imp.import_type == "relative" for imp in imports)


def test_extract_imports_grouped(language):
    """Test extraction of grouped imports with braces."""
    content = """
use std::io::{Read, Write, BufReader};
use std::collections::{HashMap, HashSet};
"""
    imports = language.extract_imports("test.rs", content)

    assert len(imports) == 2

    # First import: std::io with Read, Write, BufReader
    io_import = next(imp for imp in imports if "io" in imp.target_module)
    assert io_import.target_module == "std::io"
    assert "Read" in io_import.imported_names
    assert "Write" in io_import.imported_names
    assert "BufReader" in io_import.imported_names

    # Second import: std::collections with HashMap, HashSet
    collections_import = next(imp for imp in imports if "collections" in imp.target_module)
    assert collections_import.target_module == "std::collections"
    assert "HashMap" in collections_import.imported_names
    assert "HashSet" in collections_import.imported_names


def test_extract_imports_aliased(language):
    """Test extraction of aliased imports (as keyword)."""
    content = """
use std::io::Result as IoResult;
use std::collections::HashMap as Map;
"""
    imports = language.extract_imports("test.rs", content)

    assert len(imports) == 2
    assert any(
        imp.target_module == "std::io::Result" and "IoResult" in imp.imported_names
        for imp in imports
    )
    assert any(
        imp.target_module == "std::collections::HashMap" and "Map" in imp.imported_names
        for imp in imports
    )


def test_extract_imports_pub_use(language):
    """Test extraction of pub use statements."""
    content = """
pub use std::collections::HashMap;
pub use crate::module::Type;
"""
    imports = language.extract_imports("test.rs", content)

    assert len(imports) == 2
    assert any(imp.target_module == "std::collections::HashMap" for imp in imports)
    assert any(imp.target_module == "crate::module::Type" for imp in imports)


def test_extract_imports_absolute_path(language):
    """Test extraction of absolute imports (starting with ::)."""
    content = """
use ::external_crate::module;
"""
    imports = language.extract_imports("test.rs", content)

    assert len(imports) == 1
    assert imports[0].target_module == "::external_crate::module"
    assert imports[0].import_type == "absolute"


def test_find_entry_points_main_function(language):
    """Test detection of main() function."""
    content = """
fn main() {
    println!("Hello, world!");
}

fn helper() {
    // Not an entry point
}
"""
    entry_points = language.find_entry_points("main.rs", content)

    main_entries = [ep for ep in entry_points if ep.type == "main_function"]
    assert len(main_entries) == 1
    assert main_entries[0].name == "main"


def test_find_entry_points_pub_main(language):
    """Test detection of pub fn main()."""
    content = """
pub fn main() {
    run_server();
}
"""
    entry_points = language.find_entry_points("main.rs", content)

    main_entries = [ep for ep in entry_points if ep.type == "main_function"]
    assert len(main_entries) == 1
    assert main_entries[0].name == "main"


def test_find_entry_points_tokio_main(language):
    """Test detection of #[tokio::main] async entry point."""
    content = """
#[tokio::main]
async fn main() {
    println!("Async runtime!");
}
"""
    entry_points = language.find_entry_points("main.rs", content)

    async_entries = [ep for ep in entry_points if ep.type == "async_main"]
    assert len(async_entries) == 1
    assert async_entries[0].name == "main"
    assert async_entries[0].framework == "tokio"


def test_find_entry_points_async_std_main(language):
    """Test detection of #[async_std::main] entry point."""
    content = """
#[async_std::main]
async fn main() {
    run().await;
}
"""
    entry_points = language.find_entry_points("main.rs", content)

    async_entries = [ep for ep in entry_points if ep.type == "async_main"]
    assert len(async_entries) == 1
    assert async_entries[0].name == "main"
    assert async_entries[0].framework == "async_std"


def test_find_entry_points_actix_main(language):
    """Test detection of #[actix_web::main] entry point."""
    content = """
#[actix_web::main]
async fn main() -> std::io::Result<()> {
    HttpServer::new(|| App::new())
        .bind("127.0.0.1:8080")?
        .run()
        .await
}
"""
    entry_points = language.find_entry_points("main.rs", content)

    async_entries = [ep for ep in entry_points if ep.type == "async_main"]
    assert len(async_entries) == 1
    assert async_entries[0].framework == "actix_web"


def test_find_entry_points_test_functions(language):
    """Test detection of #[test] functions."""
    content = """
#[test]
fn test_addition() {
    assert_eq!(2 + 2, 4);
}

#[test]
fn test_subtraction() {
    assert_eq!(5 - 3, 2);
}

#[cfg(test)]
fn test_helper() {
    // Helper function
}
"""
    entry_points = language.find_entry_points("lib.rs", content)

    test_entries = [ep for ep in entry_points if ep.type == "test"]
    assert len(test_entries) == 3
    assert any(ep.name == "test_addition" for ep in test_entries)
    assert any(ep.name == "test_subtraction" for ep in test_entries)
    assert any(ep.name == "test_helper" for ep in test_entries)


def test_find_entry_points_benchmark(language):
    """Test detection of #[bench] functions."""
    content = """
#[bench]
fn bench_function(b: &mut Bencher) {
    b.iter(|| expensive_computation());
}
"""
    entry_points = language.find_entry_points("benches/bench.rs", content)

    bench_entries = [ep for ep in entry_points if ep.type == "benchmark"]
    assert len(bench_entries) == 1
    assert bench_entries[0].name == "bench_function"


def test_find_entry_points_lib_exports(language):
    """Test detection of pub mod and pub use in lib.rs."""
    content = """
pub mod module1;
pub mod module2;

pub use self::module1::Type;
pub use self::module2::Function;
"""
    entry_points = language.find_entry_points("lib.rs", content)

    export_entries = [ep for ep in entry_points if ep.type == "export"]
    assert len(export_entries) == 4

    # Check pub mod exports
    assert any("mod module1" in ep.name for ep in export_entries)
    assert any("mod module2" in ep.name for ep in export_entries)

    # Check pub use exports
    assert any("self::module1::Type" in ep.name for ep in export_entries)
    assert any("self::module2::Function" in ep.name for ep in export_entries)


def test_find_entry_points_mixed(language):
    """Test detection of multiple entry point types in one file."""
    content = """
use std::io;

fn main() {
    println!("Main function");
}

#[test]
fn test_something() {
    assert!(true);
}

#[tokio::test]
async fn test_async() {
    assert!(true);
}
"""
    entry_points = language.find_entry_points("main.rs", content)

    assert len(entry_points) == 3

    # Should have main, test, and async_test
    types = {ep.type for ep in entry_points}
    assert "main_function" in types
    assert "test" in types
    assert "async_test" in types


def test_classify_file_main_rs(language):
    """Test classification of main.rs as entry point."""
    content = """
fn main() {
    println!("Hello");
}
"""
    cluster = language.classify_file("src/main.rs", content)
    assert cluster == "entry_points"


def test_classify_file_lib_rs(language):
    """Test classification of lib.rs as entry point."""
    content = """
pub mod utils;
pub mod core;
"""
    cluster = language.classify_file("src/lib.rs", content)
    assert cluster == "entry_points"


def test_classify_file_test_directory(language):
    """Test classification of files in tests/ directory."""
    content = """
use super::*;

#[test]
fn test_something() {
    assert!(true);
}
"""
    cluster = language.classify_file("tests/integration_test.rs", content)
    assert cluster == "tests"


def test_classify_file_benches_directory(language):
    """Test classification of files in benches/ directory."""
    content = """
#[bench]
fn bench_something(b: &mut Bencher) {
    b.iter(|| expensive_op());
}
"""
    cluster = language.classify_file("benches/benchmark.rs", content)
    assert cluster == "tests"


def test_classify_file_mod_rs(language):
    """Test classification of mod.rs as infrastructure."""
    content = """
pub mod submodule1;
pub mod submodule2;
"""
    cluster = language.classify_file("src/utils/mod.rs", content)
    assert cluster == "infrastructure"


def test_classify_file_test_prefix(language):
    """Test classification of test_* files."""
    content = """
fn test_helper() {
    // Test helper
}
"""
    cluster = language.classify_file("src/test_utils.rs", content)
    assert cluster == "tests"


def test_classify_file_with_test_attribute(language):
    """Test classification by content containing #[test]."""
    content = """
#[test]
fn verify_logic() {
    assert_eq!(1 + 1, 2);
}
"""
    cluster = language.classify_file("src/verify.rs", content)
    assert cluster == "tests"


def test_classify_file_with_main_function(language):
    """Test classification by content containing fn main."""
    content = """
fn main() {
    run_app();
}
"""
    cluster = language.classify_file("src/bin/tool.rs", content)
    assert cluster == "entry_points"


def test_should_analyze_normal_file(language):
    """Test that normal files should be analyzed."""
    assert language.should_analyze("src/main.rs") == True
    assert language.should_analyze("src/lib.rs") == True
    assert language.should_analyze("src/utils/helper.rs") == True


def test_should_analyze_protobuf_generated(language):
    """Test that protobuf generated files should be skipped."""
    assert language.should_analyze("src/proto/messages.pb.rs") == False
    assert language.should_analyze("generated/api.pb.rs") == False


def test_should_analyze_target_directory(language):
    """Test that files in target/ should be skipped."""
    assert language.should_analyze("target/debug/build/foo.rs") == False
    assert language.should_analyze("target/release/main.rs") == False
    assert language.should_analyze("target/doc/src/lib.rs") == False


def test_should_analyze_build_script(language):
    """Test that build.rs in project root should be analyzed."""
    # build.rs in root is fine (it's the actual build script)
    assert language.should_analyze("build.rs") == True


def test_should_analyze_build_in_target(language):
    """Test that build.rs in target/ should be skipped."""
    # But build.rs in target/ is generated
    assert language.should_analyze("target/debug/build/pkg/build.rs") == False


def test_extract_imports_complex_mixed(language):
    """Test complex real-world import patterns."""
    content = """
use std::collections::{HashMap, HashSet, BTreeMap};
use std::io::{self, Read, Write};
use std::sync::Arc;

use crate::module::{Type1, Type2};
use crate::utils;

use super::parent::Function;
use self::local::Helper;

pub use external::Type as ExternalType;

use ::absolute::path::Module;
"""
    imports = language.extract_imports("src/complex.rs", content)

    # Should extract all import statements
    assert len(imports) >= 9

    # Check grouped imports
    assert any(
        imp.target_module == "std::collections"
        and "HashMap" in imp.imported_names
        and "HashSet" in imp.imported_names
        and "BTreeMap" in imp.imported_names
        for imp in imports
    )

    # Check self import with grouped items
    assert any(
        imp.target_module == "std::io"
        and "Read" in imp.imported_names
        and "Write" in imp.imported_names
        for imp in imports
    )

    # Check various import types
    import_types = {imp.import_type for imp in imports}
    assert "std" in import_types
    assert "crate" in import_types
    assert "relative" in import_types
    assert "use_as" in import_types
    assert "absolute" in import_types


def test_find_entry_points_comprehensive(language):
    """Test comprehensive entry point detection in realistic file."""
    content = """
use tokio::runtime::Runtime;

#[tokio::main]
async fn main() {
    run_server().await;
}

#[test]
fn test_basic() {
    assert!(true);
}

#[tokio::test]
async fn test_async_operation() {
    let result = async_function().await;
    assert!(result);
}

#[bench]
fn bench_performance(b: &mut Bencher) {
    b.iter(|| computation());
}

fn helper() {
    // Not an entry point
}
"""
    entry_points = language.find_entry_points("src/main.rs", content)

    # Should find: async main, test, async test, bench
    assert len(entry_points) >= 4

    types = {ep.type for ep in entry_points}
    assert "async_main" in types
    assert "test" in types
    assert "async_test" in types
    assert "benchmark" in types

    # Verify framework detection
    frameworks = {ep.framework for ep in entry_points if ep.framework}
    assert "tokio" in frameworks
