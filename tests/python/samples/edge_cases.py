"""Edge cases for Python scanner testing."""

from typing import Union, Optional, List, Dict, Generic, TypeVar
from abc import ABC, abstractmethod
import asyncio


# Multiple decorators
@property
@abstractmethod
def abstract_property(self):
    """Test abstract property."""
    pass


# Decorator with arguments
@dataclass(frozen=True, slots=True)
class FrozenConfig:
    """Frozen dataclass with slots."""
    name: str
    value: int


# Nested classes
class OuterClass:
    """Outer class with nested inner class."""

    class InnerClass:
        """Inner class for testing nesting."""

        def inner_method(self) -> str:
            """Method in inner class."""
            return "inner"

    class AnotherInner:
        """Another nested class."""
        pass


# Complex type hints
T = TypeVar('T')

class GenericContainer(Generic[T]):
    """Generic class with type parameter."""

    def __init__(self, value: T):
        self.value = value

    def get(self) -> T:
        """Get the stored value."""
        return self.value

    def process(
        self,
        items: List[Dict[str, Union[int, str]]],
        optional_param: Optional[T] = None
    ) -> Union[T, None]:
        """Complex signature with nested types."""
        return optional_param


# Async functions and methods
class AsyncService:
    """Service with async methods."""

    async def fetch_data(self, url: str) -> Dict[str, any]:
        """Async method to fetch data."""
        await asyncio.sleep(1)
        return {}

    @staticmethod
    async def static_async() -> None:
        """Static async method."""
        pass


# Nested functions
def outer_function(x: int) -> callable:
    """Function that returns a nested function."""

    def inner_function(y: int) -> int:
        """Nested function - should this be extracted?"""
        return x + y

    return inner_function


# All decorator types
class DecoratorShowcase:
    """Class demonstrating all decorator types."""

    @property
    def prop(self) -> str:
        """Property decorator."""
        return "value"

    @staticmethod
    def static() -> None:
        """Static method."""
        pass

    @classmethod
    def cls_method(cls) -> 'DecoratorShowcase':
        """Class method."""
        return cls()

    @abstractmethod
    def abstract(self) -> None:
        """Abstract method."""
        pass


# Lambda (should probably not be extracted)
lambda_func = lambda x, y: x + y

# Multiple functions with no docstrings
def no_doc_1():
    pass

def no_doc_2(arg1, arg2):
    return arg1 + arg2

def no_doc_3(x: int, y: str) -> bool:
    return True


# Single line docstrings vs multi-line
def single_line_doc():
    """This is a single line docstring."""
    pass

def multi_line_doc():
    """
    This is a multi-line docstring.

    It has multiple paragraphs and details.
    Only the first line should be extracted.
    """
    pass


# Class with inheritance
class ChildClass(OuterClass, ABC):
    """Child class inheriting from multiple parents."""

    def method(self) -> None:
        """Regular method."""
        pass


# Very long signature
def long_signature_function(
    param1: str,
    param2: int,
    param3: Optional[List[Dict[str, Union[int, str, bool]]]],
    param4: callable = None,
    *args,
    **kwargs
) -> Union[Dict[str, any], None]:
    """Function with very long signature."""
    pass
