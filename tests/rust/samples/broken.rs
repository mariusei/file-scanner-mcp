/// Broken Rust file for error handling tests.

use std::collections::HashMap;

/// Valid struct before errors.
pub struct ValidStruct {
    field: i32,
}

// Missing closing brace
pub struct BrokenStruct {
    field: String,
    // missing }

/// Function with syntax error.
pub fn broken_function( -> String {
    "missing param".to_string()
}

// Incomplete impl block
impl ValidStruct {
    pub fn method(&self

// Malformed enum
pub enum BrokenEnum {
    Variant1
    Variant2,  // Missing comma before
}

// Invalid trait
pub trait BrokenTrait {
    fn method(&self) ->
}

// Unclosed block comment
/**
 * This comment is never closed

pub fn after_comment() {
    println!("code");
}

// Random syntax errors
pub fn ;;;; invalid_tokens() {
    let x = ;
    return x
}

// Missing type annotation
pub fn missing_type(param) -> i32 {
    42
}

// Valid function after errors.
pub fn another_valid_function() -> bool {
    true
}
