"""Tests for Ruby language."""

import pytest
from scantool.languages.ruby import RubyLanguage
from scantool.languages import ImportInfo, EntryPointInfo


@pytest.fixture
def language():
    """Create language instance."""
    return RubyLanguage()


class TestRubyAnalyzer:
    """Test suite for Ruby language."""

    def test_extensions(self, language):
        """Test that analyzer supports correct extensions."""
        extensions = language.get_extensions()
        assert ".rb" in extensions
        assert ".rake" in extensions

    def test_language_name(self, language):
        """Test language name."""
        assert language.get_language_name() == "Ruby"

    def test_priority(self, language):
        """Test analyzer priority."""
        assert language.get_priority() == 10

    # ===================================================================
    # Import extraction tests
    # ===================================================================

    def test_extract_imports_require(self, language):
        """Test extraction of require statements."""
        content = """
require 'json'
require "active_support"
require 'rails/all'
"""
        imports = language.extract_imports("test.rb", content)

        assert len(imports) == 3
        assert any(imp.target_module == "json" and imp.import_type == "require" for imp in imports)
        assert any(imp.target_module == "active_support" and imp.import_type == "require" for imp in imports)
        assert any(imp.target_module == "rails/all" and imp.import_type == "require" for imp in imports)

    def test_extract_imports_require_relative(self, language):
        """Test extraction of require_relative statements."""
        content = """
require_relative '../utils'
require_relative "./helpers/formatter"
require_relative 'config'
"""
        imports = language.extract_imports("app/models/user.rb", content)

        assert len(imports) == 3
        assert all(imp.import_type == "require_relative" for imp in imports)

    def test_extract_imports_gem(self, language):
        """Test extraction of gem statements."""
        content = """
gem 'rails', '~> 7.0'
gem "rspec"
gem 'pg', '>= 1.0'
"""
        imports = language.extract_imports("Gemfile", content)

        assert len(imports) == 3
        assert any(imp.target_module == "rails" and imp.import_type == "gem" for imp in imports)
        assert any(imp.target_module == "rspec" and imp.import_type == "gem" for imp in imports)
        assert any(imp.target_module == "pg" and imp.import_type == "gem" for imp in imports)

    def test_extract_imports_load(self, language):
        """Test extraction of load statements."""
        content = """
load 'config.rb'
load "lib/tasks/custom.rake"
"""
        imports = language.extract_imports("test.rb", content)

        assert len(imports) == 2
        assert any(imp.target_module == "config.rb" and imp.import_type == "load" for imp in imports)
        assert any(imp.target_module == "lib/tasks/custom.rake" and imp.import_type == "load" for imp in imports)

    def test_extract_imports_autoload(self, language):
        """Test extraction of autoload statements."""
        content = """
autoload :MyClass, 'lib/my_class'
autoload :Utils, "app/utils"
"""
        imports = language.extract_imports("test.rb", content)

        assert len(imports) == 2
        autoload_imports = [imp for imp in imports if imp.import_type == "autoload"]
        assert len(autoload_imports) == 2
        assert any("MyClass" in imp.imported_names for imp in autoload_imports)
        assert any("Utils" in imp.imported_names for imp in autoload_imports)

    def test_extract_imports_mixed(self, language):
        """Test extraction of mixed import types."""
        content = """
require 'json'
require_relative '../config'
gem 'rails'
load 'setup.rb'
autoload :Parser, 'lib/parser'
"""
        imports = language.extract_imports("test.rb", content)

        assert len(imports) == 5
        import_types = {imp.import_type for imp in imports}
        assert "require" in import_types
        assert "require_relative" in import_types
        assert "gem" in import_types
        assert "load" in import_types
        assert "autoload" in import_types

    # ===================================================================
    # Entry point detection tests
    # ===================================================================

    def test_find_entry_points_if_file(self, language):
        """Test detection of if __FILE__ == $0 pattern."""
        content = """
class MyScript
  def run
    puts "Running"
  end
end

if __FILE__ == $0
  MyScript.new.run
end
"""
        entry_points = language.find_entry_points("script.rb", content)

        if_main_entries = [ep for ep in entry_points if ep.type == "if_main"]
        assert len(if_main_entries) == 1
        assert if_main_entries[0].name == "__FILE__"

    def test_find_entry_points_if_file_program_name(self, language):
        """Test detection of if __FILE__ == $PROGRAM_NAME pattern."""
        content = """
if __FILE__ == $PROGRAM_NAME
  puts "Direct execution"
end
"""
        entry_points = language.find_entry_points("script.rb", content)

        if_main_entries = [ep for ep in entry_points if ep.type == "if_main"]
        assert len(if_main_entries) == 1

    def test_find_entry_points_rails_controller(self, language):
        """Test detection of Rails controllers."""
        content = """
class UsersController < ApplicationController
  def index
    @users = User.all
  end
end
"""
        entry_points = language.find_entry_points("app/controllers/users_controller.rb", content)

        controller_entries = [ep for ep in entry_points if ep.type == "controller"]
        assert len(controller_entries) == 1
        assert controller_entries[0].name == "UsersController"
        assert controller_entries[0].framework == "Rails"

    def test_find_entry_points_rails_api_controller(self, language):
        """Test detection of Rails API controllers."""
        content = """
class Api::V1::UsersController < ActionController::API
  def index
    render json: User.all
  end
end
"""
        entry_points = language.find_entry_points("app/controllers/api/v1/users_controller.rb", content)

        controller_entries = [ep for ep in entry_points if ep.type == "controller"]
        assert len(controller_entries) == 1
        assert controller_entries[0].name == "Api::V1::UsersController"

    def test_find_entry_points_rails_model(self, language):
        """Test detection of Rails models."""
        content = """
class User < ApplicationRecord
  has_many :posts
  validates :email, presence: true
end
"""
        entry_points = language.find_entry_points("app/models/user.rb", content)

        model_entries = [ep for ep in entry_points if ep.type == "model"]
        assert len(model_entries) == 1
        assert model_entries[0].name == "User"
        assert model_entries[0].framework == "Rails"

    def test_find_entry_points_rails_model_active_record_base(self, language):
        """Test detection of Rails models using ActiveRecord::Base."""
        content = """
class LegacyUser < ActiveRecord::Base
  self.table_name = 'users'
end
"""
        entry_points = language.find_entry_points("app/models/legacy_user.rb", content)

        model_entries = [ep for ep in entry_points if ep.type == "model"]
        assert len(model_entries) == 1
        assert model_entries[0].name == "LegacyUser"

    def test_find_entry_points_sinatra_routes(self, language):
        """Test detection of Sinatra HTTP routes."""
        content = """
require 'sinatra'

get '/hello' do
  'Hello World'
end

post '/api/users' do
  # Create user
end

put '/resource/:id' do
  # Update resource
end
"""
        entry_points = language.find_entry_points("app.rb", content)

        route_entries = [ep for ep in entry_points if ep.type == "route"]
        assert len(route_entries) == 3
        assert any(ep.name == "GET /hello" and ep.framework == "Sinatra" for ep in route_entries)
        assert any(ep.name == "POST /api/users" and ep.framework == "Sinatra" for ep in route_entries)
        assert any(ep.name == "PUT /resource/:id" and ep.framework == "Sinatra" for ep in route_entries)

    def test_find_entry_points_rack_app(self, language):
        """Test detection of Rack run statements."""
        content = """
require './app'

run MyApp
"""
        entry_points = language.find_entry_points("config.ru", content)

        rack_entries = [ep for ep in entry_points if ep.type == "rack_app"]
        assert len(rack_entries) == 1
        assert rack_entries[0].name == "MyApp"
        assert rack_entries[0].framework == "Rack"

    def test_find_entry_points_rack_app_new(self, language):
        """Test detection of Rack run with .new."""
        content = """
run App.new
"""
        entry_points = language.find_entry_points("config.ru", content)

        rack_entries = [ep for ep in entry_points if ep.type == "rack_app"]
        assert len(rack_entries) == 1
        assert rack_entries[0].name == "App.new"

    def test_find_entry_points_rspec(self, language):
        """Test detection of RSpec test blocks."""
        content = """
require 'spec_helper'

RSpec.describe User do
  describe '#email' do
    it 'validates presence' do
      expect(User.new).to validate_presence_of(:email)
    end
  end
end

describe AdminUser do
  it 'has admin role' do
    expect(subject.role).to eq('admin')
  end
end
"""
        entry_points = language.find_entry_points("spec/models/user_spec.rb", content)

        test_entries = [ep for ep in entry_points if ep.type == "test"]
        assert len(test_entries) == 2
        assert any(ep.name == "describe User" and ep.framework == "RSpec" for ep in test_entries)
        assert any(ep.name == "describe AdminUser" and ep.framework == "RSpec" for ep in test_entries)

    def test_find_entry_points_rake_tasks(self, language):
        """Test detection of Rake tasks."""
        content = """
namespace :db do
  task :seed do
    puts "Seeding database"
  end

  task :reset do
    puts "Resetting database"
  end
end

task :hello do
  puts "Hello"
end
"""
        entry_points = language.find_entry_points("lib/tasks/db.rake", content)

        rake_entries = [ep for ep in entry_points if ep.type == "rake_task"]
        assert len(rake_entries) == 4  # 1 namespace + 3 tasks
        assert any(ep.name == "db" and ep.framework == "Rake" for ep in rake_entries)
        assert any(ep.name == "seed" and ep.framework == "Rake" for ep in rake_entries)
        assert any(ep.name == "reset" and ep.framework == "Rake" for ep in rake_entries)
        assert any(ep.name == "hello" and ep.framework == "Rake" for ep in rake_entries)

    # ===================================================================
    # Classification tests
    # ===================================================================

    def test_classify_file_gemfile(self, language):
        """Test classification of Gemfile."""
        content = """
source 'https://rubygems.org'
gem 'rails'
"""
        cluster = language.classify_file("Gemfile", content)
        assert cluster == "infrastructure"

    def test_classify_file_rakefile(self, language):
        """Test classification of Rakefile."""
        content = """
task :default => :test
"""
        cluster = language.classify_file("Rakefile", content)
        assert cluster == "infrastructure"

    def test_classify_file_config_ru(self, language):
        """Test classification of config.ru."""
        content = """
run MyApp
"""
        cluster = language.classify_file("config.ru", content)
        assert cluster == "infrastructure"

    def test_classify_file_controller(self, language):
        """Test classification of controller files."""
        content = """
class UsersController < ApplicationController
  def index
    @users = User.all
  end
end
"""
        cluster = language.classify_file("app/controllers/users_controller.rb", content)
        assert cluster == "entry_points"

    def test_classify_file_model(self, language):
        """Test classification of model files."""
        content = """
class User < ApplicationRecord
  has_many :posts
end
"""
        cluster = language.classify_file("app/models/user.rb", content)
        assert cluster == "core"

    def test_classify_file_spec(self, language):
        """Test classification of spec files."""
        content = """
RSpec.describe User do
  it 'works' do
    expect(true).to be true
  end
end
"""
        cluster = language.classify_file("spec/models/user_spec.rb", content)
        assert cluster == "tests"

    def test_classify_file_test(self, language):
        """Test classification of test directory files."""
        content = """
require 'test_helper'

class UserTest < ActiveSupport::TestCase
  test "user is valid" do
    assert User.new.valid?
  end
end
"""
        cluster = language.classify_file("test/models/user_test.rb", content)
        assert cluster == "tests"

    def test_classify_file_lib(self, language):
        """Test classification of lib files."""
        content = """
module Utils
  def self.format(str)
    str.upcase
  end
end
"""
        cluster = language.classify_file("lib/utils.rb", content)
        assert cluster == "core"

    def test_classify_file_config(self, language):
        """Test classification of config files."""
        content = """
Rails.application.configure do
  config.cache_classes = false
end
"""
        cluster = language.classify_file("config/environments/development.rb", content)
        assert cluster == "infrastructure"

    def test_classify_file_sinatra_routes(self, language):
        """Test classification of Sinatra route files."""
        content = """
get '/hello' do
  'Hello World'
end

post '/users' do
  # Create user
end
"""
        cluster = language.classify_file("app.rb", content)
        assert cluster == "entry_points"

    # ===================================================================
    # should_analyze tests
    # ===================================================================

    def test_should_analyze_normal_file(self, language):
        """Test that normal Ruby files should be analyzed."""
        assert language.should_analyze("app.rb") == True
        assert language.should_analyze("model.rb") == True
        assert language.should_analyze("Rakefile") == True
        assert language.should_analyze("tasks/deploy.rake") == True

    # ===================================================================
    # Edge cases and line number tests
    # ===================================================================

    def test_import_line_numbers(self, language):
        """Test that line numbers are correctly captured for imports."""
        content = """# Header comment
require 'json'

require_relative '../config'

gem 'rails'
"""
        imports = language.extract_imports("test.rb", content)

        json_import = next(imp for imp in imports if imp.target_module == "json")
        assert json_import.line == 2

    def test_entry_point_line_numbers(self, language):
        """Test that line numbers are correctly captured for entry points."""
        content = """# Header

class UsersController < ApplicationController
  def index
  end
end

if __FILE__ == $0
  puts "Run"
end
"""
        entry_points = language.find_entry_points("test.rb", content)

        controller = next(ep for ep in entry_points if ep.type == "controller")
        assert controller.line == 2  # Adjusted for leading newline in triple-quoted string

        if_main = next(ep for ep in entry_points if ep.type == "if_main")
        assert if_main.line == 7  # Adjusted for leading newline in triple-quoted string

    def test_empty_file(self, language):
        """Test handling of empty files."""
        content = ""
        imports = language.extract_imports("empty.rb", content)
        entry_points = language.find_entry_points("empty.rb", content)

        assert imports == []
        assert entry_points == []

    def test_comments_ignored(self, language):
        """Test that commented imports are ignored."""
        content = """
# require 'json'
# require_relative '../config'
require 'active_support'
"""
        imports = language.extract_imports("test.rb", content)

        # Should only find the uncommented require
        assert len(imports) == 1
        assert imports[0].target_module == "active_support"
