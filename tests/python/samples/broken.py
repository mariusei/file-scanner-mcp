"""Intentionally malformed Python for testing error handling."""

# Missing colon
class BrokenClass
    def method(self):
        pass

# Incomplete function
def incomplete_func(

# Unmatched parentheses
def unmatched(x, y:
    return x + y

# Mixed indentation issues
class MixedIndent:
	def tab_method(self):
	    pass  # Tab then spaces

# Missing closing quote
def broken_string():
    x = "unclosed string
    return x

# Invalid syntax
def @@invalid():
    pass

# Incomplete decorator
@
def no_decorator_name():
    pass

class IncompleteClass:
    def method_no_body(self)

# More valid code after errors
class ValidAfterErrors:
    """This should still be parsed via fallback."""

    def valid_method(self) -> None:
        """Should be extracted in fallback mode."""
        pass
