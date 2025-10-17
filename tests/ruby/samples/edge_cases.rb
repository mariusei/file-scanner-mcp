# Edge cases for Ruby scanner testing

require 'json'
require 'set'

# Module with nested classes
module OuterModule
  # Outer class with nested inner class
  class OuterClass
    # Inner class for testing nesting
    class InnerClass
      # Method in inner class
      def inner_method
        "inner"
      end
    end

    # Another nested class
    class AnotherInner
    end
  end
end

# Class with inheritance
class BaseService
  def process
    puts "base process"
  end
end

# Child class inheriting from parent
class ChildService < BaseService
  # Override parent method
  def process
    super
    puts "child process"
  end
end

# Class with various method types
class MethodShowcase
  attr_accessor :name, :value
  attr_reader :id
  attr_writer :status

  def initialize(name)
    @name = name
    @id = rand(1000)
  end

  # Instance method with parameters
  def instance_method(arg1, arg2 = "default")
    "#{arg1} #{arg2}"
  end

  # Singleton method (class method)
  def self.class_method
    "class method"
  end

  # Another singleton method
  def self.create_default
    new("default")
  end

  # Private methods
  private

  def private_method
    "private"
  end

  # Protected methods
  protected

  def protected_method
    "protected"
  end
end

# Class using class << self syntax for class methods
class SingletonShowcase
  class << self
    # Class method defined in singleton class
    def from_hash(hash)
      new(hash[:name])
    end

    # Another class method
    def all
      []
    end
  end

  def initialize(name)
    @name = name
  end
end

# Multiple singleton methods
class MultiSingleton
  # First singleton method
  def self.method_one
    "one"
  end

  # Second singleton method
  def self.method_two(arg)
    "two: #{arg}"
  end
end

# Blocks and procs
class BlockExamples
  # Method that takes a block
  def with_block(&block)
    yield if block_given?
  end

  # Method with explicit proc parameter
  def with_proc(my_proc)
    my_proc.call
  end
end

# Metaprogramming examples
class DynamicMethods
  # Define methods dynamically
  ['get', 'set', 'delete'].each do |action|
    define_method("#{action}_value") do |key|
      "#{action}: #{key}"
    end
  end

  # Method with splat parameters
  def variadic_method(*args, **kwargs)
    [args, kwargs]
  end

  # Method with block parameter
  def block_method(&block)
    block.call if block
  end
end

# Nested functions (procs/lambdas)
def outer_function(x)
  # Lambda - should this be extracted?
  inner = ->(y) { x + y }
  inner
end

# Methods with no docstrings
def no_doc_1
end

def no_doc_2(arg1, arg2)
  arg1 + arg2
end

def no_doc_3(x, y)
  true
end

# Single line vs multi-line comments
# This is a single line comment
def single_line_comment
  "value"
end

# This is a multi-line comment
# that spans multiple lines
# and has several parts
def multi_line_comment
  "value"
end

# Complex module nesting
module A
  module B
    module C
      # Deeply nested class
      class DeepClass
        def deep_method
          "deep"
        end
      end
    end
  end
end

# Method with all parameter types
def complex_params(
  required,
  optional = "default",
  *splat,
  keyword:,
  keyword_optional: nil,
  **double_splat,
  &block
)
  [required, optional, splat, keyword, keyword_optional, double_splat, block]
end

# Constants and class variables
class Constants
  CONSTANT = "constant value"
  @@class_var = 0

  def self.increment
    @@class_var += 1
  end
end

# Alias and alias_method
class AliasExample
  def original_method
    "original"
  end

  alias_method :aliased_method, :original_method
  alias new_alias original_method
end
