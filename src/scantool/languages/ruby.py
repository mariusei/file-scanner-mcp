"""Ruby language support - unified scanner and analyzer.

This module combines RubyScanner and RubyAnalyzer into a single class,
eliminating duplication of metadata, tree-sitter parsing, and structure extraction.

Key optimizations:
- extract_definitions() reuses scan() output instead of re-parsing
- Single tree-sitter parser instance shared across all operations
"""

import re
from typing import Optional
from pathlib import Path

import tree_sitter_ruby
from tree_sitter import Language, Parser, Node

from .base import BaseLanguage
from .models import (
    StructureNode,
    ImportInfo,
    EntryPointInfo,
    DefinitionInfo,
    CallInfo,
)


class RubyLanguage(BaseLanguage):
    """Unified language handler for Ruby files (.rb, .rake, .gemspec).

    Provides both structure scanning and semantic analysis:
    - scan(): Extract modules, classes, methods with signatures and metadata
    - extract_imports(): Find require, require_relative, gem, load statements
    - find_entry_points(): Find main guards, Rails/Sinatra/Rack patterns
    - extract_definitions(): Convert scan() output to DefinitionInfo
    - extract_calls(): Find method calls (not fully implemented)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_ruby.language())

    # ===========================================================================
    # Metadata (REQUIRED)
    # ===========================================================================

    @classmethod
    def get_extensions(cls) -> list[str]:
        return [".rb", ".rake", ".gemspec"]

    @classmethod
    def get_language_name(cls) -> str:
        return "Ruby"

    @classmethod
    def get_priority(cls) -> int:
        return 10

    # ===========================================================================
    # Skip Logic (combined from scanner + analyzer)
    # ===========================================================================

    @classmethod
    def should_skip(cls, filename: str) -> bool:
        """Skip compiled Ruby files or bundle cache."""
        # Ruby doesn't have many compiled artifacts like Python
        return False

    def should_analyze(self, file_path: str) -> bool:
        """Skip files that should not be analyzed.

        Ruby doesn't have many common generated file patterns like other languages,
        so we keep this minimal.
        """
        # No specific skip patterns for Ruby - analyze all .rb and .rake files
        return True

    def is_low_value_for_inventory(self, file_path: str, size: int = 0) -> bool:
        """Identify low-value Ruby files for inventory listing.

        Low-value files:
        - Very small Gemfile or Rakefile
        - Empty spec helper files
        """
        filename = Path(file_path).name

        # Small Gemfile/Rakefile are low-value
        if filename in ("Gemfile", "Rakefile") and size < 100:
            return True

        # Small spec helpers
        if filename == "spec_helper.rb" and size < 100:
            return True

        return super().is_low_value_for_inventory(file_path, size)

    # ===========================================================================
    # Structure Scanning (from RubyScanner)
    # ===========================================================================

    def scan(self, source_code: bytes) -> Optional[list[StructureNode]]:
        """Scan Ruby source code and extract structure with metadata."""
        try:
            tree = self.parser.parse(source_code)

            # Check if we should use fallback due to too many errors
            if self._should_use_fallback(tree.root_node):
                return self._fallback_extract(source_code)

            return self._extract_structure(tree.root_node, source_code)

        except Exception as e:
            # Return error node instead of crashing
            return [StructureNode(
                type="error",
                name=f"Failed to parse: {str(e)}",
                start_line=1,
                end_line=1
            )]

    def _extract_structure(self, root: Node, source_code: bytes) -> list[StructureNode]:
        """Extract structure using tree-sitter."""
        structures = []

        def traverse(node: Node, parent_structures: list):
            # Handle parse errors
            if node.type == "ERROR":
                if self.show_errors:
                    error_node = StructureNode(
                        type="parse-error",
                        name="invalid syntax",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1
                    )
                    parent_structures.append(error_node)
                return

            # Modules - only process if it has a name field (not keyword tokens)
            if node.type == "module" and node.child_by_field_name("name"):
                module_node = self._extract_module(node, source_code)
                parent_structures.append(module_node)

                # Traverse children for nested structures (via body field)
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, module_node.children)

            # Classes - only process if it has a name field (not keyword tokens)
            elif node.type == "class" and node.child_by_field_name("name"):
                class_node = self._extract_class(node, source_code)
                parent_structures.append(class_node)

                # Traverse children for methods (via body field)
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        traverse(child, class_node.children)

            # Regular methods - only process if it has a name field
            elif node.type == "method" and node.child_by_field_name("name"):
                method_node = self._extract_method(node, source_code)
                parent_structures.append(method_node)

            # Singleton methods (def self.method_name) - only process if it has a name field
            elif node.type == "singleton_method" and node.child_by_field_name("name"):
                method_node = self._extract_singleton_method(node, source_code)
                parent_structures.append(method_node)

            # Require statements
            elif node.type == "call" and self._is_require_call(node, source_code):
                self._handle_require(node, parent_structures)

            else:
                for child in node.children:
                    traverse(child, parent_structures)

        traverse(root, structures)
        return structures

    def _extract_module(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract module with metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get comment above module
        docstring = self._extract_comment(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="module",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            docstring=docstring,
            complexity=complexity,
            children=[]
        )

    def _extract_class(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract class with full metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get superclass
        superclass_node = node.child_by_field_name("superclass")
        signature = None
        if superclass_node:
            superclass = self._get_node_text(superclass_node, source_code)
            signature = f"< {superclass}"

        # Get comment above class
        docstring = self._extract_comment(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="class",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            complexity=complexity,
            children=[]
        )

    def _extract_method(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract regular method with signature and metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get parameters
        signature = self._extract_method_signature(node, source_code)

        # Get comment above method
        docstring = self._extract_comment(node, source_code)

        # Check for visibility modifiers in name or context
        modifiers = self._extract_visibility_modifiers(node, source_code)

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="method",
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_singleton_method(self, node: Node, source_code: bytes) -> StructureNode:
        """Extract singleton method (class method) with metadata."""
        name_node = node.child_by_field_name("name")
        name = self._get_node_text(name_node, source_code) if name_node else "unnamed"

        # Get object (usually 'self')
        object_node = node.child_by_field_name("object")
        receiver = self._get_node_text(object_node, source_code) if object_node else "self"

        # Get parameters
        signature = self._extract_method_signature(node, source_code)

        # Get comment above method
        docstring = self._extract_comment(node, source_code)

        # Singleton methods are class methods
        modifiers = ["class"]

        # Calculate complexity
        complexity = self._calculate_complexity(node)

        return StructureNode(
            type="method",
            name=f"{receiver}.{name}",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
            docstring=docstring,
            modifiers=modifiers,
            complexity=complexity,
            children=[]
        )

    def _extract_method_signature(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract method signature with parameters."""
        params_node = node.child_by_field_name("parameters")

        if params_node:
            params_text = self._get_node_text(params_node, source_code)
            # Normalize the signature
            return self._normalize_signature(params_text)

        return "()"

    def _extract_comment(self, node: Node, source_code: bytes) -> Optional[str]:
        """Extract comment above or near a declaration."""
        # Strategy 1: Look for comment as previous sibling
        # This finds comments directly above the declaration
        prev = node.prev_sibling
        while prev:
            if prev.type == "comment":
                comment_text = self._get_node_text(prev, source_code)
                comment_text = comment_text.lstrip('#').strip()
                if comment_text:
                    return comment_text
            # Stop at non-whitespace, non-comment nodes
            if prev.type not in ("comment", "\n"):
                break
            prev = prev.prev_sibling

        # Strategy 2: For nodes inside body_statement (like classes inside modules),
        # check parent's previous sibling for comments
        if node.parent and node.parent.type == "body_statement":
            parent_prev = node.parent.prev_sibling
            while parent_prev:
                if parent_prev.type == "comment":
                    comment_text = self._get_node_text(parent_prev, source_code)
                    comment_text = comment_text.lstrip('#').strip()
                    if comment_text:
                        return comment_text
                # Stop at non-comment nodes
                if parent_prev.type not in ("comment", "\n"):
                    break
                parent_prev = parent_prev.prev_sibling

        return None

    def _extract_visibility_modifiers(self, node: Node, source_code: bytes) -> list[str]:
        """Extract visibility modifiers (public, private, protected)."""
        modifiers = []

        # In Ruby, visibility is typically determined by context
        # We could check for explicit visibility declarations, but for simplicity
        # we'll return public by default unless we detect private/protected context
        # This would require more complex traversal of the tree

        return modifiers

    def _is_require_call(self, node: Node, source_code: bytes) -> bool:
        """Check if a call node is a require or require_relative statement."""
        method_node = node.child_by_field_name("method")
        if method_node:
            method_name = self._get_node_text(method_node, source_code)
            return method_name in ("require", "require_relative")
        return False

    def _handle_require(self, node: Node, parent_structures: list):
        """Group require statements together."""
        if not parent_structures or parent_structures[-1].type != "requires":
            require_node = StructureNode(
                type="requires",
                name="require statements",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1
            )
            parent_structures.append(require_node)
        else:
            # Extend the end line of the existing require group
            parent_structures[-1].end_line = node.end_point[0] + 1

    def _fallback_extract(self, source_code: bytes) -> list[StructureNode]:
        """Regex-based extraction for severely malformed files."""
        text = source_code.decode('utf-8', errors='replace')
        structures = []

        # Find module definitions
        for match in re.finditer(r'^module\s+(\w+(?:::\w+)*)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="module",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find class definitions
        for match in re.finditer(r'^class\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="class",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find method definitions
        for match in re.finditer(r'^def\s+(\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num
            ))

        # Find singleton method definitions
        for match in re.finditer(r'^def\s+(self\.\w+)', text, re.MULTILINE):
            line_num = text[:match.start()].count('\n') + 1
            structures.append(StructureNode(
                type="method",
                name=match.group(1) + " (fallback)",
                start_line=line_num,
                end_line=line_num,
                modifiers=["class"]
            ))

        return structures

    # ===========================================================================
    # Semantic Analysis - Layer 1 (from RubyAnalyzer)
    # ===========================================================================

    def extract_imports(self, file_path: str, content: str) -> list[ImportInfo]:
        """Extract imports from Ruby file.

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
        """Find entry points in Ruby file.

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

    # ===========================================================================
    # Semantic Analysis - Layer 2
    # ===========================================================================

    def extract_definitions(self, file_path: str, content: str) -> list[DefinitionInfo]:
        """Extract function/class definitions by reusing scan() output.

        This is the key optimization: instead of re-parsing with tree-sitter,
        we convert the StructureNode output from scan() to DefinitionInfo.
        """
        try:
            structures = self.scan(content.encode("utf-8"))
            if not structures:
                return []
            return self._structures_to_definitions(file_path, structures)
        except Exception:
            # Fallback to regex-based extraction
            return self._extract_definitions_regex(file_path, content)

    def _extract_definitions_regex(
        self, file_path: str, content: str
    ) -> list[DefinitionInfo]:
        """Fallback: Extract definitions using regex."""
        definitions = []

        for match in re.finditer(r"^module\s+(\w+)", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="module",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        for match in re.finditer(r"^class\s+(\w+)", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="class",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        for match in re.finditer(r"^def\s+(\w+)\s*\(", content, re.MULTILINE):
            line = content[: match.start()].count("\n") + 1
            definitions.append(
                DefinitionInfo(
                    file=file_path,
                    type="method",
                    name=match.group(1),
                    line=line,
                    signature=None,
                    parent=None,
                )
            )

        return definitions

    def extract_calls(
        self, file_path: str, content: str, definitions: list[DefinitionInfo]
    ) -> list[CallInfo]:
        """Extract method calls.

        For Layer 1, we return empty list. Full implementation would require
        tree-sitter or Ripper for robust parsing of Ruby's flexible syntax.
        """
        return []

    # ===========================================================================
    # Classification (enhanced for Ruby)
    # ===========================================================================

    def classify_file(self, file_path: str, content: str) -> str:
        """Classify Ruby file into architectural cluster.

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

    # ===========================================================================
    # CodeMap Integration
    # ===========================================================================

    def resolve_import_to_file(
        self,
        module: str,
        source_file: str,
        all_files: list[str],
        definitions_map: dict[str, str],
    ) -> Optional[str]:
        """Resolve Ruby require to file path.

        Ruby import patterns:
        - require 'foo' -> lib/foo.rb, foo.rb
        - require_relative '../bar' -> already resolved

        Gem imports are skipped.
        """
        # Already a file path (from require_relative)
        if "/" in module or module.startswith("."):
            candidate = f"{module}.rb"
            if candidate in all_files:
                return candidate
            return None

        # Try lib/ prefix (common Ruby convention)
        candidate = f"lib/{module}.rb"
        if candidate in all_files:
            return candidate

        # Try app/ prefix (Rails convention)
        for prefix in ["app/", "lib/", ""]:
            for suffix in [".rb", "/init.rb"]:
                candidate = f"{prefix}{module.replace('::', '/')}{suffix}"
                if candidate in all_files:
                    return candidate

        return None

    def format_entry_point(self, ep: EntryPointInfo) -> str:
        """Format Ruby entry point for display.

        Formats:
        - rails_app: "Rails.application @line"
        - rack_app: "Rack app @line"
        - rake_task: "rake task @line"
        - bin_script: "bin/script"
        """
        if ep.type == "rails_app":
            return f"  {ep.file}:Rails.application @{ep.line}"
        elif ep.type == "rack_app":
            return f"  {ep.file}:Rack app @{ep.line}"
        elif ep.type == "rake_task":
            return f"  {ep.file}:rake {ep.name} @{ep.line}"
        elif ep.type == "bin_script":
            return f"  {ep.file}:bin/{ep.name}"
        else:
            return super().format_entry_point(ep)
