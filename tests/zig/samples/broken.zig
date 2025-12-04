// This file contains intentionally broken Zig code for testing fallback parsing

const std = @import("std");

// Missing closing brace
pub const BrokenStruct = struct {
    field: i32,
    // missing };

pub fn brokenFunction(x: i32) i32 {
    return x +  // missing operand
}

// Syntax error in enum
pub const BrokenEnum = enum {
    value1
    value2,  // missing comma before
};

// Unclosed string
test "broken test {
    // This test is broken
}

// This function should still be detected by regex fallback
pub fn validFunction() void {
    // Valid function body
}

// Another struct that regex should find
const AnotherStruct = struct {
    x: f32,
    y: f32,
};

test "another test" {
    // This should be found
}
