"""Tests for PHP analyzer."""

import pytest
from scantool.analyzers.php_analyzer import PHPAnalyzer
from scantool.analyzers.models import ImportInfo, EntryPointInfo


@pytest.fixture
def analyzer():
    """Create PHP analyzer instance."""
    return PHPAnalyzer()


class TestPHPAnalyzerMetadata:
    """Test analyzer metadata."""

    def test_extensions(self, analyzer):
        """Test that analyzer supports correct extensions."""
        extensions = analyzer.get_extensions()
        assert ".php" in extensions
        assert ".phtml" in extensions

    def test_language_name(self, analyzer):
        """Test language name."""
        assert analyzer.get_language_name() == "PHP"

    def test_priority(self, analyzer):
        """Test priority value."""
        assert analyzer.get_priority() == 10


class TestShouldAnalyze:
    """Test should_analyze filtering."""

    def test_should_analyze_normal_file(self, analyzer):
        """Test that normal PHP files should be analyzed."""
        assert analyzer.should_analyze("src/Controller/UserController.php") is True
        assert analyzer.should_analyze("index.php") is True
        assert analyzer.should_analyze("app/Models/User.php") is True

    def test_should_analyze_skip_blade_cache(self, analyzer):
        """Test that Laravel Blade cache files are skipped."""
        assert analyzer.should_analyze("storage/framework/views/abc123.php") is False
        assert analyzer.should_analyze("storage/framework/views/compiled/test.php") is False

    def test_should_analyze_phtml(self, analyzer):
        """Test that .phtml files are analyzed."""
        assert analyzer.should_analyze("template.phtml") is True


class TestExtractImports:
    """Test import extraction."""

    def test_extract_imports_use_statements(self, analyzer):
        """Test extraction of use statements."""
        content = """<?php
namespace App\\Controllers;

use App\\Models\\User;
use App\\Services\\EmailService;
use Illuminate\\Http\\Request;
"""
        imports = analyzer.extract_imports("test.php", content)

        assert len(imports) == 3
        assert any(imp.target_module == "App\\Models\\User" for imp in imports)
        assert any(imp.target_module == "App\\Services\\EmailService" for imp in imports)
        assert any(imp.target_module == "Illuminate\\Http\\Request" for imp in imports)
        assert all(imp.import_type == "use" for imp in imports)

    def test_extract_imports_use_with_alias(self, analyzer):
        """Test extraction of use statements with aliases."""
        content = """<?php
use App\\Models\\User as UserModel;
use App\\Services\\EmailService as Mailer;
"""
        imports = analyzer.extract_imports("test.php", content)

        assert len(imports) == 2
        assert any(imp.target_module == "App\\Models\\User" for imp in imports)
        assert any(imp.target_module == "App\\Services\\EmailService" for imp in imports)

    def test_extract_imports_grouped_use(self, analyzer):
        """Test extraction of grouped use statements."""
        content = """<?php
use App\\Services\\{UserService, EmailService, LogService};
"""
        imports = analyzer.extract_imports("test.php", content)

        assert len(imports) == 3
        assert any(imp.target_module == "App\\Services\\UserService" for imp in imports)
        assert any(imp.target_module == "App\\Services\\EmailService" for imp in imports)
        assert any(imp.target_module == "App\\Services\\LogService" for imp in imports)
        assert all(imp.import_type == "use_grouped" for imp in imports)

    def test_extract_imports_require(self, analyzer):
        """Test extraction of require statements."""
        content = """<?php
require 'config/database.php';
require_once 'vendor/autoload.php';
"""
        imports = analyzer.extract_imports("test.php", content)

        assert len(imports) == 2
        assert any(imp.target_module == "config/database.php" and imp.import_type == "require" for imp in imports)
        assert any(imp.target_module == "vendor/autoload.php" and imp.import_type == "require_once" for imp in imports)

    def test_extract_imports_include(self, analyzer):
        """Test extraction of include statements."""
        content = """<?php
include 'header.php';
include_once 'footer.php';
"""
        imports = analyzer.extract_imports("test.php", content)

        assert len(imports) == 2
        assert any(imp.target_module == "header.php" and imp.import_type == "include" for imp in imports)
        assert any(imp.target_module == "footer.php" and imp.import_type == "include_once" for imp in imports)

    def test_extract_imports_require_with_parentheses(self, analyzer):
        """Test extraction of require statements with parentheses."""
        content = """<?php
require('config.php');
require_once('init.php');
"""
        imports = analyzer.extract_imports("test.php", content)

        assert len(imports) == 2
        assert any(imp.target_module == "config.php" for imp in imports)
        assert any(imp.target_module == "init.php" for imp in imports)

    def test_extract_imports_relative_paths(self, analyzer):
        """Test extraction of relative path imports."""
        content = """<?php
require './config/app.php';
include '../helpers/functions.php';
"""
        imports = analyzer.extract_imports("src/app.php", content)

        assert len(imports) == 2
        # Check that relative imports are marked correctly
        assert any(imp.import_type == "require_relative" for imp in imports)
        assert any(imp.import_type == "include_relative" for imp in imports)

    def test_extract_imports_use_function(self, analyzer):
        """Test extraction of function use statements."""
        content = """<?php
use function App\\Utils\\validateEmail;
use function App\\Helpers\\formatDate;
"""
        imports = analyzer.extract_imports("test.php", content)

        assert len(imports) == 2
        assert any(imp.target_module == "App\\Utils\\validateEmail" for imp in imports)
        assert any(imp.target_module == "App\\Helpers\\formatDate" for imp in imports)
        assert all(imp.import_type == "use_function" for imp in imports)

    def test_extract_imports_mixed(self, analyzer):
        """Test extraction of mixed import styles."""
        content = """<?php
namespace App\\Controllers;

use App\\Models\\User;
use App\\Services\\{EmailService, LogService};
require_once 'config.php';
include 'header.php';
use function App\\Utils\\debug;
"""
        imports = analyzer.extract_imports("test.php", content)

        # Should find all different import types
        assert len(imports) >= 5
        assert any(imp.import_type == "use" for imp in imports)
        assert any(imp.import_type == "use_grouped" for imp in imports)
        assert any(imp.import_type == "require_once" for imp in imports)
        assert any(imp.import_type == "include" for imp in imports)
        assert any(imp.import_type == "use_function" for imp in imports)


class TestFindEntryPoints:
    """Test entry point detection."""

    def test_find_entry_points_index_php(self, analyzer):
        """Test detection of index.php as entry point."""
        content = """<?php
require 'vendor/autoload.php';
echo "Hello World";
"""
        entry_points = analyzer.find_entry_points("public/index.php", content)

        index_entries = [ep for ep in entry_points if ep.type == "entry_file"]
        assert len(index_entries) == 1
        assert index_entries[0].name == "index.php"

    def test_find_entry_points_not_index(self, analyzer):
        """Test that non-index files are not marked as entry files."""
        content = """<?php
echo "Hello";
"""
        entry_points = analyzer.find_entry_points("app/test.php", content)

        index_entries = [ep for ep in entry_points if ep.type == "entry_file"]
        assert len(index_entries) == 0

    def test_find_entry_points_laravel_routes(self, analyzer):
        """Test detection of Laravel route definitions."""
        content = """<?php
Route::get('/users', 'UserController@index');
Route::post('/users', 'UserController@store');
Route::put('/users/{id}', 'UserController@update');
Route::delete('/users/{id}', 'UserController@destroy');
"""
        entry_points = analyzer.find_entry_points("routes/api.php", content)

        route_entries = [ep for ep in entry_points if ep.type == "route"]
        assert len(route_entries) == 4
        assert any(ep.name == "GET /users" for ep in route_entries)
        assert any(ep.name == "POST /users" for ep in route_entries)
        assert any(ep.name == "PUT /users/{id}" for ep in route_entries)
        assert any(ep.name == "DELETE /users/{id}" for ep in route_entries)
        assert all(ep.framework == "Laravel" for ep in route_entries)

    def test_find_entry_points_route_resource(self, analyzer):
        """Test detection of Laravel resource routes."""
        content = """<?php
Route::resource('photos', 'PhotoController');
"""
        entry_points = analyzer.find_entry_points("routes/web.php", content)

        route_entries = [ep for ep in entry_points if ep.type == "route"]
        assert len(route_entries) == 1
        assert route_entries[0].name == "RESOURCE photos"

    def test_find_entry_points_controllers(self, analyzer):
        """Test detection of controller classes."""
        content = """<?php
namespace App\\Controllers;

class UserController extends Controller {
    public function index() {
        return view('users.index');
    }
}
"""
        entry_points = analyzer.find_entry_points("app/Controllers/UserController.php", content)

        controller_entries = [ep for ep in entry_points if ep.type == "controller"]
        assert len(controller_entries) == 1
        assert controller_entries[0].name == "UserController"

    def test_find_entry_points_final_controller(self, analyzer):
        """Test detection of final controller classes."""
        content = """<?php
namespace App\\Controllers;

final class ApiController {
    // Controller logic
}
"""
        entry_points = analyzer.find_entry_points("app/Controllers/ApiController.php", content)

        controller_entries = [ep for ep in entry_points if ep.type == "controller"]
        assert len(controller_entries) == 1
        assert controller_entries[0].name == "ApiController"

    def test_find_entry_points_invokable(self, analyzer):
        """Test detection of invokable controllers (__invoke)."""
        content = """<?php
namespace App\\Controllers;

class ShowUserController {
    public function __invoke($id) {
        return User::find($id);
    }
}
"""
        entry_points = analyzer.find_entry_points("app/Controllers/ShowUserController.php", content)

        invokable_entries = [ep for ep in entry_points if ep.type == "invokable"]
        assert len(invokable_entries) == 1
        assert invokable_entries[0].name == "__invoke"

    def test_find_entry_points_mixed(self, analyzer):
        """Test detection of multiple entry point types."""
        content = """<?php
Route::get('/api/users', 'UserController@index');

class UserController extends Controller {
    public function index() {
        return [];
    }

    public function __invoke() {
        return [];
    }
}
"""
        entry_points = analyzer.find_entry_points("routes/api.php", content)

        # Should find route, controller, and invokable
        assert any(ep.type == "route" for ep in entry_points)
        assert any(ep.type == "controller" for ep in entry_points)
        assert any(ep.type == "invokable" for ep in entry_points)


class TestClassifyFile:
    """Test file classification."""

    def test_classify_file_index_php(self, analyzer):
        """Test classification of index.php as entry point."""
        content = """<?php
require 'vendor/autoload.php';
"""
        cluster = analyzer.classify_file("public/index.php", content)
        assert cluster == "entry_points"

    def test_classify_file_controller(self, analyzer):
        """Test classification of controller files."""
        content = """<?php
class UserController extends Controller {}
"""
        # Test by directory
        cluster = analyzer.classify_file("app/Controllers/UserController.php", content)
        assert cluster == "entry_points"

        # Test by filename
        cluster = analyzer.classify_file("UserController.php", content)
        assert cluster == "entry_points"

    def test_classify_file_routes(self, analyzer):
        """Test classification of route files."""
        content = """<?php
Route::get('/', function() {});
"""
        cluster = analyzer.classify_file("routes/web.php", content)
        assert cluster == "entry_points"

        cluster = analyzer.classify_file("routes/api.php", content)
        assert cluster == "entry_points"

    def test_classify_file_model(self, analyzer):
        """Test classification of model files."""
        content = """<?php
class User extends Model {}
"""
        cluster = analyzer.classify_file("app/Models/User.php", content)
        assert cluster == "core_logic"

    def test_classify_file_service(self, analyzer):
        """Test classification of service files."""
        content = """<?php
class EmailService {}
"""
        cluster = analyzer.classify_file("app/Services/EmailService.php", content)
        assert cluster == "core_logic"

    def test_classify_file_middleware(self, analyzer):
        """Test classification of middleware files."""
        content = """<?php
class Authenticate {}
"""
        cluster = analyzer.classify_file("app/Middleware/Authenticate.php", content)
        assert cluster == "core_logic"

    def test_classify_file_config(self, analyzer):
        """Test classification of config files."""
        content = """<?php
return [
    'app_name' => 'MyApp'
];
"""
        cluster = analyzer.classify_file("config/app.php", content)
        assert cluster == "config"

        cluster = analyzer.classify_file("config.production.php", content)
        assert cluster == "config"

    def test_classify_file_migrations(self, analyzer):
        """Test classification of migration files."""
        content = """<?php
class CreateUsersTable {}
"""
        cluster = analyzer.classify_file("database/migrations/2024_create_users_table.php", content)
        assert cluster == "database"

    def test_classify_file_seeders(self, analyzer):
        """Test classification of seeder files."""
        content = """<?php
class UserSeeder {}
"""
        cluster = analyzer.classify_file("database/seeders/UserSeeder.php", content)
        assert cluster == "database"

    def test_classify_file_views(self, analyzer):
        """Test classification of view/template files."""
        content = """
<html>
<body>Hello</body>
</html>
"""
        cluster = analyzer.classify_file("resources/views/home.blade.php", content)
        assert cluster == "presentation"

        cluster = analyzer.classify_file("templates/index.php", content)
        assert cluster == "presentation"

    def test_classify_file_test(self, analyzer):
        """Test classification of test files."""
        content = """<?php
class UserTest extends TestCase {}
"""
        cluster = analyzer.classify_file("tests/Unit/UserTest.php", content)
        assert cluster == "tests"


class TestRealWorldExamples:
    """Test with real-world PHP code examples."""

    def test_laravel_controller_example(self, analyzer):
        """Test analysis of Laravel controller."""
        content = """<?php

namespace App\\Http\\Controllers;

use App\\Models\\User;
use Illuminate\\Http\\Request;
use Illuminate\\Support\\Facades\\Hash;

class UserController extends Controller
{
    public function index()
    {
        return User::all();
    }

    public function store(Request $request)
    {
        $validated = $request->validate([
            'name' => 'required|max:255',
            'email' => 'required|email|unique:users',
        ]);

        return User::create($validated);
    }
}
"""
        imports = analyzer.extract_imports("app/Http/Controllers/UserController.php", content)
        entry_points = analyzer.find_entry_points("app/Http/Controllers/UserController.php", content)

        # Should extract imports
        assert len(imports) == 3
        assert any(imp.target_module == "App\\Models\\User" for imp in imports)

        # Should detect controller
        assert any(ep.type == "controller" and ep.name == "UserController" for ep in entry_points)

    def test_symfony_controller_example(self, analyzer):
        """Test analysis of Symfony controller."""
        content = """<?php

namespace App\\Controller;

use Symfony\\Bundle\\FrameworkBundle\\Controller\\AbstractController;
use Symfony\\Component\\HttpFoundation\\Response;
use Symfony\\Component\\Routing\\Annotation\\Route;

class HomeController extends AbstractController
{
    #[Route('/home', name: 'app_home')]
    public function index(): Response
    {
        return $this->render('home/index.html.twig');
    }
}
"""
        imports = analyzer.extract_imports("src/Controller/HomeController.php", content)
        entry_points = analyzer.find_entry_points("src/Controller/HomeController.php", content)

        # Should extract imports
        assert len(imports) == 3

        # Should detect controller
        assert any(ep.type == "controller" and ep.name == "HomeController" for ep in entry_points)

    def test_edge_cases_file(self, analyzer):
        """Test analysis of edge cases file from test fixtures."""
        with open("tests/php/samples/edge_cases.php", "r") as f:
            content = f.read()

        imports = analyzer.extract_imports("tests/php/samples/edge_cases.php", content)

        # Should extract namespace imports
        assert any(imp.target_module == "App\\Database\\DatabaseManager" for imp in imports)

        # Should extract grouped imports
        assert any(imp.target_module == "App\\Services\\UserService" for imp in imports)
        assert any(imp.target_module == "App\\Services\\EmailService" for imp in imports)

        # Should extract function imports
        assert any(imp.target_module == "App\\Utils\\validateEmail" and imp.import_type == "use_function" for imp in imports)
