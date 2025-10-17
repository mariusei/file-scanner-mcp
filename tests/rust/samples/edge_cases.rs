/// Edge cases for Rust scanner testing.

use std::fmt::{Debug, Display};
use std::marker::PhantomData;

/// Generic struct with lifetime and type parameters.
#[derive(Debug, Clone)]
pub struct Container<'a, T: Display> {
    value: &'a T,
    metadata: String,
}

/// Enum with various variants.
#[derive(Debug, PartialEq)]
pub enum Result<T, E> {
    Ok(T),
    Err(E),
}

/// Complex enum with named fields.
pub enum Message {
    Quit,
    Move { x: i32, y: i32 },
    Write(String),
    ChangeColor(i32, i32, i32),
}

/// Async trait for async operations.
#[async_trait]
pub trait AsyncProcessor {
    /// Process data asynchronously.
    async fn process(&self, data: &[u8]) -> Result<String, String>;
}

/// Struct with multiple lifetimes and generics.
pub struct ComplexStruct<'a, 'b, T, U>
where
    T: Display + Debug,
    U: Clone,
{
    first: &'a T,
    second: &'b U,
    _marker: PhantomData<T>,
}

impl<'a, 'b, T, U> ComplexStruct<'a, 'b, T, U>
where
    T: Display + Debug,
    U: Clone,
{
    /// Create a new complex struct.
    pub fn new(first: &'a T, second: &'b U) -> Self {
        Self {
            first,
            second,
            _marker: PhantomData,
        }
    }

    /// Process the data with complex signature.
    pub fn process<V>(&self, input: V) -> Option<V>
    where
        V: Clone + Debug,
    {
        Some(input)
    }
}

/// Async function with complex return type.
#[tokio::main]
pub async fn async_fetch(url: &str) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    Ok(vec![])
}

/// Unsafe function for low-level operations.
pub unsafe fn raw_pointer_access(ptr: *const u8) -> u8 {
    *ptr
}

/// Const function for compile-time evaluation.
pub const fn const_multiply(a: i32, b: i32) -> i32 {
    a * b
}

/// Extern function for FFI.
pub extern "C" fn ffi_function(x: i32) -> i32 {
    x * 2
}

/// Function with multiple modifiers.
pub async unsafe fn async_unsafe_function() -> Result<(), String> {
    Ok(())
}

/// Struct with multiple attributes.
#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg(test)]
#[allow(dead_code)]
pub struct AttributeShowcase {
    field: i32,
}

/// Module-level tests.
#[cfg(test)]
mod tests {
    use super::*;

    /// Test function.
    #[test]
    fn test_basic() {
        assert_eq!(1, 1);
    }

    /// Async test function.
    #[tokio::test]
    async fn test_async() {
        assert!(true);
    }
}

/// Macro for code generation.
#[macro_export]
macro_rules! create_function {
    ($func_name:ident) => {
        fn $func_name() {
            println!("Generated function");
        }
    };
}

/// Generic function with trait bounds.
pub fn generic_function<T, U>(first: T, second: U) -> String
where
    T: Display,
    U: Debug,
{
    format!("{} {:?}", first, second)
}

/// Function with impl Trait syntax.
pub fn impl_trait_return() -> impl Iterator<Item = i32> {
    vec![1, 2, 3].into_iter()
}

/// Function with dyn Trait.
pub fn dyn_trait_param(processor: &dyn Display) -> String {
    format!("{}", processor)
}

/// Trait with associated types.
pub trait Container {
    type Item;

    /// Get an item.
    fn get(&self) -> Option<Self::Item>;
}

/// Trait with default implementation.
pub trait DefaultBehavior {
    /// Method with default implementation.
    fn default_method(&self) -> String {
        "default".to_string()
    }

    /// Method that must be implemented.
    fn required_method(&self) -> i32;
}

/// Multiple impl blocks for same type.
impl User {
    /// First impl block method.
    pub fn method_one(&self) -> String {
        "one".to_string()
    }
}

impl User {
    /// Second impl block method.
    pub fn method_two(&self) -> String {
        "two".to_string()
    }
}

/// Simple struct for impl blocks.
pub struct User {
    name: String,
}
