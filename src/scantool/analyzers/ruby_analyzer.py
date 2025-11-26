"""Ruby code analyzer for extracting imports, entry points, and structure."""

import re
from typing import Optional
from pathlib import Path

from .base import BaseAnalyzer
from .models import ImportInfo, EntryPointInfo, DefinitionInfo, CallInfo


class RubyAnalyzer(BaseAnalyzer):
    """Analyzer for Ruby source files (.rb, .rake)."""

    def __init__(self):
        """Initialize Ruby analyzer."""
        super().__init__()

    # ===================================================================
    # REQUIRED: Metadata
    # ===================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        """File extensions for Ruby."""
        return [".rb", ".rake"]

    @classmethod
    def get_language_name(cls) -> str:
        """Language name."""
        return "Ruby"

    @classmethod
    def get_priority(cls) -> int:
        """Standard priority (0 = default, higher = preferred)."""
        return 10

    # ===================================================================
    # OPTIONAL: Skip patterns
    # ===================================================================

    def should_analyze(self, file_path: str) -> bool:
        """
        Skip files that should not be analyzed.

        Ruby doesn't have many common generated file patterns like other languages,
        so we keep this minimal.
        """
        # No specific skip patterns for Ruby - analyze all .rb and .rake files
        return True

    # ===================================================================
    # REQUIRED: Layer 1 - File-level analysis
    # ===================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """
        Extract imports from Ruby file.

        Ruby import patterns:
        - require 'foo'
        - require "foo"
        - require_relative '../bar'
        - require_relative "./utils"
        - gem 'rails', '~> 7.0'
        - load 'file.rb'
        - autoload :Constant, 'path/to/file'
        """
        imports = []

        # Pattern 1: require 'module'
        # Matches: require 'json'
        #          require "active_support"
        require_pattern = r'^\s*require\s+["\']([^"\']+)["\']'
        for match in re.finditer(require_pattern, content, re.MULTILINE):
            module = match.group(1).strip()
            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=module,
                import_type="require",
                line=line
            ))

        # Pattern 2: require_relative '../path'
        # Matches: require_relative '../foo'
        #          require_relative "./bar"
        require_relative_pattern = r'^\s*require_relative\s+["\']([^"\']+)["\']'
        for match in re.finditer(require_relative_pattern, content, re.MULTILINE):
            relative_path = match.group(1).strip()
            line = content[:match.start()].count('\n') + 1

            # Resolve relative path
            resolved = self._resolve_relative_import(file_path, relative_path)
            target = resolved if resolved else relative_path

            imports.append(ImportInfo(
                source_file=file_path,
                target_module=target,
                import_type="require_relative",
                line=line
            ))

        # Pattern 3: gem 'name', version
        # Matches: gem 'rails', '~> 7.0'
        #          gem "rspec"
        gem_pattern = r'^\s*gem\s+["\']([^"\']+)["\']'
        for match in re.finditer(gem_pattern, content, re.MULTILINE):
            gem_name = match.group(1).strip()
            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=gem_name,
                import_type="gem",
                line=line
            ))

        # Pattern 4: load 'file.rb'
        # Matches: load 'config.rb'
        load_pattern = r'^\s*load\s+["\']([^"\']+)["\']'
        for match in re.finditer(load_pattern, content, re.MULTILINE):
            load_file = match.group(1).strip()
            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=load_file,
                import_type="load",
                line=line
            ))

        # Pattern 5: autoload :Constant, 'path/to/file'
        # Matches: autoload :MyClass, 'lib/my_class'
        autoload_pattern = r'^\s*autoload\s+:(\w+)\s*,\s*["\']([^"\']+)["\']'
        for match in re.finditer(autoload_pattern, content, re.MULTILINE):
            constant_name = match.group(1).strip()
            path = match.group(2).strip()
            line = content[:match.start()].count('\n') + 1
            imports.append(ImportInfo(
                source_file=file_path,
                target_module=path,
                import_type="autoload",
                line=line,
                imported_names=[constant_name]
            ))

        return imports

    def find_entry_points(self, file_path: str, content: str) -> list[EntryPointInfo]:
        """
        Find entry points in Ruby file.

        Entry points:
        - if __FILE__ == $0 (script execution guard)
        - Rails controllers: class FooController < ApplicationController
        - Rails models: class Foo < ApplicationRecord
        - Sinatra routes: get '/path' do
        - Rack apps: run MyApp
        - RSpec tests: describe/context/it blocks
        """
        entry_points = []

        # Pattern 1: if __FILE__ == $0 (script entry point)
        # Matches: if __FILE__ == $0
        #          if __FILE__ == $PROGRAM_NAME
        file_guard_pattern = r'^\s*if\s+__FILE__\s*==\s*\$(?:0|PROGRAM_NAME)'
        for match in re.finditer(file_guard_pattern, content, re.MULTILINE):
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="if_main",
                name="__FILE__",
                line=line
            ))

        # Pattern 2: Rails controllers
        # Matches: class FooController < ApplicationController
        #          class Api::V1::UsersController < ActionController::API
        controller_pattern = r'^\s*class\s+((?:\w+::)*\w*Controller)\s*<\s*(?:Application|ActionController)'
        for match in re.finditer(controller_pattern, content, re.MULTILINE):
            controller_name = match.group(1)
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="controller",
                name=controller_name,
                line=line,
                framework="Rails"
            ))

        # Pattern 3: Rails models
        # Matches: class User < ApplicationRecord
        #          class User < ActiveRecord::Base
        model_pattern = r'^\s*class\s+((?:\w+::)*\w+)\s*<\s*(?:ApplicationRecord|ActiveRecord::Base)'
        for match in re.finditer(model_pattern, content, re.MULTILINE):
            model_name = match.group(1)
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="model",
                name=model_name,
                line=line,
                framework="Rails"
            ))

        # Pattern 4: Sinatra HTTP routes
        # Matches: get '/foo' do
        #          post '/api/users' do
        #          put '/resource/:id' do
        sinatra_route_pattern = r'^\s*(get|post|put|patch|delete|options|head)\s+["\']([^"\']+)["\']'
        for match in re.finditer(sinatra_route_pattern, content, re.MULTILINE):
            method = match.group(1).upper()
            route_path = match.group(2)
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="route",
                name=f"{method} {route_path}",
                line=line,
                framework="Sinatra"
            ))

        # Pattern 5: Rack run statement
        # Matches: run MyApp
        #          run App.new
        rack_run_pattern = r'^\s*run\s+(\w+(?:\.new)?)'
        for match in re.finditer(rack_run_pattern, content, re.MULTILINE):
            app_name = match.group(1)
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="rack_app",
                name=app_name,
                line=line,
                framework="Rack"
            ))

        # Pattern 6: RSpec test blocks
        # Matches: describe MyClass do
        #          RSpec.describe MyClass do
        rspec_describe_pattern = r'^\s*(?:RSpec\.)?describe\s+["\']?(\w+)'
        for match in re.finditer(rspec_describe_pattern, content, re.MULTILINE):
            subject = match.group(1)
            line = content[:match.start()].count('\n') + 1
            entry_points.append(EntryPointInfo(
                file=file_path,
                type="test",
                name=f"describe {subject}",
                line=line,
                framework="RSpec"
            ))

        # Pattern 7: Rake tasks
        # Matches: task :my_task do
        #          namespace :deployment do
        if file_path.endswith('.rake') or 'Rakefile' in file_path:
            rake_task_pattern = r'^\s*(?:task|namespace)\s+:(\w+)'
            for match in re.finditer(rake_task_pattern, content, re.MULTILINE):
                task_name = match.group(1)
                line = content[:match.start()].count('\n') + 1
                entry_points.append(EntryPointInfo(
                    file=file_path,
                    type="rake_task",
                    name=task_name,
                    line=line,
                    framework="Rake"
                ))

        return entry_points

    # ===================================================================
    # OPTIONAL: Layer 2 - Structure-level analysis (for call graphs)
    # ===================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """
        Extract function/class definitions.

        For Layer 1, we return empty list. Full implementation would require
        tree-sitter or Ripper for robust parsing of Ruby's flexible syntax.
        """
        return []

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """
        Extract method calls.

        For Layer 1, we return empty list. Full implementation would require
        tree-sitter or Ripper for robust parsing of Ruby's flexible syntax.
        """
        return []

    # ===================================================================
    # OPTIONAL: Custom classification
    # ===================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """
        Classify Ruby file into architectural cluster.

        Ruby-specific patterns:
        - Controllers -> entry_points
        - Models -> core
        - spec/ directory -> tests
        - test/ directory -> tests
        - lib/ directory -> core
        - config/ directory -> infrastructure
        - Gemfile -> infrastructure
        - Rakefile -> infrastructure
        """
        path = Path(file_path)
        filename = path.name

        # Check standard Ruby/Rails file names
        if filename in ('Gemfile', 'Rakefile', 'config.ru'):
            return "infrastructure"

        # Check directory structure
        if 'spec' in path.parts or 'test' in path.parts:
            return "tests"

        if 'controllers' in path.parts:
            return "entry_points"

        if 'models' in path.parts:
            return "core"

        if 'lib' in path.parts:
            return "core"

        if 'config' in path.parts:
            return "infrastructure"

        # Check content patterns
        if 'describe' in content or 'RSpec.describe' in content or 'context' in content:
            return "tests"

        if 'Controller <' in content:
            return "entry_points"

        if 'ApplicationRecord' in content or 'ActiveRecord::Base' in content:
            return "core"

        if any(keyword in content for keyword in ['get ', 'post ', 'put ', 'patch ', 'delete ']):
            # Likely a route definition
            if 'do' in content and ("'" in content or '"' in content):
                return "entry_points"

        # Fall back to base implementation
        return super().classify_file(file_path, content)
