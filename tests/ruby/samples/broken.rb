# Broken Ruby file for error handling tests

# Valid class before errors
class ValidClass
  def valid_method
    "valid"
  end
end

# Missing end for class
class BrokenClass
  def method_one
    "one"
  end

  def method_two
    "two"
  # Missing end

# Another broken structure
module BrokenModule
  class NestedClass
    def broken_method
      # Missing closing bracket
      array = [1, 2, 3
    end
  end
# Missing module end

# Incomplete method definition
def incomplete_method(arg1, arg2
  puts "incomplete"
end

# Valid method after errors
def another_valid_method
  "still works"
end

# Syntax error with operators
def syntax_error
  x = 5 +
end

# Invalid class inheritance
class InvalidInherit <
  def method
    "error"
  end
end

# Incomplete string
def string_error
  str = "incomplete string
end
